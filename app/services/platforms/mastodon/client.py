"""
Mastodon Platform Sink
Mastodon 平台消费者 - 接收统一消息并发送到 Mastodon
"""

import json
from typing import ClassVar, Optional

import httpx
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage
from app.services.platforms.limits import (
    MASTODON_TEXT_LIMIT,
    caption_too_long_error,
    caption_too_long_reply,
    text_too_long_error,
    text_too_long_reply,
)


class MastodonClient:
    """Mastodon 客户端，使用 Access Token 直接发布文本和图片。"""

    _instance: ClassVar[Optional["MastodonClient"]] = None

    def __init__(self):
        self.base_url = settings.mastodon_base_url.rstrip("/")
        self.access_token = settings.mastodon_access_token
        self.visibility = settings.mastodon_visibility
        self._max_characters: Optional[int] = None
        logger.info("MastodonClient initialized")

    async def start(self) -> None:
        await self.get_max_characters()
        logger.info("Mastodon client started")

    async def stop(self) -> None:
        logger.info("Mastodon client stopped")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
        }

    async def get_max_characters(self) -> int:
        if self._max_characters is not None:
            return self._max_characters

        self._max_characters = await self._fetch_max_characters()
        return self._max_characters

    async def _fetch_max_characters(self) -> int:
        endpoints = ("/api/v2/instance", "/api/v1/instance")

        async with httpx.AsyncClient(timeout=20) as client:
            for endpoint in endpoints:
                try:
                    response = await client.get(f"{self.base_url}{endpoint}")
                except Exception as e:
                    logger.warning("Mastodon instance metadata request failed: {}", e)
                    continue

                if not response.is_success:
                    logger.warning(
                        "Mastodon instance metadata fetch failed: status_code={} endpoint={}",
                        response.status_code,
                        endpoint,
                    )
                    continue

                max_characters = self._extract_max_characters(response.json())
                if max_characters:
                    return max_characters

        return MASTODON_TEXT_LIMIT.default_limit

    def _extract_max_characters(self, payload: dict) -> Optional[int]:
        configuration = payload.get("configuration")
        if not isinstance(configuration, dict):
            return None

        statuses = configuration.get("statuses")
        if not isinstance(statuses, dict):
            return None

        max_characters = statuses.get("max_characters")
        if isinstance(max_characters, int) and max_characters > 0:
            return max_characters
        return None

    async def post_text(self, text: str) -> Optional[dict]:
        """发布纯文本状态。"""
        if not self.access_token:
            return None

        data = {
            "status": text,
            "visibility": self.visibility,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/statuses",
                headers=self._headers(),
                data=data,
            )

        if response.is_success:
            return response.json()

        logger.error(
            "Mastodon text post failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def post_image(
        self,
        image_data: bytes,
        text: Optional[str] = None,
    ) -> Optional[dict]:
        """上传图片并发布带图状态。"""
        if not self.access_token:
            return None

        media = await self._upload_media(image_data)
        if not media:
            return None

        data: list[tuple[str, str]] = [
            ("visibility", self.visibility),
            ("media_ids[]", str(media["id"])),
        ]
        if text:
            data.append(("status", text))

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/statuses",
                headers=self._headers(),
                data=data,
            )

        if response.is_success:
            return response.json()

        logger.error(
            "Mastodon image post failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def _upload_media(self, image_data: bytes) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/api/v2/media",
                headers=self._headers(),
                files={"file": ("image.jpg", image_data, "image/jpeg")},
            )

        if response.is_success:
            return response.json()

        logger.error(
            "Mastodon media upload failed: status_code={} body={}",
            response.status_code,
            response.text,
        )
        return None

    async def handle_message(self, message: UnifiedMessage) -> None:
        """事件总线回调：转发文本和图片消息到 Mastodon。"""
        try:
            if message.command:
                return

            if message.message_type == "text":
                await self._handle_text(message)
            elif message.message_type in ("image", "post"):
                await self._handle_image(message)
            else:
                logger.debug(f"Mastodon: skipping message type '{message.message_type}'")
        except Exception as e:
            logger.error(f"Mastodon handle_message error: {e}", exc_info=True)
            raise

    async def _handle_text(self, message: UnifiedMessage) -> None:
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()
        max_characters = await self.get_max_characters()
        if len(message.content) > max_characters:
            if reply_service:
                reply_service.reply(
                    message,
                    text_too_long_reply(MASTODON_TEXT_LIMIT, max_characters),
                )
            await self._save_sink_result(
                message,
                None,
                text_too_long_error(MASTODON_TEXT_LIMIT, max_characters),
            )
            return

        ret = await self.post_text(message.content)
        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, self._success_text(ret))
        elif reply_service:
            reply_service.reply(message, "[Mastodon] 消息发送失败")

    async def _handle_image(self, message: UnifiedMessage) -> None:
        from app.core.reply import ReplyService

        reply_service = ReplyService.get_instance()
        if not message.image_data:
            if reply_service:
                reply_service.reply(message, "[Mastodon] 图片数据为空，无法发送。")
            return

        if message.content:
            max_characters = await self.get_max_characters()
            if len(message.content) > max_characters:
                if reply_service:
                    reply_service.reply(
                        message,
                        caption_too_long_reply(MASTODON_TEXT_LIMIT, max_characters),
                    )
                await self._save_sink_result(
                    message,
                    None,
                    caption_too_long_error(MASTODON_TEXT_LIMIT, max_characters),
                )
                return

        ret = await self.post_image(message.image_data, message.content or None)
        await self._save_sink_result(message, ret)

        if reply_service and ret:
            reply_service.reply(message, self._success_text(ret))
        elif reply_service:
            reply_service.reply(message, "[Mastodon] 图片发送失败")

    def _success_text(self, response_data: dict) -> str:
        url = response_data.get("url") or response_data.get("uri")
        if url:
            return f"[Mastodon] 消息发送成功\n\n{url}"
        return "[Mastodon] 消息发送成功"

    async def _save_sink_result(
        self,
        message: UnifiedMessage,
        ret: Optional[dict],
        error_message: str = "发送到 Mastodon 失败",
    ) -> None:
        from app.services.storage.db import DatabaseManager

        db = DatabaseManager.get_instance()
        if not db:
            return

        if ret:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="mastodon",
                status_id=str(ret.get("id", "")),
                status_url=ret.get("url") or ret.get("uri"),
                response_data=json.dumps(ret, ensure_ascii=False),
                success=True,
            )
        else:
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="mastodon",
                success=False,
                error_message=error_message,
            )

    @classmethod
    def get_instance(cls) -> Optional["MastodonClient"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "MastodonClient":
        if cls._instance is not None:
            raise RuntimeError("MastodonClient instance already exists")
        cls._instance = cls()
        bus.register(cls._instance.handle_message)
        logger.info("Mastodon client registered to event bus")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
