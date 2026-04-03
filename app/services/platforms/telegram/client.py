"""
Telegram Platform Adapter
Telegram 平台适配器 - 使用 aiogram 异步客户端

职责：
1. Source: 通过 polling 接收 Telegram 消息，转换为 UnifiedMessage 发布到事件总线
2. Sink: 监听事件总线消息，转发到配置的 Telegram 频道/群组
"""

import asyncio
import json
from typing import ClassVar, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import MessageSource, UnifiedMessage


class TelegramClient:
    """
    Telegram 客户端

    职责：
    1. 管理 Telegram Bot 的生命周期
    2. 接收 Telegram 消息
    3. 转换为 UnifiedMessage 并发布到事件总线
    """

    _instance: ClassVar[Optional["TelegramClient"]] = None

    def __init__(self):
        """初始化 Telegram 客户端"""
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._channel_id: str = settings.telegram_channel_id
        self._channel_name: str = ""

        logger.info("TelegramClient initialized")

    def _setup_handlers(self) -> None:
        """
        注册消息处理器

        aiogram 使用装饰器方式注册处理器：
        - @dp.message() 处理所有消息
        - @dp.message(Command("start")) 处理特定命令
        """

        assert self.dp is not None, "Dispatcher not initialized"

        @self.dp.message(Command("start"))
        async def handle_start(message: types.Message) -> None:
            """处理 /start 命令"""
            await message.answer(
                "👋 Hello! I'm a message sync bot.\n"
                "Send me any message and I'll forward it to configured platforms."
            )

        @self.dp.message()
        async def handle_message(message: types.Message) -> None:
            """处理所有文本消息"""
            try:
                await self._process_message(message)
            except Exception as e:
                logger.error(f"Error processing Telegram message: {e}", exc_info=True)
                await message.answer("❌ Sorry, failed to process your message.")

        logger.info("Telegram message handlers registered")

    async def _process_message(self, message: types.Message) -> None:
        """
        处理 Telegram 消息

        职责：
        1. 提取消息内容
        2. 转换为 UnifiedMessage
        3. 发布到事件总线

        Args:
            message: aiogram 消息对象
        """
        # 检查消息发送者是否存在
        if not message.from_user:
            logger.debug("Skipping message without sender info")
            return

        # 只处理文本消息
        if not message.text:
            logger.debug(f"Skipping non-text message from {message.from_user.id}")
            return

        # 识别命令消息（/login fanfou, /logout fanfou 等）
        command = None
        content = message.text
        if message.text.startswith("/"):
            # /start 由专用 handler 处理
            if message.text.strip() == "/start":
                return
            command = message.text
            content = message.text

        # 构建统一消息对象
        unified_msg = UnifiedMessage(
            source=MessageSource.TELEGRAM,
            content=content,
            sender_id=str(message.from_user.id),
            sender_name=message.from_user.full_name,
            chat_id=str(message.chat.id),
            command=command,
            raw_data={
                "message_id": message.message_id,
                "chat_type": message.chat.type,
                "username": message.from_user.username,
                "date": message.date.isoformat() if message.date else None,
            },
        )

        logger.info(
            f"Received Telegram message: {unified_msg.event_id} "
            f"from {unified_msg.sender_name} ({unified_msg.sender_id})"
        )

        # 发布到事件总线
        await bus.publish(unified_msg)

        # 发送确认消息（不再在这里直接回复，由 Sink 通过 ReplyService 回复）

    async def start(self) -> None:
        """
        启动 Telegram 客户端

        使用 polling 方式接收消息：
        - 优点：简单，不需要公网 IP 和 SSL 证书
        - 缺点：会有轻微延迟（通常 1-2 秒）

        生产环境建议使用 webhook 方式
        """
        if self._polling_task and not self._polling_task.done():
            logger.warning("Telegram client already running")
            return

        try:
            # 初始化 Bot 和 Dispatcher（支持代理）
            session = (
                AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
            )
            self.bot = Bot(token=settings.telegram_bot_token, session=session)
            self.dp = Dispatcher()

            # 注册处理器
            self._setup_handlers()

            # 获取 Bot 信息
            bot_info = await self.bot.get_me()
            logger.info(f"Telegram bot started: @{bot_info.username} ({bot_info.id})")

            # 获取频道名称
            if self._channel_id:
                try:
                    channel_id = (
                        self._channel_id
                        if self._channel_id.startswith("@")
                        else int(self._channel_id)
                    )
                    chat_info = await self.bot.get_chat(channel_id)
                    self._channel_name = chat_info.title or self._channel_id
                    logger.info(f"Telegram channel resolved: {self._channel_name}")
                except Exception as e:
                    logger.warning(f"Failed to get channel info: {e}")
                    self._channel_name = self._channel_id

            # 启动 polling
            logger.info("Starting Telegram polling...")
            self._polling_task = asyncio.create_task(self._run_polling())

        except Exception as e:
            logger.error(f"Failed to start Telegram client: {e}", exc_info=True)
            raise

    async def _run_polling(self) -> None:
        """
        运行 polling 循环

        这个方法会持续运行，直到调用 stop()
        handle_signals=False 避免与 uvicorn 的信号处理冲突
        """
        try:
            assert self.dp is not None, "Dispatcher not initialized"
            assert self.bot is not None, "Bot not initialized"
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["message"],
                handle_signals=False,
            )
        except asyncio.CancelledError:
            logger.info("Telegram polling cancelled")
        except Exception as e:
            logger.error(f"Error in Telegram polling: {e}", exc_info=True)

    async def stop(self) -> None:
        """停止 Telegram 客户端"""
        if not self._polling_task or self._polling_task.done():
            logger.warning("Telegram client not running")
            return

        logger.info("Stopping Telegram client...")

        # 通知 dispatcher 停止 polling，再取消任务
        if self.dp:
            await self.dp.stop_polling()
        self._polling_task.cancel()

        try:
            await self._polling_task
        except asyncio.CancelledError:
            pass

        # 关闭 Bot session
        if self.bot:
            await self.bot.session.close()

        logger.info("Telegram client stopped")

    # ===== Sink 功能：转发消息到 Telegram 频道 =====

    async def handle_message(self, message: UnifiedMessage) -> None:
        """
        事件总线回调：将消息转发到配置的 Telegram 频道

        支持文本和图片消息。command 消息不转发。
        """
        if not self.bot or not self._channel_id:
            return

        if message.command:
            return

        try:
            source_platform = message.source
            if message.message_type == "text":
                await self._sink_text(message, source_platform)
            elif message.message_type in ("image", "post"):
                await self._sink_image(message, source_platform)
            else:
                logger.debug(f"TelegramSink: skipping message type '{message.message_type}'")
        except Exception as e:
            logger.error(f"TelegramSink handle_message error: {e}", exc_info=True)
            raise

    async def _sink_text(self, message: UnifiedMessage, source_platform: str) -> None:
        """转发文本消息到频道"""
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()

        text = self._format_channel_message(message)
        ret = await self._send_to_channel(text=text)

        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, f"[{self._channel_name}] 消息发送成功")
        elif reply_service:
            reply_service.reply(message, f"[{self._channel_name}] 消息发送失败")

    async def _sink_image(self, message: UnifiedMessage, source_platform: str) -> None:
        """转发图片消息到频道"""
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()

        if not message.image_data:
            if reply_service:
                reply_service.reply(message, f"[{self._channel_name}] 图片数据为空，无法发送。")
            return

        caption = self._format_channel_message(message) if message.content else None
        ret = await self._send_to_channel(image_data=message.image_data, caption=caption)

        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, f"[{self._channel_name}] 图片发送成功")
        elif reply_service:
            reply_service.reply(message, f"[{self._channel_name}] 图片发送失败")

    def _format_channel_message(self, message: UnifiedMessage) -> str:
        """格式化频道消息"""
        return message.content

    async def _send_to_channel(
        self,
        text: Optional[str] = None,
        image_data: Optional[bytes] = None,
        caption: Optional[str] = None,
    ) -> Optional[dict]:
        """发送消息到 Telegram 频道，返回结果 dict 或 None"""
        try:
            if self.bot is None:
                logger.warning("Telegram bot not initialized")
                return None

            channel_id = (
                self._channel_id if self._channel_id.startswith("@") else int(self._channel_id)
            )

            if image_data:
                photo = BufferedInputFile(image_data, filename="image.jpg")
                result = await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=photo,
                    caption=caption,
                )
            elif text:
                result = await self.bot.send_message(
                    chat_id=channel_id,
                    text=text,
                )
            else:
                return None

            return {
                "message_id": result.message_id,
                "chat_id": result.chat.id,
                "date": result.date.isoformat() if result.date else None,
            }
        except Exception as e:
            logger.error(f"TelegramSink send to channel failed: {e}", exc_info=True)
            return None

    async def _save_sink_result(self, message: UnifiedMessage, ret: Optional[dict]) -> None:
        """保存发送结果到数据库"""
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return

        if ret:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="telegram",
                status_id=str(ret.get("message_id", "")),
                response_data=json.dumps(ret, ensure_ascii=False),
                success=True,
            )
        else:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="telegram",
                success=False,
                error_message="发送到 Telegram 频道失败",
            )

    # ===== Reply 功能：供 ReplyService 调用 =====

    def reply_to_message(self, message: "UnifiedMessage", text: str) -> None:
        """供 ReplyService 调用：回复用户消息"""
        if not self.bot:
            logger.warning("Telegram bot not started, cannot reply")
            return
        chat_id = message.chat_id
        if not chat_id:
            chat_id = message.sender_id
        try:
            asyncio.get_event_loop().create_task(
                self.bot.send_message(chat_id=int(chat_id), text=text)
            )
        except Exception as e:
            logger.error(f"Telegram reply failed: {e}")

    def send_to_user(self, user_id: str, text: str) -> None:
        """供 ReplyService 调用：主动发送消息"""
        if not self.bot:
            logger.warning("Telegram bot not started, cannot send")
            return
        try:
            asyncio.get_event_loop().create_task(
                self.bot.send_message(chat_id=int(user_id), text=text)
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    @classmethod
    def get_instance(cls) -> Optional["TelegramClient"]:
        """获取单例实例（可能为 None）"""
        return cls._instance

    @classmethod
    def create_instance(cls) -> "TelegramClient":
        """
        创建单例实例

        Returns:
            TelegramClient 实例

        Raises:
            RuntimeError: 如果实例已存在
        """
        if cls._instance is not None:
            raise RuntimeError("TelegramClient instance already exists")
        cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        cls._instance = None
