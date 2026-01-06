"""
Feishu Platform Adapter with Thread Isolation
飞书平台适配器 - 包含线程隔离和 Monkey Patch 解决方案

难点：
1. lark-oapi SDK 是同步阻塞的，不能直接在 asyncio 主循环中使用
2. SDK 内部可能绑定了全局 event loop，在子线程中运行会出错

解决方案：
1. 在独立线程中运行 SDK
2. Monkey Patch 修正 SDK 的 loop 绑定问题
3. 使用线程安全的方式将消息传递回主事件循环
"""
import asyncio
import sys
import threading
from typing import Any, ClassVar, Optional

from loguru import logger
from lark_oapi import Client
try:
    # 尝试导入事件相关类（根据实际 SDK 版本可能不同）
    from lark_oapi.event import EventManager, MessageReceiveEvent
except ImportError:
    # 如果导入失败，定义占位符（实际使用时需要查阅 SDK 文档）
    EventManager = None
    MessageReceiveEvent = None
    logger.warning("Failed to import EventManager from lark_oapi, Feishu integration may not work")

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import MessageSource, UnifiedMessage


class FeishuManager:
    """
    飞书客户端管理器
    
    核心职责：
    1. 在独立线程中运行飞书 SDK（避免阻塞主循环）
    2. Monkey Patch 修正 SDK 的 event loop 绑定问题
    3. 接收飞书消息并转换为 UnifiedMessage
    4. 线程安全地将消息发布到主事件总线
    """
    
    _instance: ClassVar[Optional["FeishuManager"]] = None
    
    def __init__(self, main_loop: asyncio.AbstractEventLoop):
        """
        初始化飞书管理器
        
        Args:
            main_loop: 主事件循环，用于将消息从子线程提交回主线程
        """
        self.main_loop = main_loop
        self.thread: Optional[threading.Thread] = None
        self.client: Optional[Client] = None
        self.event_manager: Optional[Any] = None  # type: ignore
        self._stop_event = threading.Event()
        
        logger.info("FeishuManager initialized")
    
    def _monkey_patch_sdk(self) -> None:
        """
        Monkey Patch: 修正飞书 SDK 的 event loop 绑定问题
        
        为什么需要这个？
        - lark-oapi SDK 内部某些模块可能在导入时绑定了全局 event loop
        - 当在子线程中运行时，这个 loop 可能是主线程的，导致错误
        - 我们需要将其替换为当前子线程的 loop
        
        实现原理：
        1. 遍历已导入的 lark_oapi 相关模块
        2. 检查模块中是否有名为 'loop' 的全局变量
        3. 如果有，将其替换为当前线程的 event loop
        """
        try:
            # 获取当前子线程的新 event loop
            current_loop = asyncio.get_event_loop()
            
            # 遍历所有已导入的模块
            for module_name, module in list(sys.modules.items()):
                # 只处理 lark_oapi 相关模块
                if module_name.startswith("lark_oapi") and module:
                    # 检查模块是否有 loop 属性
                    if hasattr(module, "loop"):
                        old_loop = getattr(module, "loop", None)
                        # 替换为当前线程的 loop
                        setattr(module, "loop", current_loop)
                        logger.debug(
                            f"Monkey patched {module_name}.loop: "
                            f"{id(old_loop)} -> {id(current_loop)}"
                        )
            
            logger.info("Feishu SDK monkey patch completed")
            
        except Exception as e:
            logger.error(f"Monkey patch failed: {e}", exc_info=True)
    
    def _run_in_thread(self) -> None:
        """
        在独立线程中运行飞书 SDK
        
        执行流程：
        1. 创建新的 event loop（子线程需要独立的 loop）
        2. 执行 Monkey Patch
        3. 初始化飞书客户端和事件管理器
        4. 注册消息接收处理器
        5. 进入事件循环（阻塞，直到收到停止信号）
        """
        try:
            # Step 1: 为子线程创建新的 event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop for Feishu thread")
            
            # Step 2: Monkey Patch SDK
            self._monkey_patch_sdk()
            
            # Step 3: 初始化飞书客户端
            self.client = Client.builder() \
                .app_id(settings.feishu_app_id) \
                .app_secret(settings.feishu_app_secret) \
                .build()
            
            # Step 4: 初始化事件管理器
            if EventManager is not None:
                self.event_manager = EventManager()
            else:
                logger.error("EventManager not available, skipping event registration")
                return
            
            # Step 5: 注册消息接收事件处理器
            @self.event_manager.register("im.message.receive_v1")  # type: ignore
            def handle_message(data: Any) -> None:
                """处理飞书消息接收事件"""
                try:
                    self._handle_feishu_message(data)
                except Exception as e:
                    logger.error(f"Error handling Feishu message: {e}", exc_info=True)
            
            logger.info("Feishu event handlers registered")
            
            # Step 6: 保持线程运行，等待停止信号
            logger.info("Feishu thread started, waiting for messages...")
            self._stop_event.wait()
            
            logger.info("Feishu thread stopping...")
            
        except Exception as e:
            logger.error(f"Error in Feishu thread: {e}", exc_info=True)
        finally:
            # 清理资源
            if loop and not loop.is_closed():
                loop.close()
            logger.info("Feishu thread stopped")
    
    def _handle_feishu_message(self, event: Any) -> None:  # type: ignore
        """
        处理飞书消息事件
        
        职责：
        1. 从飞书事件中提取消息内容
        2. 转换为 UnifiedMessage 标准格式
        3. 线程安全地发布到主事件循环的消息总线
        
        Args:
            event: 飞书消息接收事件
        """
        try:
            # 提取消息内容
            message = event.event.message
            sender = event.event.sender
            
            # 解析消息内容（飞书消息是 JSON 格式）
            content = message.content
            message_type = message.message_type
            
            # 只处理文本消息（可以扩展支持其他类型）
            if message_type != "text":
                logger.debug(f"Skipping non-text message type: {message_type}")
                return
            
            # 从 JSON 中提取文本
            import json
            content_obj = json.loads(content)
            text_content = content_obj.get("text", "")
            
            # 构建统一消息对象
            unified_msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content=text_content,
                sender_id=sender.sender_id.user_id if sender.sender_id else "unknown",
                sender_name=None,  # 飞书需要额外调用 API 获取用户名
                chat_id=message.chat_id,
                raw_data={
                    "message_id": message.message_id,
                    "message_type": message_type,
                    "chat_type": message.chat_type,
                    "event": event.event.__dict__
                }
            )
            
            logger.info(
                f"Received Feishu message: {unified_msg.event_id} "
                f"from {unified_msg.sender_id}"
            )
            
            # 线程安全地将消息发布到主循环的事件总线
            # 使用 run_coroutine_threadsafe 将协程提交到主事件循环
            future = asyncio.run_coroutine_threadsafe(
                bus.publish(unified_msg),
                self.main_loop
            )
            
            # 等待发布完成（可选，这里设置超时避免阻塞）
            future.result(timeout=5.0)
            
        except Exception as e:
            logger.error(f"Error processing Feishu message: {e}", exc_info=True)
    
    def start(self) -> None:
        """启动飞书客户端（在独立线程中）"""
        if self.thread and self.thread.is_alive():
            logger.warning("Feishu thread already running")
            return
        
        # 创建并启动 daemon 线程
        # daemon=True 表示主程序退出时，子线程自动退出
        self.thread = threading.Thread(
            target=self._run_in_thread,
            daemon=True,
            name="FeishuThread"
        )
        self.thread.start()
        logger.info("Feishu thread started")
    
    def stop(self) -> None:
        """停止飞书客户端"""
        if not self.thread or not self.thread.is_alive():
            logger.warning("Feishu thread not running")
            return
        
        logger.info("Stopping Feishu thread...")
        self._stop_event.set()
        
        # 等待线程结束（最多 5 秒）
        self.thread.join(timeout=5.0)
        
        if self.thread.is_alive():
            logger.warning("Feishu thread did not stop gracefully")
        else:
            logger.info("Feishu thread stopped")
    
    @classmethod
    def get_instance(cls) -> Optional["FeishuManager"]:
        """获取单例实例（可能为 None）"""
        return cls._instance
    
    @classmethod
    def create_instance(cls, main_loop: asyncio.AbstractEventLoop) -> "FeishuManager":
        """
        创建单例实例
        
        Args:
            main_loop: 主事件循环
        
        Returns:
            FeishuManager 实例
        
        Raises:
            RuntimeError: 如果实例已存在
        """
        if cls._instance is not None:
            raise RuntimeError("FeishuManager instance already exists")
        cls._instance = cls(main_loop)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        cls._instance = None
