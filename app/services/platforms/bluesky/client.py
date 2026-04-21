"""
Bluesky Platform Sink
Bluesky 平台消费者 - 接收统一消息并发送到 Bluesky
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, ClassVar, Optional, TypeVar

import httpx
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage
from app.services.platforms.limits import (
    BLUESKY_TEXT_LIMIT,
    caption_too_long_error,
    caption_too_long_reply,
    text_too_long_error,
    text_too_long_reply,
)
from app.utils.image import compress_image_advanced

BLUESKY_POST_COLLECTION = "app.bsky.feed.post"
BLUESKY_IMAGE_LIMIT_BYTES = 1_000_000
BLUESKY_SHARED_SOURCE_PLATFORM = "shared"
BLUESKY_SHARED_SOURCE_USER_ID = "shared"
T = TypeVar("T")
R = TypeVar("R")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_at_uri(uri: str) -> Optional[tuple[str, str, str]]:
    if not uri.startswith("at://"):
        return None

    parts = uri.removeprefix("at://").split("/")
    if len(parts) != 3:
        return None

    return parts[0], parts[1], parts[2]


def _is_expired_token_response(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False

    try:
        body = response.json()
    except ValueError:
        return False

    return body.get("error") == "ExpiredToken"


def _is_transient_upstream_response(response: httpx.Response) -> bool:
    if response.status_code not in (502, 503, 504):
        return False

    try:
        body = response.json()
    except ValueError:
        return True

    error = body.get("error")
    return error in ("UpstreamFailure", "InternalServerError", None)


class BlueskyClient:
    """Bluesky 客户端，支持文本和单图消息。"""

    _instance: ClassVar[Optional["BlueskyClient"]] = None

    def __init__(self):
        self.service_url = settings.bluesky_service_url.rstrip("/")
        self.identifier = settings.bluesky_identifier
        self.app_password = settings.bluesky_app_password
        self._session: Optional[dict[str, Any]] = None
        logger.info("BlueskyClient initialized")

    async def start(self) -> None:
        await self._load_session_from_db()
        logger.info("Bluesky client started")

    async def stop(self) -> None:
        self._session = None
        logger.info("Bluesky client stopped")

    async def handle_message(self, message: UnifiedMessage) -> None:
        try:
            if message.command:
                return

            if message.message_type == "text":
                await self._handle_text(message)
            elif message.message_type in ("image", "post"):
                await self._handle_image(message)
            else:
                logger.debug(f"Bluesky: skipping message type '{message.message_type}'")
        except Exception as e:
            logger.error(f"Bluesky handle_message error: {e}", exc_info=True)
            raise

    async def _handle_text(self, message: UnifiedMessage) -> None:
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()
        if len(message.content) > BLUESKY_TEXT_LIMIT.default_limit:
            if reply_service:
                reply_service.reply(message, text_too_long_reply(BLUESKY_TEXT_LIMIT))
            await self._save_sink_result(
                message,
                None,
                text_too_long_error(BLUESKY_TEXT_LIMIT),
            )
            return

        ret = await self.post_text(message.content)
        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, self._success_text(ret))
        elif reply_service:
            reply_service.reply(message, "[Bluesky] 消息发送失败")

    async def _handle_image(self, message: UnifiedMessage) -> None:
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()

        if not message.image_data:
            if reply_service:
                reply_service.reply(message, "[Bluesky] 图片数据为空，无法发送。")
            return

        if message.content and len(message.content) > BLUESKY_TEXT_LIMIT.default_limit:
            if reply_service:
                reply_service.reply(message, caption_too_long_reply(BLUESKY_TEXT_LIMIT))
            await self._save_sink_result(
                message,
                None,
                caption_too_long_error(BLUESKY_TEXT_LIMIT),
            )
            return

        ret = await self.post_image(message.image_data, message.content or None)
        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, self._success_text(ret))
        elif reply_service:
            reply_service.reply(message, "[Bluesky] 图片发送失败")

    async def post_text(self, text: str) -> Optional[dict]:
        session = await self._get_session()
        if not session:
            return None

        record = {
            "$type": BLUESKY_POST_COLLECTION,
            "text": text,
            "createdAt": _utc_now_iso(),
        }
        return await self._create_record(record, session)

    async def post_image(self, image_data: bytes, text: Optional[str] = None) -> Optional[dict]:
        upload_image_data = self._fit_image_for_upload(image_data)
        if not upload_image_data:
            return None

        session = await self._get_session()
        if not session:
            return None

        blob, uploaded_session = await self._upload_blob(upload_image_data, session)
        if not blob or not uploaded_session:
            return None

        record = {
            "$type": BLUESKY_POST_COLLECTION,
            "text": text or "",
            "createdAt": _utc_now_iso(),
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [
                    {
                        "alt": text or "image",
                        "image": blob,
                    }
                ],
            },
        }
        return await self._create_record(record, uploaded_session)

    def _fit_image_for_upload(self, image_data: bytes) -> Optional[bytes]:
        if len(image_data) <= BLUESKY_IMAGE_LIMIT_BYTES:
            return image_data

        try:
            compressed = compress_image_advanced(
                image_data,
                target_size_mb=BLUESKY_IMAGE_LIMIT_BYTES / 1024 / 1024,
            )
        except Exception as e:
            logger.error(
                "Bluesky image compression failed: original_size={} error={}",
                len(image_data),
                e,
            )
            return None

        if len(compressed) > BLUESKY_IMAGE_LIMIT_BYTES:
            logger.error(
                "Bluesky image too large after compression: {} bytes, max {} bytes",
                len(compressed),
                BLUESKY_IMAGE_LIMIT_BYTES,
            )
            return None

        logger.info(
            "Bluesky image compressed: {} bytes -> {} bytes",
            len(image_data),
            len(compressed),
        )
        return compressed

    async def _get_session(self) -> Optional[dict[str, Any]]:
        if self._session and self._session.get("accessJwt") and self._session.get("did"):
            return self._session

        await self._load_session_from_db()
        if self._session and self._session.get("accessJwt") and self._session.get("did"):
            return self._session

        return await self._refresh_or_create_session()

    async def _refresh_or_create_session(self) -> Optional[dict[str, Any]]:
        refresh_jwt = None
        if self._session:
            refresh_jwt = self._session.get("refreshJwt")

        if refresh_jwt:
            session = await self._refresh_session(refresh_jwt)
            if session:
                return session

        self._session = None
        return await self._create_session()

    async def _create_session(self) -> Optional[dict[str, Any]]:
        if not self.identifier or not self.app_password:
            return None

        payload = {
            "identifier": self.identifier,
            "password": self.app_password,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.service_url}/xrpc/com.atproto.server.createSession",
                json=payload,
            )

        if response.is_success:
            session_payload = response.json()
            if not isinstance(session_payload, dict):
                logger.error("Bluesky createSession returned invalid payload type")
                return None
            self._session = session_payload
            await self._save_session_to_db(session_payload)
            return session_payload

        logger.error(
            "Bluesky createSession failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def _refresh_session(self, refresh_jwt: str) -> Optional[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {refresh_jwt}"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.service_url}/xrpc/com.atproto.server.refreshSession",
                headers=headers,
            )

        if response.is_success:
            session_payload = response.json()
            if not isinstance(session_payload, dict):
                logger.error("Bluesky refreshSession returned invalid payload type")
                return None
            self._session = session_payload
            await self._save_session_to_db(session_payload)
            return session_payload

        logger.error(
            "Bluesky refreshSession failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def _create_record(
        self, record: dict[str, Any], session: dict[str, Any]
    ) -> Optional[dict]:
        payload = {
            "repo": session["did"],
            "collection": BLUESKY_POST_COLLECTION,
            "record": record,
        }

        async def request(current_session: dict[str, Any]) -> httpx.Response:
            return await self._post_with_session(
                "/xrpc/com.atproto.repo.createRecord",
                current_session,
                json=payload,
            )

        async def on_session_refresh(refreshed_session: dict[str, Any]) -> None:
            payload["repo"] = refreshed_session["did"]

        return await self._execute_with_session_retry(
            operation_name="createRecord",
            session=session,
            request=request,
            extract_success=lambda response, _session: response.json(),
            on_session_refresh=on_session_refresh,
            failure_result=None,
        )

    async def _upload_blob(
        self, image_data: bytes, session: dict[str, Any]
    ) -> tuple[Optional[dict], Optional[dict[str, Any]]]:
        async def request(current_session: dict[str, Any]) -> httpx.Response:
            return await self._post_with_session(
                "/xrpc/com.atproto.repo.uploadBlob",
                current_session,
                content=image_data,
                content_type="image/jpeg",
                timeout=30,
            )

        return await self._execute_with_session_retry(
            operation_name="uploadBlob",
            session=session,
            request=request,
            extract_success=lambda response, current_session: (
                response.json().get("blob"),
                current_session,
            ),
            failure_result=(None, None),
        )

    async def _execute_with_session_retry(
        self,
        *,
        operation_name: str,
        session: dict[str, Any],
        request: Callable[[dict[str, Any]], Awaitable[httpx.Response]],
        extract_success: Callable[[httpx.Response, dict[str, Any]], R],
        failure_result: R,
        on_session_refresh: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    ) -> R:
        current_session: dict[str, Any] = session
        for attempt in range(3):
            response = await request(current_session)

            if response.is_success:
                return extract_success(response, current_session)

            if attempt == 0 and _is_expired_token_response(response):
                refreshed_session = await self._refresh_or_create_session()
                if refreshed_session:
                    current_session = refreshed_session
                    if on_session_refresh:
                        await on_session_refresh(current_session)
                    continue

            if attempt < 2 and _is_transient_upstream_response(response):
                logger.warning(
                    "Bluesky {} transient failure: status_code={} body={} retry={}",
                    operation_name,
                    response.status_code,
                    response.text,
                    attempt + 1,
                )
                await asyncio.sleep(0.5 * (attempt + 1))
                continue

            logger.error(
                "Bluesky {} failed: status_code={} body={}",
                operation_name,
                response.status_code,
                response.text,
            )
            if _is_expired_token_response(response):
                self._session = None
            return failure_result

        return failure_result

    async def _post_with_session(
        self,
        path: str,
        session: dict[str, Any],
        *,
        json: Optional[dict[str, Any]] = None,
        content: Optional[bytes] = None,
        content_type: Optional[str] = None,
        timeout: int = 20,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {session['accessJwt']}"}
        if content_type:
            headers["Content-Type"] = content_type

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(
                f"{self.service_url}{path}",
                json=json,
                content=content,
                headers=headers,
            )

    async def _load_session_from_db(self) -> Optional[dict[str, Any]]:
        if self._session:
            return self._session

        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return None

        token_data = await db.get_any_token_for_sink("bluesky")
        if not token_data:
            return None

        try:
            payload = json.loads(token_data)
        except json.JSONDecodeError:
            logger.error("Bluesky persisted session is invalid JSON")
            return None

        if not isinstance(payload, dict):
            logger.error("Bluesky persisted session has invalid payload type")
            return None

        self._session = payload
        return self._session

    async def _save_session_to_db(self, session: dict[str, Any]) -> None:
        if not session:
            return

        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return

        await db.save_user_token(
            source_platform=BLUESKY_SHARED_SOURCE_PLATFORM,
            source_user_id=BLUESKY_SHARED_SOURCE_USER_ID,
            sink_platform="bluesky",
            token_data=json.dumps(session, ensure_ascii=False),
        )

    def _success_text(self, response_data: dict[str, Any]) -> str:
        web_url = self._web_post_url(response_data)
        if web_url:
            return f"[Bluesky] 消息发送成功\n\n{web_url}"

        uri = response_data.get("uri")
        if uri:
            return f"[Bluesky] 消息发送成功\n\n{uri}"
        return "[Bluesky] 消息发送成功"

    def _web_post_url(self, response_data: dict[str, Any]) -> Optional[str]:
        uri = response_data.get("uri")
        if not uri:
            return None

        parsed = _parse_at_uri(uri)
        if not parsed:
            return None

        _repo, collection, record_key = parsed
        if collection != BLUESKY_POST_COLLECTION:
            return None

        handle = None
        if self._session:
            handle = self._session.get("handle")

        if not handle:
            return None

        return f"https://bsky.app/profile/{handle}/post/{record_key}"

    async def _save_sink_result(
        self,
        message: UnifiedMessage,
        ret: Optional[dict],
        error_message: str = "发送到 Bluesky 失败",
    ) -> None:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return

        if ret:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="bluesky",
                status_id=str(ret.get("cid", "")),
                status_url=ret.get("uri"),
                response_data=json.dumps(ret, ensure_ascii=False),
                success=True,
            )
        else:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="bluesky",
                success=False,
                error_message=error_message,
            )

    @classmethod
    def get_instance(cls) -> Optional["BlueskyClient"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "BlueskyClient":
        if cls._instance is not None:
            raise RuntimeError("BlueskyClient instance already exists")
        cls._instance = cls()
        bus.register(cls._instance.handle_message)
        logger.info("Bluesky client registered to event bus")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
