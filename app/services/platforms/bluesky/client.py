"""
Bluesky Platform Sink
Bluesky 平台消费者 - 接收统一消息并发送到 Bluesky
"""

import json
from datetime import UTC, datetime
from typing import Any, ClassVar, Optional

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

BLUESKY_POST_COLLECTION = "app.bsky.feed.post"
BLUESKY_IMAGE_LIMIT_BYTES = 1_000_000


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_at_uri(uri: str) -> Optional[tuple[str, str, str]]:
    if not uri.startswith("at://"):
        return None

    parts = uri.removeprefix("at://").split("/")
    if len(parts) != 3:
        return None

    return parts[0], parts[1], parts[2]


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
        if len(image_data) > BLUESKY_IMAGE_LIMIT_BYTES:
            logger.error(
                "Bluesky image too large: {} bytes, max {} bytes",
                len(image_data),
                BLUESKY_IMAGE_LIMIT_BYTES,
            )
            return None

        session = await self._get_session()
        if not session:
            return None

        blob = await self._upload_blob(image_data, session["accessJwt"])
        if not blob:
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
        return await self._create_record(record, session)

    async def _get_session(self) -> Optional[dict[str, Any]]:
        if self._session and self._session.get("accessJwt") and self._session.get("did"):
            return self._session

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
            self._session = response.json()
            return self._session

        logger.error(
            "Bluesky createSession failed: status_code={} body={}",
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
        headers = {"Authorization": f"Bearer {session['accessJwt']}"}

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.service_url}/xrpc/com.atproto.repo.createRecord",
                json=payload,
                headers=headers,
            )

        if response.is_success:
            return response.json()

        logger.error(
            "Bluesky createRecord failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        self._session = None
        return None

    async def _upload_blob(self, image_data: bytes, access_jwt: str) -> Optional[dict]:
        headers = {
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": "image/jpeg",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.service_url}/xrpc/com.atproto.repo.uploadBlob",
                content=image_data,
                headers=headers,
            )

        if response.is_success:
            return response.json().get("blob")

        logger.error(
            "Bluesky uploadBlob failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        self._session = None
        return None

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
