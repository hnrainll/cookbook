"""Tests for Mastodon client components."""

import asyncio
import os
import tempfile
from unittest.mock import patch

import pytest

from app.core.bus import bus
from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.platforms.mastodon.client import MastodonClient


@pytest.fixture
def db_manager():
    """Create a fresh DatabaseManager for each test."""
    from app.services.storage.db import DatabaseManager

    DatabaseManager.reset_instance()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    mgr = DatabaseManager()
    mgr.db_path = path
    loop = asyncio.new_event_loop()
    loop.run_until_complete(mgr.start())
    DatabaseManager._instance = mgr
    yield mgr, loop
    loop.run_until_complete(mgr.stop())
    loop.close()
    DatabaseManager.reset_instance()
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before/after each test."""
    bus.clear_handlers()
    ReplyService.reset_instance()
    MastodonClient.reset_instance()
    yield
    bus.clear_handlers()
    ReplyService.reset_instance()
    MastodonClient.reset_instance()


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


class TestMastodonClient:
    def test_post_text_no_token(self):
        loop = asyncio.new_event_loop()
        try:
            client = MastodonClient()
            client.access_token = ""
            result = loop.run_until_complete(client.post_text("hello"))
            assert result is None
        finally:
            loop.close()

    def test_post_text_success(self):
        loop = asyncio.new_event_loop()
        try:
            client = MastodonClient()
            client.access_token = "token"

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.return_value = MockResponse(
                    200,
                    {"id": "123", "url": "https://mastodon.social/@user/123"},
                )

                result = loop.run_until_complete(client.post_text("hello"))
                assert result is not None
                assert result["id"] == "123"
        finally:
            loop.close()

    def test_handle_text_success(self, db_manager):
        mgr, loop = db_manager
        ReplyService.create_instance()
        replies = []
        reply_service = ReplyService.get_instance()
        assert reply_service is not None
        reply_service.register(
            MessageSource.FEISHU,
            reply_handler=lambda m, t: replies.append(t),
        )

        client = MastodonClient()
        client.access_token = "token"

        with patch.object(
            client,
            "post_text",
            return_value={"id": "123", "url": "https://mastodon.social/@user/123"},
        ):
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="hello mastodon",
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

        assert replies == ["[Mastodon] 消息发送成功\n\nhttps://mastodon.social/@user/123"]

        async def fetch_row():
            assert mgr.conn is not None
            cursor = await mgr.conn.execute(
                "SELECT sink_platform, status_id, success FROM sink_results WHERE event_id = ?",
                (str(msg.event_id),),
            )
            return await cursor.fetchone()

        row = loop.run_until_complete(fetch_row())
        assert row == ("mastodon", "123", 1)

    def test_handle_image_missing_data(self):
        loop = asyncio.new_event_loop()
        try:
            ReplyService.create_instance()
            replies = []
            reply_service = ReplyService.get_instance()
            assert reply_service is not None
            reply_service.register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            client = MastodonClient()
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="",
                message_type="image",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

            assert replies == ["[Mastodon] 图片数据为空，无法发送。"]
        finally:
            loop.close()
