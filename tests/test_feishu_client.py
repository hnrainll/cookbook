"""Tests for Feishu client components"""

from app.services.platforms.feishu.client import OrderedDictDeduplicator


class TestOrderedDictDeduplicator:
    def test_new_message(self):
        dedup = OrderedDictDeduplicator(max_size=10)
        assert dedup.add("msg1") is True
        assert dedup.exists("msg1") is True

    def test_duplicate_rejected(self):
        dedup = OrderedDictDeduplicator(max_size=10)
        assert dedup.add("msg1") is True
        assert dedup.add("msg1") is False

    def test_max_size_eviction(self):
        dedup = OrderedDictDeduplicator(max_size=3)
        dedup.add("msg1")
        dedup.add("msg2")
        dedup.add("msg3")
        # Adding msg4 should evict msg1
        dedup.add("msg4")
        assert dedup.exists("msg1") is False
        assert dedup.exists("msg2") is True
        assert dedup.exists("msg4") is True

    def test_exists_unknown(self):
        dedup = OrderedDictDeduplicator()
        assert dedup.exists("nonexistent") is False
