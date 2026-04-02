"""
Threads Platform Sink
Threads 平台消费者 - 接收统一消息并发送到 Threads
"""

import json
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Optional
from uuid import uuid4

import httpx
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage
from app.services.platforms.limits import (
    THREADS_TEXT_LIMIT,
    text_too_long_error,
    text_too_long_reply,
)

THREADS_SCOPES = "threads_basic,threads_content_publish"
THREADS_AUTHORIZE_URL = "https://threads.net/oauth/authorize"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ThreadsAuthHandler:
    """Threads OAuth 2.0 认证处理器。"""

    def __init__(self):
        self.app_id = settings.threads_app_id
        self.app_secret = settings.threads_app_secret
        self.redirect_uri = settings.threads_redirect_uri
        self.base_url = settings.threads_base_url.rstrip("/")

    async def gen_auth_url(self, user_id: str) -> str:
        from app.services.storage.db import DatabaseManager

        state = uuid4().hex
        db = DatabaseManager.get_instance()
        if db:
            await db.save_request_token(
                oauth_token=state,
                source_platform="shared",
                source_user_id=user_id,
                sink_platform="threads",
                token_data=json.dumps({"state": state}),
            )

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": THREADS_SCOPES,
            "response_type": "code",
            "state": state,
        }
        return str(httpx.URL(THREADS_AUTHORIZE_URL, params=params))

    async def handle_callback(self, params: dict) -> tuple[str, Optional[str]]:
        state = params.get("state")
        code = params.get("code")
        if not state or not code:
            return "授权失败：缺少 code 或 state", None

        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return "授权失败：数据库未初始化", None

        request_record = await db.get_request_token(state)
        if not request_record:
            return "授权失败：state 不存在或已过期", None

        source_user_id = request_record["source_user_id"]

        short_token = await self.exchange_code_for_short_lived_token(code)
        if not short_token:
            await db.delete_request_token(state)
            return "授权失败：无法获取短期 token", source_user_id

        long_token = await self.exchange_for_long_lived_token(short_token["access_token"])
        if long_token:
            payload = self._normalize_token_payload(long_token)
            result_message = "Threads 授权成功"
        else:
            payload = self._normalize_token_payload(short_token)
            result_message = "Threads 授权成功（使用短期 token，未换取长期 token）"

        await db.save_user_token(
            source_platform="shared",
            source_user_id="shared",
            sink_platform="threads",
            token_data=json.dumps(payload),
        )
        await db.delete_request_token(state)
        return result_message, source_user_id

    async def remove_auth(self, user_id: str) -> bool:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return False
        return await db.delete_any_token_for_sink("threads")

    async def exchange_code_for_short_lived_token(self, code: str) -> Optional[dict]:
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/oauth/access_token", data=params)

        if response.is_success:
            return response.json()

        logger.error(
            "Threads short-lived token exchange failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def exchange_for_long_lived_token(self, access_token: str) -> Optional[dict]:
        params = {
            "grant_type": "th_exchange_token",
            "client_secret": self.app_secret,
        }
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.base_url}/access_token",
                params=params,
                headers=headers,
            )

        if response.is_success:
            return response.json()

        logger.error(
            "Threads long-lived token exchange failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    def _normalize_token_payload(self, token_data: dict) -> dict:
        expires_in = int(token_data.get("expires_in", 0) or 0)
        now = _utc_now()
        payload = {
            "access_token": token_data.get("access_token", ""),
            "token_type": token_data.get("token_type", "bearer"),
            "expires_in": expires_in,
            "expires_at": (now + timedelta(seconds=expires_in)).isoformat() if expires_in else None,
            "refreshed_at": now.isoformat(),
        }
        if "threads_user_id" in token_data:
            payload["threads_user_id"] = token_data["threads_user_id"]
        return payload


class ThreadsClient:
    """Threads 客户端，只处理文本 sink。"""

    _instance: ClassVar[Optional["ThreadsClient"]] = None

    def __init__(self):
        self.base_url = settings.threads_base_url.rstrip("/")
        self.refresh_window_days = settings.threads_refresh_window_days
        logger.info("ThreadsClient initialized")

    async def start(self) -> None:
        logger.info("Threads client started")

    async def stop(self) -> None:
        logger.info("Threads client stopped")

    async def handle_message(self, message: UnifiedMessage) -> None:
        try:
            if message.command:
                return

            if message.message_type == "text":
                await self._handle_text(message)
            elif message.message_type in ("image", "post"):
                logger.debug("Threads: skipping non-text message {}", message.event_id)
            else:
                logger.debug(f"Threads: skipping message type '{message.message_type}'")
        except Exception as e:
            logger.error(f"Threads handle_message error: {e}", exc_info=True)
            raise

    async def _handle_text(self, message: UnifiedMessage) -> None:
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()
        if len(message.content) > THREADS_TEXT_LIMIT.default_limit:
            if reply_service:
                reply_service.reply(message, text_too_long_reply(THREADS_TEXT_LIMIT))
            await self._save_sink_result(
                message,
                None,
                text_too_long_error(THREADS_TEXT_LIMIT),
            )
            return

        ret = await self.post_text(message.content)
        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, self._success_text(ret))
        elif reply_service:
            reply_service.reply(message, "[Threads] 消息发送失败")

    async def post_text(self, text: str) -> Optional[dict]:
        token_payload = await self.get_valid_token()
        if not token_payload:
            return None

        creation_id = await self.create_text_container(text, token_payload["access_token"])
        if not creation_id:
            return None

        publish_response = await self.publish_container(creation_id, token_payload["access_token"])
        if publish_response:
            publish_response.setdefault("creation_id", creation_id)
        return publish_response

    async def create_text_container(self, text: str, access_token: str) -> Optional[str]:
        data = {"media_type": "TEXT", "text": text}
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/me/threads",
                data=data,
                headers=headers,
            )

        if response.is_success:
            payload = response.json()
            return payload.get("id")

        logger.error(
            "Threads create container failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def publish_container(self, creation_id: str, access_token: str) -> Optional[dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/me/threads_publish",
                params={"creation_id": creation_id},
                headers=headers,
            )

        if response.is_success:
            return response.json()

        if self._is_auth_error(response):
            refreshed = await self.refresh_and_get_token()
            if refreshed:
                retry_headers = {"Authorization": f"Bearer {refreshed['access_token']}"}
                async with httpx.AsyncClient(timeout=20) as client:
                    retry_response = await client.post(
                        f"{self.base_url}/me/threads_publish",
                        params={"creation_id": creation_id},
                        headers=retry_headers,
                    )
                if retry_response.is_success:
                    return retry_response.json()
                response = retry_response

        logger.error(
            "Threads publish failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def get_valid_token(self) -> Optional[dict]:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return None

        token_data = await db.get_any_token_for_sink("threads")
        if not token_data:
            return None

        payload = json.loads(token_data)
        refreshed = await self.refresh_access_token_if_needed(payload)
        return refreshed or payload

    async def refresh_access_token_if_needed(self, token_payload: dict) -> Optional[dict]:
        expires_at_raw = token_payload.get("expires_at")
        if not expires_at_raw:
            return token_payload

        expires_at = datetime.fromisoformat(expires_at_raw)
        refresh_time = expires_at - timedelta(days=self.refresh_window_days)
        now = _utc_now()

        if now < refresh_time:
            return token_payload

        refreshed = await self.refresh_access_token(token_payload["access_token"])
        if refreshed:
            return refreshed

        if now < expires_at:
            logger.warning("Threads token refresh failed, using existing token before expiry")
            return token_payload

        return None

    async def refresh_access_token(self, access_token: str) -> Optional[dict]:
        params = {"grant_type": "th_refresh_token"}
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.base_url}/refresh_access_token",
                params=params,
                headers=headers,
            )

        if not response.is_success:
            logger.error(
                "Threads token refresh failed: status_code={} body={}",
                response.status_code,
                response.text,
            )
            return None

        payload = self._normalize_refreshed_token(response.json(), access_token)
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if db:
            await db.save_user_token(
                source_platform="shared",
                source_user_id="shared",
                sink_platform="threads",
                token_data=json.dumps(payload),
            )
        return payload

    async def refresh_and_get_token(self) -> Optional[dict]:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return None

        token_data = await db.get_any_token_for_sink("threads")
        if not token_data:
            return None

        payload = json.loads(token_data)
        access_token = payload.get("access_token")
        if not access_token:
            return None
        return await self.refresh_access_token(access_token)

    def _normalize_refreshed_token(self, token_data: dict, access_token: str) -> dict:
        expires_in = int(token_data.get("expires_in", 0) or 0)
        now = _utc_now()
        return {
            "access_token": token_data.get("access_token") or access_token,
            "token_type": token_data.get("token_type", "bearer"),
            "expires_in": expires_in,
            "expires_at": (now + timedelta(seconds=expires_in)).isoformat() if expires_in else None,
            "refreshed_at": now.isoformat(),
            **(
                {"threads_user_id": token_data["threads_user_id"]}
                if "threads_user_id" in token_data
                else {}
            ),
        }

    def _success_text(self, response_data: dict) -> str:
        post_id = response_data.get("id")
        if post_id:
            return f"[Threads] 消息发送成功\n\nPost ID: {post_id}"
        return "[Threads] 消息发送成功"

    def _is_auth_error(self, response: httpx.Response) -> bool:
        if response.status_code in (401, 403):
            return True

        try:
            payload = response.json()
        except Exception:
            return False

        error = payload.get("error", {})
        if isinstance(error, dict):
            code = error.get("code")
            message = str(error.get("message", "")).lower()
            return code in (190, 102) or "access token" in message
        return False

    async def _save_sink_result(
        self,
        message: UnifiedMessage,
        ret: Optional[dict],
        error_message: str = "发送到 Threads 失败",
    ) -> None:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return

        if ret:
            post_id = str(ret.get("id", ""))
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="threads",
                status_id=post_id,
                status_url=None,
                response_data=json.dumps(ret, ensure_ascii=False),
                success=True,
            )
        else:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="threads",
                success=False,
                error_message=error_message,
            )

    @classmethod
    def get_instance(cls) -> Optional["ThreadsClient"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "ThreadsClient":
        if cls._instance is not None:
            raise RuntimeError("ThreadsClient instance already exists")
        cls._instance = cls()
        bus.register(cls._instance.handle_message)
        logger.info("Threads client registered to event bus")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
