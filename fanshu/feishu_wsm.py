import sys
import asyncio
import threading
from loguru import logger

import lark_oapi as lark
from fanshu.feishu_bot import feishu_handler, send_message


class LarkWebSocketManager:
    def __init__(self):
        self.ws_thread = None

    def _run_ws_client(self):
        feishu_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(feishu_loop)

        try:
            feishu_ws_module_name = lark.ws.Client.__module__
            logger.info(f"正在修复 {feishu_ws_module_name} 中的全局 loop 变量...")
            
            if feishu_ws_module_name in sys.modules:
                feishu_ws_target_module = sys.modules[feishu_ws_module_name]
                
                if hasattr(feishu_ws_target_module, "loop"):
                    setattr(feishu_ws_target_module, "loop", feishu_loop)
                    logger.info(f"已成功修复 {feishu_ws_module_name} 中的全局 loop 变量")
                else:
                    logger.warning(f"在 {feishu_ws_module_name} 中没找到全局 loop 变量，可能源码版本变了？")

            feishu_app_id = lark.APP_ID
            feishu_app_secret = lark.APP_SECRET
            if feishu_app_id is None or feishu_app_secret is None:
                logger.error("Lark APP_ID 或 APP_SECRET 未配置，无法启动 WebSocket 客户端")
                return

            lark_ws_client = lark.ws.Client(
                feishu_app_id,
                feishu_app_secret,
                event_handler=feishu_handler,
                log_level=lark.LogLevel.DEBUG,
            )
            lark_ws_client.start()
        except Exception as e:
            logger.exception(f"WebSocket客户端错误: {e}")
        finally:
            feishu_loop.close()

    def start(self):
        """启动WebSocket客户端"""
        if self.ws_thread is None or not self.ws_thread.is_alive():
            self.ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
            self.ws_thread.start()

    @staticmethod
    def post_message(open_id: str, message: str):        
        send_message(open_id, message)