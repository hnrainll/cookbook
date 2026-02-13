"""Tests for UnifiedMessage schema"""
from app.schemas.event import MessageSource, UnifiedMessage


class TestUnifiedMessage:

    def test_default_values(self):
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="hello",
            sender_id="user1",
        )
        assert msg.message_type == "text"
        assert msg.image_data is None
        assert msg.image_key is None
        assert msg.image_path is None
        assert msg.command is None
        assert msg.event_id is not None
        assert msg.timestamp is not None

    def test_all_fields(self):
        msg = UnifiedMessage(
            source=MessageSource.TELEGRAM,
            content="photo caption",
            message_type="image",
            sender_id="user2",
            sender_name="Test User",
            chat_id="chat1",
            image_data=b"fake_image",
            image_key="img_key",
            image_path="data/images/test.jpg",
            command=None,
            raw_data={"key": "value"},
        )
        assert msg.message_type == "image"
        assert msg.image_data == b"fake_image"
        assert msg.image_key == "img_key"
        assert msg.image_path == "data/images/test.jpg"

    def test_command_message(self):
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="/login fanfou",
            sender_id="user1",
            command="/login fanfou",
        )
        assert msg.command == "/login fanfou"

    def test_json_serialization_excludes_image_data(self):
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="test",
            sender_id="user1",
            image_data=b"binary_data",
        )
        json_data = msg.model_dump_json()
        assert "binary_data" not in json_data

    def test_str_representation(self):
        msg = UnifiedMessage(
            source=MessageSource.FEISHU,
            content="hello world",
            sender_id="user1",
            message_type="text",
        )
        s = str(msg)
        assert "text" in s
        assert "user1" in s
