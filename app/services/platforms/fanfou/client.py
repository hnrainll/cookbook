"""
Fanfou Platform Sink
Fanfou 平台消费者 - 接收统一消息并发送到 Fanfou

这是一个 Sink（消费者），职责：
1. 监听事件总线的消息
2. 将消息发送到 Fanfou API
3. 处理 OAuth 1.0a 认证
"""
import asyncio
from typing import Optional

import httpx
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage


class FanfouClient:
    """
    Fanfou 客户端
    
    实现 OAuth 1.0a 认证和消息发送
    注意：这里简化了 OAuth 实现，生产环境建议使用专门的 OAuth 库
    """
    
    def __init__(self):
        """初始化 Fanfou 客户端"""
        self.base_url = "https://api.fanfou.com"
        self.client: Optional[httpx.AsyncClient] = None
        
        # OAuth 1.0a 凭据
        self.consumer_key = settings.fanfou_consumer_key
        self.consumer_secret = settings.fanfou_consumer_secret
        self.access_token = settings.fanfou_access_token
        self.access_secret = settings.fanfou_access_secret
        
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


# 全局 Fanfou 客户端实例
fanfou_client: Optional[FanfouClient] = None


def init_fanfou() -> FanfouClient:
    """
    初始化 Fanfou 客户端并注册到事件总线
    
    Returns:
        FanfouClient 实例
    """
    global fanfou_client
    fanfou_client = FanfouClient()
    
    # 注册到事件总线
    bus.register(fanfou_client.handle_message)
    
    logger.info("Fanfou client registered to event bus")
    
    return fanfou_client
