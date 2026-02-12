"""Tests for Fanfou client components"""
import asyncio
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.core.auth import AuthService
from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.platforms.fanfou.client import FanfouClient


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
    yield mgr
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
    FanfouClient.reset_instance()
    yield
    AuthService.reset_instance()
    ReplyService.reset_instance()
    FanfouClient.reset_instance()


class TestFanfouClient:

    def test_post_text_no_token(self):
        """No token returns None."""
        client = FanfouClient()
        # Without db_manager / token, should return None
        result = client.post_text("feishu", "user1", "hello")
        assert result is None

    def test_post_photo_no_token(self):
        """No token returns None."""
        client = FanfouClient()
        result = client.post_photo("feishu", "user1", b"fake_image")
        assert result is None

    def test_post_text_with_mock_sdk(self, db_manager):
        """post_text calls SDK correctly."""
        # Save a token
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.save_user_token(
                source_platform="feishu",
                source_user_id="user1",
                sink_platform="fanfou",
                token_data=json.dumps({"oauth_token": "tok", "oauth_token_secret": "sec"}),
            ))

            client = FanfouClient()

            with patch("app.services.platforms.fanfou.client.Fanfou") as MockFanfou:
                mock_ff = MockFanfou.return_value
                mock_ff.post_text.return_value = ({"id": "12345"}, MagicMock())

                result = client.post_text("feishu", "user1", "test post")
                assert result is not None
                assert result["id"] == "12345"
        finally:
            loop.close()

    def test_post_photo_with_mock_sdk(self, db_manager):
        """post_photo calls SDK correctly."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.save_user_token(
                source_platform="feishu",
                source_user_id="user1",
                sink_platform="fanfou",
                token_data=json.dumps({"oauth_token": "tok", "oauth_token_secret": "sec"}),
            ))

            client = FanfouClient()

            with patch("app.services.platforms.fanfou.client.Fanfou") as MockFanfou:
                mock_ff = MockFanfou.return_value
                mock_ff.post_photo.return_value = ({"id": "67890"}, MagicMock())

                result = client.post_photo("feishu", "user1", b"image_data", "caption")
                assert result is not None
                assert result["id"] == "67890"
        finally:
            loop.close()


class TestFanfouHandleMessage:

    def test_handle_command_login_list(self):
        """Handle /login without platform lists available platforms."""
        loop = asyncio.new_event_loop()
        try:
            auth_svc = AuthService.create_instance()
            reply_svc = ReplyService.create_instance()

            replies = []
            reply_svc.register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            from app.core.bus import bus
            bus.clear_handlers()

            client = FanfouClient()

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="/login",
                sender_id="user1",
                command="/login",
                raw_data={"message_id": "mid1"},
            )
            loop.run_until_complete(client.handle_message(msg))

            assert len(replies) == 1
            # No platforms registered, should say "暂无"
            assert "暂无" in replies[0]
        finally:
            bus.clear_handlers()
            loop.close()

    def test_handle_text_no_auth(self):
        """Text message without auth fails gracefully."""
        loop = asyncio.new_event_loop()
        try:
            ReplyService.create_instance()
            replies = []
            ReplyService.get_instance().register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            from app.core.bus import bus
            bus.clear_handlers()

            client = FanfouClient()

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="hello fanfou",
                message_type="text",
                sender_id="user1",
                raw_data={"message_id": "mid1"},
            )
            loop.run_until_complete(client.handle_message(msg))

            # Should report failure since no token
            assert len(replies) == 1
            assert "失败" in replies[0]
        finally:
            bus.clear_handlers()
            loop.close()

    def test_handle_image_no_data(self):
        """Image message without image_data fails."""
        loop = asyncio.new_event_loop()
        try:
            ReplyService.create_instance()
            replies = []
            ReplyService.get_instance().register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            from app.core.bus import bus
            bus.clear_handlers()

            client = FanfouClient()

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="",
                message_type="image",
                sender_id="user1",
                raw_data={"message_id": "mid1"},
            )
            loop.run_until_complete(client.handle_message(msg))

            assert len(replies) == 1
            assert "图片数据为空" in replies[0]
        finally:
            bus.clear_handlers()
            loop.close()
