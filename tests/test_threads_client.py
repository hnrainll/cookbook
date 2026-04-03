"""Tests for Threads client components."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.auth import AuthService
from app.core.bus import bus
from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.platforms.threads.client import ThreadsAuthHandler, ThreadsClient


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
    AuthService.reset_instance()
    ReplyService.reset_instance()
    ThreadsClient.reset_instance()
    bus.clear_handlers()
    yield
    AuthService.reset_instance()
    ReplyService.reset_instance()
    ThreadsClient.reset_instance()
    bus.clear_handlers()


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


class TestThreadsAuthHandler:
    def test_exchange_for_long_lived_token_uses_access_token_param(self):
        loop = asyncio.new_event_loop()
        try:
            handler = ThreadsAuthHandler()
            handler.app_secret = "secret123"

            with patch("httpx.AsyncClient.get") as mock_get:
                mock_get.return_value = MockResponse(
                    200,
                    {
                        "access_token": "long",
                        "token_type": "bearer",
                        "expires_in": 5184000,
                    },
                )

                result = loop.run_until_complete(handler.exchange_for_long_lived_token("short123"))

            assert result is not None
            assert mock_get.call_args.kwargs["params"] == {
                "grant_type": "th_exchange_token",
                "client_secret": "secret123",
                "access_token": "short123",
            }
        finally:
            loop.close()

    def test_gen_auth_url_saves_state(self, db_manager):
        mgr, loop = db_manager
        handler = ThreadsAuthHandler()
        handler.app_id = "app123"
        handler.redirect_uri = "http://127.0.0.1:8009/auth?platform=threads"

        url = loop.run_until_complete(handler.gen_auth_url("user1"))
        assert "client_id=app123" in url
        assert "response_type=code" in url
        assert "state=" in url

        state = url.split("state=")[1].split("&")[0]
        record = loop.run_until_complete(mgr.get_request_token(state))
        assert record is not None
        assert record["sink_platform"] == "threads"
        assert record["source_user_id"] == "user1"

    def test_handle_callback_exchanges_and_saves_long_lived_token(self, db_manager):
        mgr, loop = db_manager
        handler = ThreadsAuthHandler()

        state = "state123"
        loop.run_until_complete(
            mgr.save_request_token(
                oauth_token=state,
                source_platform="shared",
                source_user_id="user1",
                sink_platform="threads",
                token_data=json.dumps({"state": state}),
            )
        )

        with (
            patch.object(
                handler,
                "exchange_code_for_short_lived_token",
                AsyncMock(return_value={"access_token": "short"}),
            ),
            patch.object(
                handler,
                "exchange_for_long_lived_token",
                AsyncMock(
                    return_value={
                        "access_token": "long",
                        "token_type": "bearer",
                        "expires_in": 5184000,
                    }
                ),
            ),
        ):
            message, user_id = loop.run_until_complete(
                handler.handle_callback({"state": state, "code": "code123"})
            )

        assert message == "Threads 授权成功"
        assert user_id == "user1"

        token_data = loop.run_until_complete(mgr.get_any_token_for_sink("threads"))
        assert token_data is not None
        payload = json.loads(token_data)
        assert payload["access_token"] == "long"
        assert payload["expires_in"] == 5184000
        assert payload["expires_at"] is not None

    def test_remove_auth_deletes_shared_token(self, db_manager):
        mgr, loop = db_manager
        handler = ThreadsAuthHandler()

        loop.run_until_complete(
            mgr.save_user_token(
                source_platform="shared",
                source_user_id="shared",
                sink_platform="threads",
                token_data=json.dumps({"access_token": "long"}),
            )
        )

        result = loop.run_until_complete(handler.remove_auth("user1"))
        assert result is True
        assert loop.run_until_complete(mgr.get_any_token_for_sink("threads")) is None

    def test_handle_callback_falls_back_to_short_lived_token(self, db_manager):
        mgr, loop = db_manager
        handler = ThreadsAuthHandler()

        state = "state123"
        loop.run_until_complete(
            mgr.save_request_token(
                oauth_token=state,
                source_platform="shared",
                source_user_id="user1",
                sink_platform="threads",
                token_data=json.dumps({"state": state}),
            )
        )

        with (
            patch.object(
                handler,
                "exchange_code_for_short_lived_token",
                AsyncMock(
                    return_value={
                        "access_token": "short",
                        "token_type": "bearer",
                        "expires_in": 3600,
                    }
                ),
            ),
            patch.object(
                handler,
                "exchange_for_long_lived_token",
                AsyncMock(return_value=None),
            ),
        ):
            message, user_id = loop.run_until_complete(
                handler.handle_callback({"state": state, "code": "code123"})
            )

        assert message == "Threads 授权成功（使用短期 token，未换取长期 token）"
        assert user_id == "user1"

        token_data = loop.run_until_complete(mgr.get_any_token_for_sink("threads"))
        assert token_data is not None
        payload = json.loads(token_data)
        assert payload["access_token"] == "short"
        assert payload["expires_in"] == 3600
        assert payload["expires_at"] is not None


class TestThreadsClient:
    def test_post_text_fetches_permalink_when_available(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()

            with (
                patch.object(
                    client,
                    "get_valid_token",
                    AsyncMock(return_value={"access_token": "token"}),
                ),
                patch.object(
                    client,
                    "create_text_container",
                    AsyncMock(return_value="container123"),
                ),
                patch.object(
                    client,
                    "publish_container",
                    AsyncMock(return_value={"id": "post123"}),
                ),
                patch.object(
                    client,
                    "get_post_permalink",
                    AsyncMock(return_value="https://www.threads.com/@user/post/abc"),
                ),
            ):
                result = loop.run_until_complete(client.post_text("hello"))

            assert result == {
                "id": "post123",
                "creation_id": "container123",
                "permalink": "https://www.threads.com/@user/post/abc",
            }
        finally:
            loop.close()

    def test_post_text_keeps_success_when_permalink_fetch_fails(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()

            with (
                patch.object(
                    client,
                    "get_valid_token",
                    AsyncMock(return_value={"access_token": "token"}),
                ),
                patch.object(
                    client,
                    "create_text_container",
                    AsyncMock(return_value="container123"),
                ),
                patch.object(
                    client,
                    "publish_container",
                    AsyncMock(return_value={"id": "post123"}),
                ),
                patch.object(
                    client,
                    "get_post_permalink",
                    AsyncMock(return_value=None),
                ),
            ):
                result = loop.run_until_complete(client.post_text("hello"))

            assert result == {
                "id": "post123",
                "creation_id": "container123",
            }
        finally:
            loop.close()

    def test_refresh_access_token_uses_access_token_param(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()

            with patch("httpx.AsyncClient.get") as mock_get:
                mock_get.return_value = MockResponse(
                    200,
                    {
                        "access_token": "refreshed",
                        "token_type": "bearer",
                        "expires_in": 5184000,
                    },
                )

                result = loop.run_until_complete(client.refresh_access_token("long123"))

            assert result is not None
            assert mock_get.call_args.kwargs["params"] == {
                "grant_type": "th_refresh_token",
                "access_token": "long123",
            }
        finally:
            loop.close()

    def test_post_text_no_token(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()
            result = loop.run_until_complete(client.post_text("hello"))
            assert result is None
        finally:
            loop.close()

    def test_refresh_access_token_if_needed_returns_existing_token_when_fresh(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()
            fresh_payload = {
                "access_token": "token",
                "expires_at": (_utc_now() + timedelta(days=30)).isoformat(),
            }
            result = loop.run_until_complete(client.refresh_access_token_if_needed(fresh_payload))
            assert result == fresh_payload
        finally:
            loop.close()

    def test_refresh_access_token_if_needed_refreshes_expiring_token(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()
            expiring_payload = {
                "access_token": "token",
                "expires_at": (_utc_now() + timedelta(days=1)).isoformat(),
            }

            with patch.object(
                client,
                "refresh_access_token",
                AsyncMock(return_value={"access_token": "new-token"}),
            ):
                result = loop.run_until_complete(
                    client.refresh_access_token_if_needed(expiring_payload)
                )
            assert result == {"access_token": "new-token"}
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

        client = ThreadsClient()

        with patch.object(
            client,
            "post_text",
            AsyncMock(return_value={"id": "post123", "creation_id": "container123"}),
        ):
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="hello threads",
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

        assert replies == ["[Threads] 消息发送成功\n\nPost ID: post123"]

        async def fetch_row():
            assert mgr.conn is not None
            cursor = await mgr.conn.execute(
                "SELECT sink_platform, status_id, success FROM sink_results WHERE event_id = ?",
                (str(msg.event_id),),
            )
            return await cursor.fetchone()

        row = loop.run_until_complete(fetch_row())
        assert row == ("threads", "post123", 1)

    def test_success_text_prefers_permalink(self):
        client = ThreadsClient()

        text = client._success_text(
            {
                "id": "post123",
                "permalink": "https://www.threads.com/@user/post/abc",
            }
        )

        assert text == "[Threads] 消息发送成功\n\nhttps://www.threads.com/@user/post/abc"

    def test_handle_image_is_skipped(self, db_manager):
        _mgr, loop = db_manager
        ReplyService.create_instance()
        replies = []
        reply_service = ReplyService.get_instance()
        assert reply_service is not None
        reply_service.register(
            MessageSource.FEISHU,
            reply_handler=lambda m, t: replies.append(t),
        )

        client = ThreadsClient()
        with patch.object(client, "post_text", AsyncMock()) as mock_post_text:
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="caption",
                message_type="image",
                sender_id="user1",
                image_data=b"fake",
            )
            loop.run_until_complete(client.handle_message(msg))

        mock_post_text.assert_not_called()
        assert replies == []

    def test_handle_text_too_long(self, db_manager):
        _mgr, loop = db_manager
        ReplyService.create_instance()
        replies = []
        reply_service = ReplyService.get_instance()
        assert reply_service is not None
        reply_service.register(
            MessageSource.FEISHU,
            reply_handler=lambda m, t: replies.append(t),
        )

        client = ThreadsClient()
        with patch.object(client, "post_text", AsyncMock()) as mock_post_text:
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="x" * 501,
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

        mock_post_text.assert_not_called()
        assert replies == ["[Threads] 消息长度超过 500 字，无法发送"]

    def test_publish_container_refreshes_on_auth_error(self):
        loop = asyncio.new_event_loop()
        try:
            client = ThreadsClient()
            first_response = MockResponse(
                401,
                {"error": {"code": 190, "message": "Invalid OAuth access token."}},
            )
            second_response = MockResponse(200, {"id": "post456"})

            with (
                patch("httpx.AsyncClient.post", side_effect=[first_response, second_response]),
                patch.object(
                    client,
                    "refresh_and_get_token",
                    AsyncMock(return_value={"access_token": "new-token"}),
                ),
            ):
                result = loop.run_until_complete(client.publish_container("container", "token"))

            assert result == {"id": "post456"}
        finally:
            loop.close()


def _utc_now() -> datetime:
    return datetime.now(UTC)
