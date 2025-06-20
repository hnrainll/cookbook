import asyncio
import threading


class LarkWebSocketManager:
    def __init__(self):
        self.ws_thread = None
        self._stop_event = threading.Event()

    @staticmethod
    def _run_ws_client():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from cookbook.feishu_bot import lark_ws_client
            lark_ws_client.start()
        except Exception as e:
            print(f"WebSocket客户端错误: {e}")
        finally:
            loop.close()

    def start(self):
        """启动WebSocket客户端"""
        if self.ws_thread is None or not self.ws_thread.is_alive():
            self.ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
            self.ws_thread.start()

    def stop(self):
        """停止WebSocket客户端"""
        self._stop_event.set()