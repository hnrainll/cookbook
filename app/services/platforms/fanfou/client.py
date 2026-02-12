"""
Fanfou Platform Sink
Fanfou 平台消费者 - 接收统一消息并发送到 Fanfou

职责：
1. 监听事件总线的消息
2. 将消息发送到 Fanfou API（text / photo）
3. 处理 OAuth 1.0a 认证（通过 FanfouAuthHandler）
4. 通过 ReplyService 回复用户处理结果
"""
import json
from typing import ClassVar, Optional

from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage

from app.services.platforms.fanfou.sdk import Fanfou


class FanfouAuthHandler:
    """
    Fanfou OAuth 认证处理器

    实现 AuthHandler 协议，由 AuthService 调用。
    Token 存储委托给 DatabaseManager。
    """

    def __init__(self):
        self.consumer_key = settings.fanfou_consumer_key
        self.consumer_secret = settings.fanfou_consumer_secret
        self.oauth_callback = settings.fanfou_oauth_callback

    async def gen_auth_url(self, user_id: str) -> str:
        """生成 Fanfou OAuth 授权 URL"""
        ff = Fanfou(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
        )
        token, _ = await ff.request_token()

        # 保存 request token 到数据库
        from app.services.storage.db import DatabaseManager
        db = DatabaseManager.get_instance()
        if db:
            await db.save_request_token(
                oauth_token=ff.oauth_token,
                source_platform="feishu",
                source_user_id=user_id,
                sink_platform="fanfou",
                token_data=json.dumps(token),
            )

        url = (
            f"https://fanfou.com/oauth/authorize"
            f"?oauth_token={ff.oauth_token}"
            f"&oauth_callback={self.oauth_callback}"
        )
        return url

    async def handle_callback(self, params: dict) -> tuple[str, Optional[str]]:
        """处理 OAuth 回调，交换 access token"""
        oauth_token = params.get("oauth_token")
        if not oauth_token:
            return "授权失败：缺少 oauth_token", None

        from app.services.storage.db import DatabaseManager
        db = DatabaseManager.get_instance()
        if not db:
            return "授权失败：数据库未初始化", None

        request_record = await db.get_request_token(oauth_token)
        if not request_record:
            return "授权失败：request token 不存在或已过期", None

        source_user_id = request_record["source_user_id"]
        source_platform = request_record["source_platform"]
        token = json.loads(request_record["token_data"])

        # 交换 access token
        ff = Fanfou(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
        )
        access_token, response = await ff.access_token(token)

        # 清理 request token
        await db.delete_request_token(oauth_token)

        if access_token:
            await db.save_user_token(
                source_platform=source_platform,
                source_user_id=source_user_id,
                sink_platform="fanfou",
                token_data=json.dumps(access_token),
            )
            return "授权成功", source_user_id
        return "授权失败", None

    async def remove_auth(self, user_id: str) -> bool:
        """移除用户的 Fanfou 授权"""
        from app.services.storage.db import DatabaseManager
        db = DatabaseManager.get_instance()
        if not db:
            return False
        return await db.delete_user_token(
            source_platform="feishu",
            source_user_id=user_id,
            sink_platform="fanfou",
        )


