"""Integration tests - full message flow through EventBus"""
import asyncio
import json
import os
import tempfile

import pytest

from app.core.auth import AuthService
from app.core.bus import bus
from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.platforms.fanfou.client import FanfouClient
from app.services.storage.db import DatabaseManager


@pytest.fixture(autouse=True)
def reset_all():
    """Reset all singletons and bus handlers."""
    bus.clear_handlers()
    AuthService.reset_instance()
    ReplyService.reset_instance()
    FanfouClient.reset_instance()
    DatabaseManager.reset_instance()
    yield
    bus.clear_handlers()
    AuthService.reset_instance()
    ReplyService.reset_instance()
    FanfouClient.reset_instance()
    DatabaseManager.reset_instance()


@pytest.fixture
def db_manager():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    mgr = DatabaseManager()
    mgr.db_path = path
    loop = asyncio.new_event_loop()
    loop.run_until_complete(mgr.start())
    DatabaseManager._instance = mgr
    bus.register(mgr.handle_message)

    yield mgr

    loop.run_until_complete(mgr.stop())
    loop.close()
    if os.path.exists(path):
        os.unlink(path)


class TestMessageFlow:

    def test_bus_distributes_to_db_sink(self, db_manager):
        """Message published to bus gets saved by DB handler."""
        loop = asyncio.new_event_loop()
        try:
            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="integration test",
                message_type="text",
                sender_id="user1",
            )
            loop.run_until_complete(bus.publish(msg))

            count = loop.run_until_complete(db_manager.get_message_count())
            assert count == 1

            messages = loop.run_until_complete(db_manager.get_recent_messages(10))
            assert messages[0]["content"] == "integration test"
            assert messages[0]["source"] == "feishu"
        finally:
            loop.close()

    def test_bus_distributes_to_multiple_sinks(self, db_manager):
        """Message reaches both DB sink and Fanfou sink."""
        loop = asyncio.new_event_loop()
        try:
            # Set up reply service
            reply_svc = ReplyService.create_instance()
            replies = []
            reply_svc.register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            # Set up Fanfou client (will fail to post since no token, but should handle)
            client = FanfouClient()
            bus.register(client.handle_message)

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="multi-sink test",
                message_type="text",
                sender_id="user1",
                raw_data={"message_id": "mid1"},
            )
            loop.run_until_complete(bus.publish(msg))

            # DB should have the message
            count = loop.run_until_complete(db_manager.get_message_count())
            assert count == 1

            # Fanfou should have replied with failure (no token)
            assert len(replies) >= 1
            assert "失败" in replies[0]
        finally:
            loop.close()

    def test_command_message_not_posted(self, db_manager):
        """Command messages are handled by auth, not posted to fanfou."""
        loop = asyncio.new_event_loop()
        try:
            auth_svc = AuthService.create_instance()
            reply_svc = ReplyService.create_instance()

            replies = []
            reply_svc.register(
                MessageSource.FEISHU,
                reply_handler=lambda m, t: replies.append(t),
            )

            client = FanfouClient()
            bus.register(client.handle_message)

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="/login",
                sender_id="user1",
                command="/login",
                raw_data={"message_id": "mid1"},
            )
            loop.run_until_complete(bus.publish(msg))

            # Should get a reply listing platforms (none registered)
            assert len(replies) >= 1
            assert "暂无" in replies[0] or "可用" in replies[0]

            # DB should still save the message
            count = loop.run_until_complete(db_manager.get_message_count())
            assert count == 1
        finally:
            loop.close()

    def test_image_message_flow(self, db_manager):
        """Image message flows through bus to sinks."""
        loop = asyncio.new_event_loop()
        try:
            reply_svc = ReplyService.create_instance()
            replies = []
            reply_svc.register(
                MessageSource.TELEGRAM,
                reply_handler=lambda m, t: replies.append(t),
            )

            client = FanfouClient()
            bus.register(client.handle_message)

            msg = UnifiedMessage(
                source=MessageSource.TELEGRAM,
                content="photo caption",
                message_type="image",
                sender_id="tg_user1",
                image_data=b"fake_image_bytes",
                image_path="data/images/test.jpg",
                raw_data={"message_id": 123},
            )
            loop.run_until_complete(bus.publish(msg))

            # DB saves message with image_path
            messages = loop.run_until_complete(db_manager.get_recent_messages(10))
            assert len(messages) == 1
            assert messages[0]["message_type"] == "image"

            # Fanfou replies with failure (no token)
            assert len(replies) >= 1
            assert "失败" in replies[0]
        finally:
            loop.close()

    def test_telegram_source_message(self, db_manager):
        """Telegram-sourced messages flow correctly."""
        loop = asyncio.new_event_loop()
        try:
            msg = UnifiedMessage(
                source=MessageSource.TELEGRAM,
                content="from telegram",
                message_type="text",
                sender_id="tg123",
                sender_name="TG User",
                chat_id="chat456",
                raw_data={"message_id": 999},
            )
            loop.run_until_complete(bus.publish(msg))

            messages = loop.run_until_complete(db_manager.get_recent_messages(10))
            assert len(messages) == 1
            assert messages[0]["source"] == "telegram"
            assert messages[0]["sender_name"] == "TG User"
        finally:
            loop.close()
