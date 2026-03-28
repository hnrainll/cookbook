"""Tests for DatabaseManager"""

import asyncio
import os
import tempfile

import pytest

from app.schemas.event import MessageSource, UnifiedMessage


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def db_manager(db_path):
    """Create a fresh DatabaseManager for each test (not singleton)."""
    from app.services.storage.db import DatabaseManager

    DatabaseManager.reset_instance()

    # Directly instantiate without singleton
    mgr = DatabaseManager()
    mgr.db_path = db_path
    return mgr


class TestDatabaseManager:
    def test_start_creates_tables(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            async def check():
                cursor = await db_manager.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in await cursor.fetchall()]
                return tables

            tables = loop.run_until_complete(check())
            assert "messages" in tables
            assert "sink_results" in tables
            assert "auth_tokens" in tables
            assert "auth_requests" in tables

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_save_and_get_message(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="test message",
                message_type="text",
                sender_id="user1",
            )
            result = loop.run_until_complete(db_manager.save_message(msg))
            assert result is True

            count = loop.run_until_complete(db_manager.get_message_count())
            assert count == 1

            messages = loop.run_until_complete(db_manager.get_recent_messages(10))
            assert len(messages) == 1
            assert messages[0]["content"] == "test message"
            assert messages[0]["message_type"] == "text"

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_save_message_with_image_path(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="",
                message_type="image",
                sender_id="user1",
                image_path="data/images/test.jpg",
            )
            result = loop.run_until_complete(db_manager.save_message(msg))
            assert result is True

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_save_sink_result(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            result = loop.run_until_complete(
                db_manager.save_sink_result(
                    event_id="evt1",
                    sink_platform="fanfou",
                    status_id="123",
                    status_url="https://fanfou.com/statuses/123",
                    response_data='{"id":"123"}',
                    success=True,
                )
            )
            assert result is True

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_request_token_crud(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            # Save
            loop.run_until_complete(
                db_manager.save_request_token(
                    oauth_token="req_tok_1",
                    source_platform="feishu",
                    source_user_id="user1",
                    sink_platform="fanfou",
                    token_data='{"oauth_token":"req_tok_1","oauth_token_secret":"secret"}',
                )
            )

            # Get
            record = loop.run_until_complete(db_manager.get_request_token("req_tok_1"))
            assert record is not None
            assert record["source_user_id"] == "user1"

            # Delete
            deleted = loop.run_until_complete(db_manager.delete_request_token("req_tok_1"))
            assert deleted is True

            # Get again
            record = loop.run_until_complete(db_manager.get_request_token("req_tok_1"))
            assert record is None

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_user_token_crud(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            # Save
            loop.run_until_complete(
                db_manager.save_user_token(
                    source_platform="feishu",
                    source_user_id="user1",
                    sink_platform="fanfou",
                    token_data='{"oauth_token":"tok","oauth_token_secret":"sec"}',
                )
            )

            # Get
            token_data = loop.run_until_complete(db_manager.get_any_token_for_sink("fanfou"))
            assert token_data is not None
            assert "tok" in token_data

            # Delete
            deleted = loop.run_until_complete(
                db_manager.delete_user_token("feishu", "user1", "fanfou")
            )
            assert deleted is True

            # Get again
            token_data = loop.run_until_complete(db_manager.get_any_token_for_sink("fanfou"))
            assert token_data is None

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()

    def test_duplicate_message_rejected(self, db_manager):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db_manager.start())

            msg = UnifiedMessage(
                source=MessageSource.FEISHU,
                content="test",
                sender_id="user1",
            )
            assert loop.run_until_complete(db_manager.save_message(msg)) is True
            assert loop.run_until_complete(db_manager.save_message(msg)) is False

            loop.run_until_complete(db_manager.stop())
        finally:
            loop.close()