class FanfouClient:
    """
    Fanfou 客户端

    事件总线消费者，处理三种消息：
    - command: /login, /logout → 委托 AuthService
    - text: 发文本到 Fanfou
    - image: 发图片到 Fanfou
    """

    _instance: ClassVar[Optional["FanfouClient"]] = None

    def __init__(self):
        self.consumer_key = settings.fanfou_consumer_key
        self.consumer_secret = settings.fanfou_consumer_secret
        logger.info("FanfouClient initialized")

    async def start(self) -> None:
        logger.info("Fanfou client started")

    async def stop(self) -> None:
        logger.info("Fanfou client stopped")

    async def _get_fanfou_for_user(self, source_platform: str, user_id: str) -> Optional[Fanfou]:
        """获取已授权用户的 Fanfou 实例"""
        from app.services.storage.db import DatabaseManager
        db = DatabaseManager.get_instance()
        if not db:
            return None

        token_data = await db.get_user_token(source_platform, user_id, "fanfou")
        if not token_data:
            return None

        token = json.loads(token_data)
        return Fanfou(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            oauth_token=token["oauth_token"],
            oauth_token_secret=token["oauth_token_secret"],
        )

    async def post_text(self, source_platform: str, user_id: str, text: str) -> Optional[dict]:
        """发文本到 Fanfou"""
        ff = await self._get_fanfou_for_user(source_platform, user_id)
        if not ff:
            return None
        ret, response = await ff.post_text("/statuses/update", {"status": text})
        return ret

    async def post_photo(
        self, source_platform: str, user_id: str, image_data: bytes, text: Optional[str] = None
    ) -> Optional[dict]:
        """发图片到 Fanfou"""
        ff = await self._get_fanfou_for_user(source_platform, user_id)
        if not ff:
            return None
        files = {"photo": image_data}
        params = {"status": text} if text else {}
        ret, response = await ff.post_photo("/photos/upload", files, params)
        return ret

    async def handle_message(self, message: UnifiedMessage) -> None:
        """
        事件总线回调：处理统一消息

        - command 消息 → 委托 AuthService
        - text 消息 → post_text → 回复结果
        - image 消息 → post_photo → 回复结果
        """
        try:
            if message.command:
                await self._handle_command(message)
                return

            source_platform = message.source
            user_id = message.sender_id

            if message.message_type == "text":
                await self._handle_text(message, source_platform, user_id)
            elif message.message_type in ("image", "post"):
                await self._handle_image(message, source_platform, user_id)
            else:
                logger.debug(f"Fanfou: skipping message type '{message.message_type}'")

        except Exception as e:
            logger.error(f"Fanfou handle_message error: {e}", exc_info=True)
            raise

    async def _handle_command(self, message: UnifiedMessage) -> None:
        """处理 /login, /logout 命令"""
        from app.core.auth import AuthService
        from app.core.reply import ReplyService

        auth_service = AuthService.get_instance()
        reply_service = ReplyService.get_instance()

        if not auth_service or not reply_service:
            logger.warning("AuthService or ReplyService not initialized")
            return

        command = message.command
        parts = command.split()
        cmd = parts[0]

        if cmd == "/login":
            if len(parts) < 2:
                platforms = auth_service.list_platforms()
                text = "可用平台: " + ", ".join(platforms) if platforms else "暂无可用平台"
                reply_service.reply(message, text)
                return

            platform = parts[1]
            url = await auth_service.start_auth(platform, message.sender_id)
            reply_service.reply(message, f"请点击如下链接并授权登录。\n{url}")

        elif cmd == "/logout":
            if len(parts) < 2:
                reply_service.reply(message, "请指定平台，如: /logout fanfou")
                return

            platform = parts[1]
            success = await auth_service.remove_auth(platform, message.sender_id)
            reply_service.reply(message, "登出成功" if success else "登出失败")

    async def _handle_text(self, message: UnifiedMessage, source_platform: str, user_id: str) -> None:
        """处理文本消息"""
        from app.core.reply import ReplyService
        reply_service = ReplyService.get_instance()

        ret = await self.post_text(source_platform, user_id, message.content)

        await self._save_sink_result(message, ret)

        if reply_service and ret:
            status_id = ret.get("id", "")
            reply_service.reply(
                message, f"消息发送成功\n\nhttps://fanfou.com/statuses/{status_id}"
            )
        elif reply_service:
            reply_service.reply(message, "消息发送失败")

    async def _handle_image(self, message: UnifiedMessage, source_platform: str, user_id: str) -> None:
        """处理图片消息"""
        from app.core.reply import ReplyService
        reply_service = ReplyService.get_instance()

        if not message.image_data:
            if reply_service:
                reply_service.reply(message, "图片数据为空，无法发送。")
            return

        text = message.content if message.content else None
        ret = await self.post_photo(source_platform, user_id, message.image_data, text)

        await self._save_sink_result(message, ret)

        if reply_service and ret:
            status_id = ret.get("id", "")
            reply_service.reply(
                message, f"图片发送成功\n\nhttps://fanfou.com/statuses/{status_id}"
            )
        elif reply_service:
            reply_service.reply(message, "图片发送失败")

    async def _save_sink_result(self, message: UnifiedMessage, ret: Optional[dict]) -> None:
        """保存发送结果到数据库"""
        from app.services.storage.db import DatabaseManager
        db = DatabaseManager.get_instance()
        if not db:
            return

        if ret:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="fanfou",
                status_id=ret.get("id"),
                status_url=f"https://fanfou.com/statuses/{ret.get('id', '')}",
                response_data=json.dumps(ret, ensure_ascii=False),
                success=True,
            )
        else:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="fanfou",
                success=False,
                error_message="发送失败",
            )

    @classmethod
    def get_instance(cls) -> Optional["FanfouClient"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "FanfouClient":
        if cls._instance is not None:
            raise RuntimeError("FanfouClient instance already exists")
        cls._instance = cls()
        bus.register(cls._instance.handle_message)
        logger.info("Fanfou client registered to event bus")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
