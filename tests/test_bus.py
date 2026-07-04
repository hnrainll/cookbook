"""Tests for EventBus logging semantics."""

import asyncio
import os
import tempfile

import pytest
from loguru import logger

from app.core.bus import bus
from app.schemas.event import MessageSource, UnifiedMessage
from app.services.storage.db import DatabaseManager


async def _ok_handler(message: UnifiedMessage) -> None:
    return None


async def _failing_handler(message: UnifiedMessage) -> None:
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def reset_singletons():
    bus.clear_handlers()
    DatabaseManager.reset_instance()
    yield
    bus.clear_handlers()
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
    try:
        yield mgr, loop
    finally:
        loop.run_until_complete(mgr.stop())
        loop.close()
        DatabaseManager.reset_instance()
        if os.path.exists(path):
            os.unlink(path)


def test_publish_logs_handler_completion_not_sink_success():
    bus.register(_ok_handler)

    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}")
    loop = asyncio.new_event_loop()
    try:
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="bus log test",
            message_type="text",
            sender_id="user1",
        )

        loop.run_until_complete(bus.publish(msg))

        assert any(
            f"Message {msg.event_id} distributed to 1 handlers: 1 completed, 0 raised exceptions"
            in entry
            for entry in messages
        )
    finally:
        logger.remove(sink_id)
        loop.close()


def test_publish_logs_handler_exceptions():
    bus.register(_ok_handler)
    bus.register(_failing_handler)

    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}")
    loop = asyncio.new_event_loop()
    try:
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="bus error log test",
            message_type="text",
            sender_id="user1",
        )

        loop.run_until_complete(bus.publish(msg))

        assert any(
            f"Message {msg.event_id} distributed to 2 handlers: 1 completed, 1 raised exceptions"
            in entry
            for entry in messages
        )
    finally:
        logger.remove(sink_id)
        loop.close()


def test_publish_logs_final_sink_result_summary(db_manager):
    _mgr, loop = db_manager

    class FanfouClient:
        async def handle_message(self, message: UnifiedMessage) -> None:
            db = DatabaseManager.get_instance()
            assert db is not None
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="fanfou",
                success=True,
            )

    class ThreadsClient:
        async def handle_message(self, message: UnifiedMessage) -> None:
            db = DatabaseManager.get_instance()
            assert db is not None
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="threads",
                success=False,
                error_message="need reauth",
            )

    bus.register(FanfouClient().handle_message)
    bus.register(ThreadsClient().handle_message)

    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="sink summary test",
            message_type="text",
            sender_id="user1",
        )

        loop.run_until_complete(bus.publish(msg))

        assert any(
            f"Message {msg.event_id} sink results: 1 succeeded, 1 failed, 0 missing" in entry
            for entry in messages
        )
        assert any(f"Message {msg.event_id} failed sinks: threads" in entry for entry in messages)
    finally:
        logger.remove(sink_id)


def test_publish_logs_missing_sink_results(db_manager):
    _mgr, loop = db_manager

    class FanfouClient:
        async def handle_message(self, message: UnifiedMessage) -> None:
            db = DatabaseManager.get_instance()
            assert db is not None
            await db.save_sink_result(
                event_id=str(message.event_id),
                sink_platform="fanfou",
                success=True,
            )

    class ThreadsClient:
        async def handle_message(self, message: UnifiedMessage) -> None:
            return None

    bus.register(FanfouClient().handle_message)
    bus.register(ThreadsClient().handle_message)

    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="missing sink result test",
            message_type="text",
            sender_id="user1",
        )

        loop.run_until_complete(bus.publish(msg))

        assert any(
            f"Message {msg.event_id} sink results: 1 succeeded, 0 failed, 1 missing" in entry
            for entry in messages
        )
        assert any(
            f"Message {msg.event_id} sinks without persisted result: threads" in entry
            for entry in messages
        )
    finally:
        logger.remove(sink_id)
