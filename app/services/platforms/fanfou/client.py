"""
Fanfou Platform Sink
Fanfou 平台消费者 - 接收统一消息并发送到 Fanfou

这是一个 Sink（消费者），职责：
1. 监听事件总线的消息
2. 将消息发送到 Fanfou API
3. 处理 OAuth 1.0a 认证
"""
import asyncio
import os
import json
from typing import ClassVar, Optional

import httpx
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage

from app.services.platforms.fanfou.sdk import Fanfou
from app.services.platforms.fanfou.token_utils import save_request_token, load_token, remove_token, save_user_token


class FanfouClient:
    """
    Fanfou 客户端
    
    实现 OAuth 1.0a 认证和消息发送
    注意：这里简化了 OAuth 实现，生产环境建议使用专门的 OAuth 库
    """
    
    _instance: ClassVar[Optional["FanfouClient"]] = None
    
    def __init__(self):
        """初始化 Fanfou 客户端"""
        self.base_url = "https://api.fanfou.com"
        self.client: Optional[httpx.AsyncClient] = None
        
        # OAuth 1.0a 凭据
        self.consumer_key = settings.fanfou_consumer_key
        self.consumer_secret = settings.fanfou_consumer_secret
        # self.access_token = settings.fanfou_access_token
        # self.access_secret = settings.fanfou_access_secret
        
        logger.info("FanfouClient initialized")
    
    async def start(self) -> None:
        """启动 Fanfou 客户端"""
        if self.client:
            logger.warning("Fanfou client already started")
            return
        
        # 创建异步 HTTP 客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0
        )
        
        logger.info("Fanfou client started")
    
    async def stop(self) -> None:
        """停止 Fanfou 客户端"""
        if not self.client:
            logger.warning("Fanfou client not started")
            return
        
        await self.client.aclose()
        self.client = None
        logger.info("Fanfou client stopped")
    
    def gen_auth_url(self, open_id: str):
        ff = Fanfou(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret
        )

        token, _ = ff.request_token()
        save_request_token(ff.oauth_token, token, open_id)

        oauth_callback = os.getenv('FANFOU_OAUTH_CALLBACK')
        url = f"https://fanfou.com/oauth/authorize?oauth_token={ff.oauth_token}&oauth_callback={oauth_callback}"
        return url


    def get_access_token(self, oauth_token: str):
        request_token = _load_token(oauth_token)

        if request_token:
            ff = Fanfou(
                consumer_key=self.consumer_key,
                consumer_secret=self.consumer_secret
            )

            open_id = request_token['open_id']
            token, response = ff.access_token(request_token['token'])

            remove_token(oauth_token)
            if token:
                _save_user_token(open_id, token)
                return "授权成功", open_id

        return "授权失败", None


    def post_text(self, open_id: str, text: str):
        ret = None
        user_token = _load_token(open_id)

        if user_token:
            token = user_token['token']

            ff = Fanfou(
                consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
                consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET'),
                oauth_token=token['oauth_token'],
                oauth_token_secret=token['oauth_token_secret']
            )

            content = {
                'status': text
            }

            ret, response = ff.post_text('/statuses/update', content)

        return ret


    def post_photo(self, open_id: str, image_data: bytes, text: str=None):
        ret = None
        user_token = self._load_token(open_id)

        if user_token:
            token = user_token['token']

            ff = Fanfou(
                consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
                consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET'),
                oauth_token=token['oauth_token'],
                oauth_token_secret=token['oauth_token_secret']
            )

            files = {
                'photo': image_data
            }

            params = {'status': text} if text else {}

            ret, response = ff.post_photo('/photos/upload', files, params)
            logger.info(ret)
            logger.info(response)

        return ret
    
    def _build_oauth_header(self, method: str, url: str, params: dict) -> str:
        """
        构建 OAuth 1.0a 认证头
        
        注意：这是简化实现，生产环境应使用标准 OAuth 库
        如 requests-oauthlib 或 authlib
        
        Args:
            method: HTTP 方法
            url: 请求 URL
            params: 请求参数
        
        Returns:
            OAuth 认证头字符串
        """
        # TODO: 实现完整的 OAuth 1.0a 签名算法
        # 这里返回空字符串，实际使用需要实现
        # 可以参考 fanfou_sdk 中的 oauth.py 实现
        return ""
    
    async def post_status(self, content: str) -> bool:
        """
        发送消息到 Fanfou
        
        Args:
            content: 消息内容
        
        Returns:
            是否成功
        """
        if not self.client:
            logger.error("Fanfou client not started")
            return False
        
        try:
            # Fanfou API: POST /statuses/update.json
            endpoint = "/statuses/update.json"
            
            # 简化实现：直接使用 fanfou_sdk
            # 在真实场景中，应该使用 OAuth 认证
            # 这里先记录日志，实际发送需要集成 fanfou_sdk
            logger.info(f"Would post to Fanfou: {content[:50]}...")
            
            # TODO: 实际发送到 Fanfou
            # 可以导入并使用项目根目录的 fanfou_sdk
            # 但需要注意：fanfou_sdk 可能是同步的，需要使用 run_in_executor
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to post to Fanfou: {e}", exc_info=True)
            return False
    
    async def handle_message(self, message: UnifiedMessage) -> None:
        """
        处理消息事件（事件总线回调）
        
        这个方法会被事件总线调用，当有新消息时
        
        Args:
            message: 统一消息对象
        """
        try:
            logger.info(
                f"Fanfou handler processing message {message.event_id} "
                f"from {message.source}"
            )
            
            # 格式化消息内容
            # 可以根据来源平台添加不同的前缀
            formatted_content = self._format_message(message)
            
            # 发送到 Fanfou
            success = await self.post_status(formatted_content)
            
            if success:
                logger.info(f"Successfully posted message {message.event_id} to Fanfou")
            else:
                logger.error(f"Failed to post message {message.event_id} to Fanfou")
        
        except Exception as e:
            logger.error(
                f"Error handling message {message.event_id} in Fanfou client: {e}",
                exc_info=True
            )
            raise
    
    def _format_message(self, message: UnifiedMessage) -> str:
        """
        格式化消息内容
        
        Args:
            message: 统一消息对象
        
        Returns:
            格式化后的消息文本
        """
        # 添加来源标识
        source_emoji = {
            "telegram": "📱",
            "feishu": "🚀",
            "system": "⚙️"
        }
        
        emoji = source_emoji.get(message.source, "📨")
        
        # 如果有发送者名称，添加到消息中
        sender_info = f"[@{message.sender_name}]" if message.sender_name else ""
        
        # 格式化：[emoji] 内容 (from sender)
        formatted = f"{emoji} {message.content}"
        if sender_info:
            formatted += f"\n{sender_info}"
        
        # Fanfou 限制 140 字符，截断如果太长
        if len(formatted) > 140:
            formatted = formatted[:137] + "..."
        
        return formatted
    
    @classmethod
    def get_instance(cls) -> Optional["FanfouClient"]:
        """获取单例实例（可能为 None）"""
        return cls._instance
    
    @classmethod
    def create_instance(cls) -> "FanfouClient":
        """
        创建单例实例并注册到事件总线
        
        Returns:
            FanfouClient 实例
        
        Raises:
            RuntimeError: 如果实例已存在
        """
        if cls._instance is not None:
            raise RuntimeError("FanfouClient instance already exists")
        cls._instance = cls()
        
        # 注册到事件总线
        bus.register(cls._instance.handle_message)
        
        logger.info("Fanfou client registered to event bus")
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        cls._instance = None
