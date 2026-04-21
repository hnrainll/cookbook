"""Tests for Bluesky client components."""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from app.core.bus import bus
from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.platforms.bluesky.client import (
    BLUESKY_IMAGE_LIMIT_BYTES,
    BlueskyClient,
)


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
    BlueskyClient.reset_instance()
    yield
    bus.clear_handlers()
    ReplyService.reset_instance()
    BlueskyClient.reset_instance()


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


class TestBlueskyClient:
    def test_post_text_retries_transient_upstream_failure(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:test",
                "accessJwt": "jwt",
                "handle": "tester.bsky.social",
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.side_effect = [
                    MockResponse(
                        502,
                        {
                            "error": "UpstreamFailure",
                            "message": "UpstreamFailure",
                        },
                    ),
                    MockResponse(
                        200,
                        {
                            "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                            "cid": "bafy123",
                        },
                    ),
                ]

                result = loop.run_until_complete(client.post_text("hello"))

            assert result is not None
            assert result["cid"] == "bafy123"
            assert client._session is not None
            assert mock_post.call_count == 2
        finally:
            loop.close()

    def test_post_text_keeps_session_on_transient_upstream_failure(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:test",
                "accessJwt": "jwt",
                "handle": "tester.bsky.social",
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.side_effect = [
                    MockResponse(
                        502,
                        {
                            "error": "UpstreamFailure",
                            "message": "UpstreamFailure",
                        },
                    ),
                    MockResponse(
                        502,
                        {
                            "error": "UpstreamFailure",
                            "message": "UpstreamFailure",
                        },
                    ),
                    MockResponse(
                        502,
                        {
                            "error": "UpstreamFailure",
                            "message": "UpstreamFailure",
                        },
                    ),
                ]

                result = loop.run_until_complete(client.post_text("hello"))

            assert result is None
            assert client._session is not None
            assert mock_post.call_count == 3
        finally:
            loop.close()

    def test_start_loads_persisted_session(self, db_manager):
        mgr, loop = db_manager
        loop.run_until_complete(
            mgr.save_user_token(
                source_platform="shared",
                source_user_id="shared",
                sink_platform="bluesky",
                token_data=json.dumps(
                    {
                        "did": "did:plc:test",
                        "accessJwt": "persisted-access",
                        "refreshJwt": "persisted-refresh",
                        "handle": "tester.bsky.social",
                    }
                ),
            )
        )

        client = BlueskyClient()
        loop.run_until_complete(client.start())

        assert client._session is not None
        assert client._session["accessJwt"] == "persisted-access"
        assert client._session["refreshJwt"] == "persisted-refresh"

    def test_get_session_uses_refresh_jwt_before_create_session(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:test",
                "accessJwt": "",
                "refreshJwt": "refresh-jwt",
                "handle": "tester.bsky.social",
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.return_value = MockResponse(
                    200,
                    {
                        "did": "did:plc:new",
                        "accessJwt": "fresh-jwt",
                        "refreshJwt": "fresh-refresh-jwt",
                        "handle": "tester.bsky.social",
                    },
                )

                result = loop.run_until_complete(client._get_session())

            assert result is not None
            assert result["accessJwt"] == "fresh-jwt"
            assert mock_post.call_count == 1
            assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer refresh-jwt"
            assert mock_post.call_args.args[0].endswith("/xrpc/com.atproto.server.refreshSession")
        finally:
            loop.close()

    def test_create_session_persists_session(self, db_manager):
        mgr, loop = db_manager
        client = BlueskyClient()
        client.identifier = "tester.bsky.social"
        client.app_password = "app-password"

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MockResponse(
                200,
                {
                    "did": "did:plc:new",
                    "accessJwt": "fresh-jwt",
                    "refreshJwt": "fresh-refresh-jwt",
                    "handle": "tester.bsky.social",
                },
            )

            result = loop.run_until_complete(client._create_session())

        assert result is not None
        token_data = loop.run_until_complete(mgr.get_any_token_for_sink("bluesky"))
        assert token_data is not None
        payload = json.loads(token_data)
        assert payload["accessJwt"] == "fresh-jwt"
        assert payload["refreshJwt"] == "fresh-refresh-jwt"

    def test_get_session_falls_back_to_create_session_when_refresh_fails(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client.identifier = "tester.bsky.social"
            client.app_password = "app-password"
            client._session = {
                "did": "did:plc:test",
                "accessJwt": "",
                "refreshJwt": "expired-refresh-jwt",
                "handle": "tester.bsky.social",
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.side_effect = [
                    MockResponse(
                        401,
                        {"error": "ExpiredToken", "message": "Token has expired"},
                    ),
                    MockResponse(
                        200,
                        {
                            "did": "did:plc:new",
                            "accessJwt": "fresh-jwt",
                            "refreshJwt": "fresh-refresh-jwt",
                            "handle": "tester.bsky.social",
                        },
                    ),
                ]

                result = loop.run_until_complete(client._get_session())

            assert result is not None
            assert result["accessJwt"] == "fresh-jwt"
            assert mock_post.call_count == 2
            assert (
                mock_post.call_args_list[0]
                .args[0]
                .endswith("/xrpc/com.atproto.server.refreshSession")
            )
            assert mock_post.call_args_list[0].kwargs["headers"]["Authorization"] == (
                "Bearer expired-refresh-jwt"
            )
            assert (
                mock_post.call_args_list[1]
                .args[0]
                .endswith("/xrpc/com.atproto.server.createSession")
            )
            assert mock_post.call_args_list[1].kwargs["json"] == {
                "identifier": "tester.bsky.social",
                "password": "app-password",
            }
        finally:
            loop.close()

    def test_refresh_session_persists_session(self, db_manager):
        mgr, loop = db_manager
        client = BlueskyClient()

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MockResponse(
                200,
                {
                    "did": "did:plc:new",
                    "accessJwt": "fresh-jwt",
                    "refreshJwt": "fresh-refresh-jwt",
                    "handle": "tester.bsky.social",
                },
            )

            result = loop.run_until_complete(client._refresh_session("refresh-jwt"))

        assert result is not None
        token_data = loop.run_until_complete(mgr.get_any_token_for_sink("bluesky"))
        assert token_data is not None
        payload = json.loads(token_data)
        assert payload["accessJwt"] == "fresh-jwt"
        assert payload["refreshJwt"] == "fresh-refresh-jwt"

    def test_post_text_refreshes_expired_token(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:old",
                "accessJwt": "expired-jwt",
                "refreshJwt": "refresh-jwt",
                "handle": "tester.bsky.social",
            }

            with (
                patch.object(
                    client,
                    "_refresh_or_create_session",
                    AsyncMock(
                        return_value={
                            "did": "did:plc:new",
                            "accessJwt": "fresh-jwt",
                            "refreshJwt": "fresh-refresh-jwt",
                            "handle": "tester.bsky.social",
                        }
                    ),
                ) as mock_refresh_or_create,
                patch("httpx.AsyncClient.post") as mock_post,
            ):
                mock_post.side_effect = [
                    MockResponse(
                        400,
                        {
                            "error": "ExpiredToken",
                            "message": "Token has expired",
                        },
                    ),
                    MockResponse(
                        200,
                        {
                            "uri": "at://did:plc:new/app.bsky.feed.post/abc123",
                            "cid": "bafy123",
                        },
                    ),
                ]

                result = loop.run_until_complete(client.post_text("hello"))

            assert result is not None
            assert result["cid"] == "bafy123"
            assert mock_refresh_or_create.await_count == 1
            assert (
                mock_post.call_args_list[0].kwargs["headers"]["Authorization"]
                == "Bearer expired-jwt"
            )
            assert (
                mock_post.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer fresh-jwt"
            )
        finally:
            loop.close()

    def test_post_text_no_credentials(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client.identifier = ""
            client.app_password = ""
            result = loop.run_until_complete(client.post_text("hello"))
            assert result is None
        finally:
            loop.close()

    def test_post_text_success(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:test",
                "accessJwt": "jwt",
                "handle": "tester.bsky.social",
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.return_value = MockResponse(
                    200,
                    {
                        "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                        "cid": "bafy123",
                    },
                )

                result = loop.run_until_complete(client.post_text("hello"))

            assert result is not None
            assert result["cid"] == "bafy123"
        finally:
            loop.close()

    def test_success_text_prefers_web_url(self):
        client = BlueskyClient()
        client._session = {"handle": "tester.bsky.social"}

        text = client._success_text(
            {
                "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                "cid": "bafy123",
            }
        )

        assert (
            text
            == "[Bluesky] 消息发送成功\n\nhttps://bsky.app/profile/tester.bsky.social/post/abc123"
        )

    def test_post_image_too_large(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            payload = b"x" * (BLUESKY_IMAGE_LIMIT_BYTES + 1)
            result = loop.run_until_complete(client.post_image(payload, "caption"))
            assert result is None
        finally:
            loop.close()

    def test_post_image_compresses_large_image_before_upload(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            session = {
                "did": "did:plc:test",
                "accessJwt": "jwt",
                "handle": "tester.bsky.social",
            }
            client._session = session
            payload = b"x" * (BLUESKY_IMAGE_LIMIT_BYTES + 1)
            compressed = b"compressed-image"

            with (
                patch(
                    "app.services.platforms.bluesky.client.compress_image_advanced",
                    return_value=compressed,
                ) as mock_compress,
                patch.object(
                    client,
                    "_upload_blob",
                    AsyncMock(return_value=({"ref": {"$link": "blob"}}, session)),
                ) as mock_upload_blob,
                patch.object(
                    client,
                    "_create_record",
                    AsyncMock(
                        return_value={
                            "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                            "cid": "bafy123",
                        }
                    ),
                ),
            ):
                result = loop.run_until_complete(client.post_image(payload, "caption"))

            assert result is not None
            assert result["cid"] == "bafy123"
            mock_compress.assert_called_once()
            assert mock_upload_blob.await_args is not None
            assert mock_upload_blob.await_args.args[0] == compressed
        finally:
            loop.close()

    def test_post_image_refreshes_expired_token_during_upload(self):
        loop = asyncio.new_event_loop()
        try:
            client = BlueskyClient()
            client._session = {
                "did": "did:plc:old",
                "accessJwt": "expired-jwt",
                "refreshJwt": "refresh-jwt",
                "handle": "tester.bsky.social",
            }

            with (
                patch.object(
                    client,
                    "_refresh_or_create_session",
                    AsyncMock(
                        return_value={
                            "did": "did:plc:new",
                            "accessJwt": "fresh-jwt",
                            "refreshJwt": "fresh-refresh-jwt",
                            "handle": "tester.bsky.social",
                        }
                    ),
                ) as mock_refresh_or_create,
                patch("httpx.AsyncClient.post") as mock_post,
            ):
                mock_post.side_effect = [
                    MockResponse(
                        400,
                        {
                            "error": "ExpiredToken",
                            "message": "Token has expired",
                        },
                    ),
                    MockResponse(
                        200,
                        {
                            "blob": {
                                "$type": "blob",
                                "ref": {"$link": "bafkrei123"},
                                "mimeType": "image/jpeg",
                                "size": 123,
                            }
                        },
                    ),
                    MockResponse(
                        200,
                        {
                            "uri": "at://did:plc:new/app.bsky.feed.post/abc123",
                            "cid": "bafy123",
                        },
                    ),
                ]

                result = loop.run_until_complete(client.post_image(b"image-bytes", "caption"))

            assert result is not None
            assert result["cid"] == "bafy123"
            assert mock_refresh_or_create.await_count == 1
            assert (
                mock_post.call_args_list[0].kwargs["headers"]["Authorization"]
                == "Bearer expired-jwt"
            )
            assert (
                mock_post.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer fresh-jwt"
            )
            assert (
                mock_post.call_args_list[2].kwargs["headers"]["Authorization"] == "Bearer fresh-jwt"
            )
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

        client = BlueskyClient()
        client._session = {"handle": "tester.bsky.social"}

        with patch.object(
            client,
            "post_text",
            AsyncMock(
                return_value={
                    "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
                    "cid": "bafy123",
                }
            ),
        ):
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="hello bluesky",
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

        assert replies == [
            "[Bluesky] 消息发送成功\n\nhttps://bsky.app/profile/tester.bsky.social/post/abc123"
        ]

        async def fetch_row():
            assert mgr.conn is not None
            cursor = await mgr.conn.execute(
                "SELECT sink_platform, status_id, success FROM sink_results WHERE event_id = ?",
                (str(msg.event_id),),
            )
            return await cursor.fetchone()

        row = loop.run_until_complete(fetch_row())
        assert row == ("bluesky", "bafy123", 1)

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

            client = BlueskyClient()
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="",
                message_type="image",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

            assert replies == ["[Bluesky] 图片数据为空，无法发送。"]
        finally:
            loop.close()

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

        client = BlueskyClient()
        with patch.object(client, "post_text", AsyncMock()) as mock_post_text:
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="x" * 301,
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(client.handle_message(msg))

        mock_post_text.assert_not_called()
        assert replies == ["[Bluesky] 消息长度超过 300 字，无法发送"]
