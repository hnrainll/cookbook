"""
Async Event Bus - Core Message Routing System
异步消息总线 - 核心消息路由系统

这是整个系统的核心组件，负责：
1. 解耦生产者和消费者
2. 并发分发消息到所有订阅者
3. 错误隔离 - 单个消费者失败不影响其他消费者
"""
import asyncio
from typing import Any, Awaitable, Callable, List
from loguru import logger

from app.schemas.event import UnifiedMessage


# 定义消息处理器类型
MessageHandler = Callable[[UnifiedMessage], Awaitable[None]]


class EventBus:
    """
    异步事件总线 - 单例模式
    
    实现发布/订阅模式，支持：
    - 装饰器方式注册消费者
    - 异步并发分发消息
    - 自动错误隔离和日志记录
    
    为什么需要消息总线？
    1. **解耦**：平台模块之间不直接依赖，通过总线通信
    2. **扩展性**：新增消费者只需注册，无需修改生产者代码
    3. **容错性**：单个消费者失败不影响其他消费者继续处理
    """
    
    _instance = None
    _lock = asyncio.Lock()  # 用于线程安全的单例实现
    
    def __new__(cls):
        """单例模式：确保全局只有一个 EventBus 实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化事件总线"""
        if self._initialized:
            return
        
        self._handlers: List[MessageHandler] = []
        self._initialized = True
        logger.info("EventBus initialized")
    
    def on_event(self, handler: MessageHandler) -> MessageHandler:
        """
        装饰器：注册消息处理器
        
        用法示例：
        ```python
        @bus.on_event
        async def process_message(msg: UnifiedMessage):
            # 处理消息
            pass
        ```
        
        Args:
            handler: 异步消息处理函数
        
        Returns:
            原始处理函数（支持链式装饰器）
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.info(f"Registered event handler: {handler.__name__}")
        return handler
    
    def register(self, handler: MessageHandler) -> None:
        """
        编程式注册消息处理器
        
        Args:
            handler: 异步消息处理函数
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.info(f"Registered event handler: {handler.__name__}")
    
    async def publish(self, message: UnifiedMessage) -> None:
        """
        发布消息到所有订阅者
        
        使用 asyncio.gather 并发执行所有处理器，关键特性：
        - return_exceptions=True: 单个处理器异常不会中断其他处理器
        - 并发执行：所有处理器同时开始处理，提高吞吐量
        
        Args:
            message: 统一消息对象
        """
        if not self._handlers:
            logger.warning(f"No handlers registered, message dropped: {message.event_id}")
            return
        
        logger.debug(
            f"Publishing message {message.event_id} from {message.source} "
            f"to {len(self._handlers)} handlers"
        )
        
        # 并发分发消息到所有处理器
        # return_exceptions=True 确保单个处理器报错不影响其他处理器
        results = await asyncio.gather(
            *[self._safe_handle(handler, message) for handler in self._handlers],
            return_exceptions=True
        )
        
        # 统计处理结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        logger.info(
            f"Message {message.event_id} distributed: "
            f"{success_count} succeeded, {error_count} failed"
        )
    
    async def _safe_handle(self, handler: MessageHandler, message: UnifiedMessage) -> Any:
        """
        安全执行单个处理器，捕获并记录异常
        
        为什么需要这个包装函数？
        - 统一的异常处理和日志记录
        - 方便追踪哪个处理器出错了
        - 避免单个处理器的错误影响整体流程
        
        Args:
            handler: 消息处理器
            message: 消息对象
        
        Returns:
            处理器的返回值，或抛出异常
        """
        try:
            logger.debug(f"Handler {handler.__name__} processing message {message.event_id}")
            result = await handler(message)
            logger.debug(f"Handler {handler.__name__} completed for message {message.event_id}")
            return result
        except Exception as e:
            logger.error(
                f"Handler {handler.__name__} failed for message {message.event_id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True
            )
            raise
    
    def get_handler_count(self) -> int:
        """获取已注册的处理器数量"""
        return len(self._handlers)
    
    def clear_handlers(self) -> None:
        """清除所有处理器（主要用于测试）"""
        self._handlers.clear()
        logger.warning("All event handlers cleared")


# 全局单例实例
# 在整个应用中使用此实例进行消息发布和订阅
bus = EventBus()
