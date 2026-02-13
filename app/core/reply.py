"""
ReplyService - 回复路由服务

Sink 处理完消息后需要回复用户，但不应直接依赖各 Source 平台。
ReplyService 根据消息的 source 字段路由回复到正确的平台。
"""
from typing import Callable, Optional

from loguru import logger

from app.schemas.event import MessageSource, UnifiedMessage


# 回复函数签名: (message: UnifiedMessage, text: str) -> None
ReplyHandler = Callable[[UnifiedMessage, str], None]

# 发送函数签名: (user_id: str, text: str) -> None
SendHandler = Callable[[str, str], None]


class ReplyService:
    """
    回复路由服务（单例）

    各 Source 启动时注册回复方法：
        reply_service.register(MessageSource.FEISHU, feishu_reply, feishu_send)
    """

    _instance: Optional["ReplyService"] = None

    def __init__(self):
        self._reply_handlers: dict[str, ReplyHandler] = {}
        self._send_handlers: dict[str, SendHandler] = {}

    def register(
        self,
        source: MessageSource,
        reply_handler: ReplyHandler,
        send_handler: Optional[SendHandler] = None,
    ) -> None:
        """注册 Source 平台的回复/发送方法"""
        source_value = source.value if isinstance(source, MessageSource) else source
        self._reply_handlers[source_value] = reply_handler
        if send_handler:
            self._send_handlers[source_value] = send_handler
        logger.info(f"ReplyService: registered handlers for '{source_value}'")

    def reply(self, message: UnifiedMessage, text: str) -> None:
        """
        回复消息（按 source 路由）

        Args:
            message: 原始消息，用于确定回复目标
            text: 回复文本
        """
        source = message.source
        handler = self._reply_handlers.get(source)
        if not handler:
            logger.warning(f"ReplyService: no reply handler for source '{source}'")
            return
        try:
            handler(message, text)
        except Exception as e:
            logger.error(f"ReplyService: reply failed for '{source}': {e}")

    def send(self, source: MessageSource, user_id: str, text: str) -> None:
        """
        主动发送消息到指定平台的用户

        Args:
            source: 目标平台
            user_id: 用户 ID
            text: 消息文本
        """
        source_value = source.value if isinstance(source, MessageSource) else source
        handler = self._send_handlers.get(source_value)
        if not handler:
            logger.warning(f"ReplyService: no send handler for source '{source_value}'")
            return
        try:
            handler(user_id, text)
        except Exception as e:
            logger.error(f"ReplyService: send failed for '{source_value}': {e}")

    @classmethod
    def get_instance(cls) -> Optional["ReplyService"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "ReplyService":
        if cls._instance is not None:
            raise RuntimeError("ReplyService instance already exists")
        cls._instance = cls()
        logger.info("ReplyService initialized")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
