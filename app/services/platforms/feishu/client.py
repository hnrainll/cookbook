"""
Feishu Platform Adapter with Thread Isolation
飞书平台适配器 - 使用 lark.ws.Client WebSocket 长连接

核心方案：
1. lark-oapi SDK 是同步阻塞的，运行在独立线程
2. Monkey Patch 修正 SDK 的 event loop 绑定问题
3. 使用 lark.ws.Client + EventDispatcherHandler（与旧版一致）
4. 线程安全地将消息发布到主事件循环的消息总线
"""

import asyncio
import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import ClassVar, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateMessageResponse,
    GetMessageResourceRequest,
    GetMessageResourceResponse,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    ReplyMessageResponse,
)
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import MessageSource, UnifiedMessage
from app.utils.feishu import extract_img_and_first_text_group
from app.utils.image import compress_image_advanced


class OrderedDictDeduplicator:
    """消息去重器，使用 OrderedDict 实现 LRU 风格去重"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.messages: OrderedDict[str, bool] = OrderedDict()

    def add(self, message_id: str) -> bool:
        """添加消息 ID，返回 True 表示是新消息，False 表示重复"""
        if message_id in self.messages:
            return False
        if len(self.messages) >= self.max_size:
            self.messages.popitem(last=False)
        self.messages[message_id] = True
        return True

    def exists(self, message_id: str) -> bool:
        return message_id in self.messages


class FeishuManager:
    """
    飞书客户端管理器

    核心职责：
    1. 在独立线程中运行 lark.ws.Client WebSocket 长连接
    2. 接收飞书消息并转换为 UnifiedMessage
    3. 线程安全地将消息发布到主事件总线
    4. 提供 send_message / reply_message 供 ReplyService 使用
    """

    _instance: ClassVar[Optional["FeishuManager"]] = None

    def __init__(self, main_loop: asyncio.AbstractEventLoop):
        self.main_loop = main_loop
        self.thread: Optional[threading.Thread] = None
        self.client: Optional[lark.Client] = None
        self._dedup = OrderedDictDeduplicator()
        logger.info("FeishuManager initialized")

    def send_message(self, open_id: str, text: str) -> CreateMessageResponse:
        """发送消息给用户"""
        content = json.dumps({"text": text})
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(open_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        return response

    def reply_message(self, message_id: str, text: str) -> ReplyMessageResponse:
        """回复消息"""
        content = json.dumps({"text": text})
        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                ReplyMessageRequestBody.builder().content(content).msg_type("text").build()
            )
            .build()
        )
        response = self.client.im.v1.message.reply(request)
        return response

    def get_feishu_image_data(self, message_id: str, file_key: str) -> Optional[bytes]:
        """下载飞书图片并压缩"""
        try:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type("image")
                .build()
            )
            response: GetMessageResourceResponse = self.client.im.v1.message_resource.get(request)

            if response.code == 0:
                return compress_image_advanced(response.file.read())
            else:
                logger.error(f"下载飞书图片失败: {response.msg}")
        except Exception as e:
            logger.error(f"下载飞书图片异常: {e}")
        return None

    def _reply_for_reply_service(self, message: UnifiedMessage, text: str) -> None:
        """供 ReplyService 调用的回复方法"""
        message_id = message.raw_data.get("message_id")
        if message_id:
            try:
                self.reply_message(message_id, text)
            except Exception as e:
                logger.error(f"飞书回复失败: {e}")
        else:
            # 没有 message_id，用 send_message
            try:
                self.send_message(message.sender_id, text)
            except Exception as e:
                logger.error(f"飞书发送失败: {e}")

    def _send_for_reply_service(self, user_id: str, text: str) -> None:
        """供 ReplyService 调用的发送方法"""
        try:
            self.send_message(user_id, text)
        except Exception as e:
            logger.error(f"飞书发送失败: {e}")

    def _do_handle_message(self, data: P2ImMessageReceiveV1) -> None:
        """处理飞书消息接收事件（在子线程中执行）"""
        try:
            open_id = data.event.sender.sender_id.open_id
            message_type = data.event.message.message_type
            message_id = data.event.message.message_id
            chat_id = data.event.message.chat_id

            # 去重
            if self._dedup.exists(message_id):
                logger.debug(f"重复消息: {message_id}")
                return
            self._dedup.add(message_id)

            if message_type == "text":
                self._handle_text_message(data, open_id, message_id, chat_id)
            elif message_type == "image":
                self._handle_image_message(data, open_id, message_id, chat_id)
            elif message_type == "post":
                self._handle_post_message(data, open_id, message_id, chat_id)
            else:
                self.send_message(
                    open_id,
                    f"当前饭薯不支持该消息类型. message_type: {message_type}",
                )

        except Exception as e:
            logger.error(f"处理飞书消息异常: {e}", exc_info=True)

    def _handle_text_message(self, data, open_id, message_id, chat_id):
        """处理文本消息"""
        content = json.loads(data.event.message.content)["text"]

        # 检查命令
        if content.startswith("/"):
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content=content,
                message_type="text",
                sender_id=open_id,
                chat_id=chat_id,
                command=content,
                raw_data={"message_id": message_id, "message_type": "text"},
            )
            self._publish_to_bus(msg)
            return

        # 检查长度
        if len(content) > 140:
            self.reply_message(message_id, "消息长度大于140，无法发送。")
            return

        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content=content,
            message_type="text",
            sender_id=open_id,
            chat_id=chat_id,
            raw_data={"message_id": message_id, "message_type": "text"},
        )
        self._publish_to_bus(msg)

    def _handle_image_message(self, data, open_id, message_id, chat_id):
        """处理图片消息"""
        content = json.loads(data.event.message.content)
        image_key = content.get("image_key")

        if not image_key:
            self.reply_message(message_id, "未找到图片文件。")
            return

        image_data = self.get_feishu_image_data(message_id, image_key)
        if not image_data:
            self.reply_message(message_id, "下载图片失败，无法发送。")
            return

        # 保存图片到文件系统
        image_path = self._save_image(str(message_id), image_data)

        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="",
            message_type="image",
            sender_id=open_id,
            chat_id=chat_id,
            image_data=image_data,
            image_key=image_key,
            image_path=image_path,
            raw_data={"message_id": message_id, "message_type": "image"},
        )
        self._publish_to_bus(msg)

    def _handle_post_message(self, data, open_id, message_id, chat_id):
        """处理富文本消息"""
        content = json.loads(data.event.message.content)
        image_key, text = extract_img_and_first_text_group(content)

        if image_key:
            image_data = self.get_feishu_image_data(message_id, image_key)
            if not image_data:
                self.reply_message(message_id, "下载图片失败，无法发送。")
                return

            image_path = self._save_image(str(message_id), image_data)
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content=text or "",
                message_type="image",
                sender_id=open_id,
                chat_id=chat_id,
                image_data=image_data,
                image_key=image_key,
                image_path=image_path,
                raw_data={"message_id": message_id, "message_type": "post"},
            )
            self._publish_to_bus(msg)
        elif text:
            if len(text) > 140:
                self.reply_message(message_id, "消息长度大于140，无法发送。")
                return

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content=text,
                message_type="text",
                sender_id=open_id,
                chat_id=chat_id,
                raw_data={"message_id": message_id, "message_type": "post"},
            )
            self._publish_to_bus(msg)
        else:
            self.reply_message(message_id, "发送富文本内容失败。")

    def _save_image(self, event_id: str, image_data: bytes) -> str:
        """保存图片到文件系统，返回相对路径"""
        image_dir = Path("data/images")
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = f"data/images/{event_id}.jpg"
        Path(image_path).write_bytes(image_data)
        return image_path

    def _publish_to_bus(self, message: UnifiedMessage) -> None:
        """线程安全地将消息发布到主事件循环的 EventBus"""
        try:
            future = asyncio.run_coroutine_threadsafe(bus.publish(message), self.main_loop)
            future.result(timeout=10.0)
        except Exception as e:
            logger.error(f"发布消息到 EventBus 失败: {e}", exc_info=True)

    def _run_in_thread(self) -> None:
        """在独立线程中运行 lark.ws.Client WebSocket 长连接"""
        try:
            # 创建子线程的 event loop
            feishu_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(feishu_loop)

            # Monkey Patch：修复 SDK 的全局 loop 变量
            feishu_ws_module_name = lark.ws.Client.__module__
            if feishu_ws_module_name in sys.modules:
                feishu_ws_module = sys.modules[feishu_ws_module_name]
                if hasattr(feishu_ws_module, "loop"):
                    setattr(feishu_ws_module, "loop", feishu_loop)
                    logger.info(f"已修复 {feishu_ws_module_name} 中的全局 loop 变量")

            # 初始化 Lark Client（用于 OpenAPI 调用）
            self.client = (
                lark.Client.builder()
                .app_id(settings.feishu_app_id)
                .app_secret(settings.feishu_app_secret)
                .build()
            )

            # 注册事件处理器
            handler = (
                lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(self._do_handle_message)
                .build()
            )

            # 创建并启动 WebSocket 客户端
            ws_client = lark.ws.Client(
                settings.feishu_app_id,
                settings.feishu_app_secret,
                event_handler=handler,
                log_level=lark.LogLevel.DEBUG,
            )

            logger.info("飞书 WebSocket 客户端启动中...")
            ws_client.start()

        except Exception as e:
            logger.exception(f"飞书 WebSocket 客户端错误: {e}")
        finally:
            feishu_loop.close()

    def start(self) -> None:
        """启动飞书客户端（在独立线程中）"""
        if self.thread and self.thread.is_alive():
            logger.warning("Feishu thread already running")
            return
        self.thread = threading.Thread(target=self._run_in_thread, daemon=True, name="FeishuThread")
        self.thread.start()
        logger.info("Feishu thread started")

    def stop(self) -> None:
        """停止飞书客户端"""
        if self.thread and self.thread.is_alive():
            logger.info("Feishu thread is daemon, will stop with main process")

    @classmethod
    def get_instance(cls) -> Optional["FeishuManager"]:
        return cls._instance

    @classmethod
    def create_instance(cls, main_loop: asyncio.AbstractEventLoop) -> "FeishuManager":
        if cls._instance is not None:
            raise RuntimeError("FeishuManager instance already exists")
        cls._instance = cls(main_loop)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
