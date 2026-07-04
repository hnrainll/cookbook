"""
Async Event Bus - Core Message Routing System
异步消息总线 - 核心消息路由系统

这是整个系统的核心组件，负责：
1. 解耦生产者和消费者
2. 并发分发消息到所有订阅者
3. 错误隔离 - 单个消费者失败不影响其他消费者
"""

import asyncio
from typing import Any, Awaitable, Callable, List, Optional

from loguru import logger

from app.schemas.event import UnifiedMessage

# 定义消息处理器类型
MessageHandler = Callable[[UnifiedMessage], Awaitable[None]]


def _handler_name(handler: MessageHandler) -> str:
    """获取 handler 的可读名称，兼容任意可调用对象。"""
    return getattr(handler, "__name__", handler.__class__.__name__)


def _sink_platform_name(handler: MessageHandler) -> Optional[str]:
    """从已注册 handler 推断对应的 sink 平台名。"""
    owner = getattr(handler, "__self__", None)
    if owner is None:
        return None

    class_name = owner.__class__.__name__
    return {
        "FanfouClient": "fanfou",
        "TelegramClient": "telegram",
        "MastodonClient": "mastodon",
        "ThreadsClient": "threads",
        "BlueskyClient": "bluesky",
    }.get(class_name)


class EventBus:
    """
    异步事件总线 - 单例模式

    实现发布/订阅模式，支持：
    - 编程式注册消费者
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

    def register(self, handler: MessageHandler) -> None:
        """
        注册消息处理器

        用法示例：
        ```python
        bus.register(client.handle_message)
        ```

        Args:
            handler: 异步消息处理函数
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.info(f"Registered event handler: {_handler_name(handler)}")

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
            return_exceptions=True,
        )

        # 这里统计的是 handler 执行状态，不代表各 sink 的业务发送结果。
        completed_count = sum(1 for r in results if not isinstance(r, Exception))
        raised_count = len(results) - completed_count

        logger.info(
            f"Message {message.event_id} distributed to {len(self._handlers)} handlers: "
            f"{completed_count} completed, {raised_count} raised exceptions"
        )
        await self._log_sink_result_summary(message)

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
        handler_name = _handler_name(handler)
        try:
            logger.debug(f"Handler {handler_name} processing message {message.event_id}")
            result = await handler(message)
            logger.debug(f"Handler {handler_name} completed for message {message.event_id}")
            return result
        except Exception as e:
            logger.error(
                f"Handler {handler_name} failed for message {message.event_id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    def get_handler_count(self) -> int:
        """获取已注册的处理器数量"""
        return len(self._handlers)

    async def _log_sink_result_summary(self, message: UnifiedMessage) -> None:
        if message.command:
            return

        expected_platforms = sorted(
            {
                platform
                for handler in self._handlers
                if (platform := _sink_platform_name(handler)) is not None
            }
        )
        if not expected_platforms:
            return

        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            logger.debug("Sink result summary skipped: DatabaseManager not initialized")
            return

        sink_results = await db.get_sink_results(str(message.event_id))
        result_by_platform = {result["sink_platform"]: result for result in sink_results}

        success_count = 0
        failed_platforms: list[str] = []
        missing_platforms: list[str] = []

        for platform in expected_platforms:
            result = result_by_platform.get(platform)
            if result is None:
                missing_platforms.append(platform)
            elif result["success"]:
                success_count += 1
            else:
                failed_platforms.append(platform)

        logger.info(
            "Message {} sink results: {} succeeded, {} failed, {} missing",
            message.event_id,
            success_count,
            len(failed_platforms),
            len(missing_platforms),
        )
        if failed_platforms:
            logger.warning(
                "Message {} failed sinks: {}",
                message.event_id,
                ", ".join(failed_platforms),
            )
        if missing_platforms:
            logger.warning(
                "Message {} sinks without persisted result: {}",
                message.event_id,
                ", ".join(missing_platforms),
            )

    def clear_handlers(self) -> None:
        """清除所有处理器（主要用于测试）"""
        self._handlers.clear()
        logger.warning("All event handlers cleared")


# 全局单例实例
# 在整个应用中使用此实例进行消息发布和订阅
bus = EventBus()
