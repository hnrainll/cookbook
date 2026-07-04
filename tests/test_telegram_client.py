"""Tests for Telegram source message processing."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from aiogram import types

from app.core.bus import bus
from app.services.platforms.telegram.client import TelegramClient


def _telegram_message(
    *,
    text=None,
    caption=None,
    photo=None,
    message_id=123,
    user_id=456,
    full_name="TG User",
    username="tg_user",
    chat_id=789,
    chat_type="private",
):
    return SimpleNamespace(
        text=text,
        caption=caption,
        photo=photo or [],
        message_id=message_id,
        from_user=SimpleNamespace(id=user_id, full_name=full_name, username=username),
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        date=None,
    )


class TestTelegramClient:
    def setup_method(self):
        bus.clear_handlers()
        TelegramClient.reset_instance()

    def teardown_method(self):
        bus.clear_handlers()
        TelegramClient.reset_instance()

    def test_process_text_message_publishes_unified_message(self):
        loop = asyncio.new_event_loop()
        try:
            client = TelegramClient()
            published = []

            async def capture(message):
                published.append(message)

            bus.register(capture)

            msg = cast(types.Message, _telegram_message(text="hello telegram"))
            loop.run_until_complete(client._process_message(msg))

            assert len(published) == 1
            assert published[0].source == "telegram"
            assert published[0].message_type == "text"
            assert published[0].content == "hello telegram"
            assert published[0].image_data is None
        finally:
            loop.close()

    def test_process_photo_message_publishes_image_message(self):
        loop = asyncio.new_event_loop()
        try:
            client = TelegramClient()
            published = []

            async def capture(message):
                published.append(message)

            bus.register(capture)

            photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")]
            msg = cast(
                types.Message,
                _telegram_message(caption="photo caption", photo=photo, message_id=999),
            )

            with (
                patch.object(
                    client,
                    "_download_photo_bytes",
                    AsyncMock(return_value=b"image-bytes"),
                ) as mock_download,
                patch.object(
                    client,
                    "_save_image",
                    return_value="data/images/999.jpg",
                ) as mock_save,
            ):
                loop.run_until_complete(client._process_message(msg))

            mock_download.assert_awaited_once_with("large")
            mock_save.assert_called_once_with("999", b"image-bytes")
            assert len(published) == 1
            assert published[0].source == "telegram"
            assert published[0].message_type == "image"
            assert published[0].content == "photo caption"
            assert published[0].image_data == b"image-bytes"
            assert published[0].image_path == "data/images/999.jpg"
        finally:
            loop.close()

    def test_process_photo_message_skips_when_download_fails(self):
        loop = asyncio.new_event_loop()
        try:
            client = TelegramClient()
            published = []

            async def capture(message):
                published.append(message)

            bus.register(capture)

            msg = cast(types.Message, _telegram_message(photo=[SimpleNamespace(file_id="large")]))

            with patch.object(
                client,
                "_download_photo_bytes",
                AsyncMock(return_value=None),
            ):
                loop.run_until_complete(client._process_message(msg))

            assert published == []
        finally:
            loop.close()
