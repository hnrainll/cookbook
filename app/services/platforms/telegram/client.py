"""
Telegram Platform Adapter
Telegram 平台适配器 - 使用 aiogram 异步客户端

相比飞书，Telegram 的实现要简单得多：
- aiogram 是原生异步库，直接兼容 asyncio
- 不需要线程隔离或 Monkey Patch
- 使用 polling 方式接收消息（也可以使用 webhook）
"""
import asyncio
from typing import ClassVar, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
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
        
        # 跳过命令消息（已在 handle_start 中处理）
        if message.text.startswith("/"):
            return
        
        # 构建统一消息对象
        unified_msg = UnifiedMessage(
            source=MessageSource.TELEGRAM,
            content=message.text,
            sender_id=str(message.from_user.id),
            sender_name=message.from_user.full_name,
            chat_id=str(message.chat.id),
            raw_data={
                "message_id": message.message_id,
                "chat_type": message.chat.type,
                "username": message.from_user.username,
                "date": message.date.isoformat() if message.date else None
            }
        )
        
        logger.info(
            f"Received Telegram message: {unified_msg.event_id} "
            f"from {unified_msg.sender_name} ({unified_msg.sender_id})"
        )
        
        # 发布到事件总线
        await bus.publish(unified_msg)
        
        # 发送确认消息
        await message.answer("✅ Message received and forwarded!")
    
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
            # 初始化 Bot 和 Dispatcher
            self.bot = Bot(token=settings.telegram_bot_token)
            self.dp = Dispatcher()
            
            # 注册处理器
            self._setup_handlers()
            
            # 获取 Bot 信息
            bot_info = await self.bot.get_me()
            logger.info(f"Telegram bot started: @{bot_info.username} ({bot_info.id})")
            
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
        """
        try:
            assert self.dp is not None, "Dispatcher not initialized"
            assert self.bot is not None, "Bot not initialized"
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["message"]  # 只接收消息更新
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
        
        # 取消 polling 任务
        self._polling_task.cancel()
        
        try:
            await self._polling_task
        except asyncio.CancelledError:
            pass
        
        # 关闭 Bot session
        if self.bot:
            await self.bot.session.close()
        
        logger.info("Telegram client stopped")
    
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
