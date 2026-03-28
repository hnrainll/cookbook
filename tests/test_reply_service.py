"""Tests for ReplyService"""

from app.core.reply import ReplyService
from app.schemas.event import MessageSource, UnifiedMessage


class TestReplyService:
    def setup_method(self):
        ReplyService.reset_instance()

    def teardown_method(self):
        ReplyService.reset_instance()

    def test_create_instance(self):
        svc = ReplyService.create_instance()
        assert svc is not None
        assert ReplyService.get_instance() is svc

    def test_register_and_reply(self):
        svc = ReplyService.create_instance()
        replies = []

        def mock_reply(msg, text):
            replies.append((msg.sender_id, text))

        svc.register(MessageSource.FEISHU, reply_handler=mock_reply)

        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="test",
            sender_id="user1",
        )
        svc.reply(msg, "hello")
        assert len(replies) == 1
        assert replies[0] == ("user1", "hello")

    def test_reply_unregistered_source(self):
        svc = ReplyService.create_instance()
        msg = UnifiedMessage(
            source=MessageSource.TELEGRAM,
            content="test",
            sender_id="user1",
        )
        # Should not raise, just log warning
        svc.reply(msg, "hello")

    def test_send(self):
        svc = ReplyService.create_instance()
        sent = []

        def mock_send(user_id, text):
            sent.append((user_id, text))

        svc.register(
            MessageSource.FEISHU,
            reply_handler=lambda m, t: None,
            send_handler=mock_send,
        )
        svc.send(MessageSource.FEISHU, "user1", "hi")
        assert len(sent) == 1
        assert sent[0] == ("user1", "hi")

    def test_send_unregistered_source(self):
        svc = ReplyService.create_instance()
        # Should not raise
        svc.send(MessageSource.TELEGRAM, "user1", "hi")
