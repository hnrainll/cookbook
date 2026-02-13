"""
AuthService - 多平台 OAuth 授权管理服务

集中管理所有 Sink 平台的 OAuth 授权流程：
- /login <platform> → 生成授权 URL
- /logout <platform> → 移除授权
- /auth?platform=xxx&oauth_token=xxx → OAuth 回调
"""
from typing import Optional, Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class AuthHandler(Protocol):
    """各平台实现的认证处理器接口"""

    async def gen_auth_url(self, user_id: str) -> str:
        """生成 OAuth 授权 URL"""
        ...

    async def handle_callback(self, params: dict) -> tuple[str, Optional[str]]:
        """
        处理 OAuth 回调

        Returns:
            (result_message, user_id) — user_id 用于回复用户
        """
        ...

    async def remove_auth(self, user_id: str) -> bool:
        """移除用户授权"""
        ...


class AuthService:
    """
    认证管理服务（单例）

    注册各平台的 AuthHandler，统一处理 /login、/logout 命令和 OAuth 回调。
    """

    _instance: Optional["AuthService"] = None

    def __init__(self):
        self._handlers: dict[str, AuthHandler] = {}

    def register(self, platform: str, handler: AuthHandler) -> None:
        """注册平台认证处理器"""
        self._handlers[platform] = handler
        logger.info(f"AuthService: registered handler for '{platform}'")

    def list_platforms(self) -> list[str]:
        """列出所有已注册的平台"""
        return list(self._handlers.keys())

    async def start_auth(self, platform: str, user_id: str) -> str:
        """
        开始授权流程，返回授权 URL 或提示信息

        Args:
            platform: 平台名称，如 "fanfou"
            user_id: source 端的用户 ID（如 open_id）
        """
        handler = self._handlers.get(platform)
        if not handler:
            available = ", ".join(self.list_platforms()) or "无"
            return f"未知平台: {platform}\n可用平台: {available}"
        return await handler.gen_auth_url(user_id)

    async def handle_callback(self, platform: str, params: dict) -> tuple[str, Optional[str]]:
        """
        处理 OAuth 回调

        Returns:
            (result_message, user_id)
        """
        handler = self._handlers.get(platform)
        if not handler:
            return f"未知平台: {platform}", None
        return await handler.handle_callback(params)

    async def remove_auth(self, platform: str, user_id: str) -> bool:
        """移除用户在指定平台的授权"""
        handler = self._handlers.get(platform)
        if not handler:
            return False
        return await handler.remove_auth(user_id)

    @classmethod
    def get_instance(cls) -> Optional["AuthService"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "AuthService":
        if cls._instance is not None:
            raise RuntimeError("AuthService instance already exists")
        cls._instance = cls()
        logger.info("AuthService initialized")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
