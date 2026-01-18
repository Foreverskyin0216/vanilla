"""Tests for types module."""

from src.types import Member, Message, Square, SquareData


def test_message_dataclass():
    """Test Message dataclass."""
    msg = Message(id="msg123", content="Hello world")
    assert msg.id == "msg123"
    assert msg.content == "Hello world"


def test_member_dataclass():
    """Test Member dataclass."""
    member = Member(id="user123", name="Test User")
    assert member.id == "user123"
    assert member.name == "Test User"


def test_square_data_defaults():
    """Test SquareData dataclass with defaults."""
    data = SquareData()
    assert data.bot_id == ""
    assert data.messages == []
    assert data.members == []
    assert data.history == []


def test_square_data_with_values():
    """Test SquareData dataclass with values."""
    member = Member(id="user1", name="User One")
    msg = Message(id="msg1", content="Test")

    data = SquareData(
        bot_id="bot123",
        messages=[],
        members=[member],
        history=[msg],
    )

    assert data.bot_id == "bot123"
    assert len(data.members) == 1
    assert data.members[0].name == "User One"
    assert len(data.history) == 1
    assert data.history[0].content == "Test"


def test_square_type_alias():
    """Test Square type alias (dict)."""
    square: Square = {}
    square["chat123"] = SquareData(bot_id="bot1")
    assert "chat123" in square
    assert square["chat123"].bot_id == "bot1"


class TestChatDataMemberCache:
    """Tests for ChatData member caching functionality."""

    def test_member_cache_default_values(self):
        """Test default cache values in ChatData."""
        data = SquareData()
        assert data._member_cache_time == 0.0
        assert data.MEMBER_CACHE_TTL == 300.0

    def test_is_member_cached_empty(self):
        """Test is_member_cached returns False for empty chat."""
        data = SquareData()
        assert data.is_member_cached("user123") is False

    def test_is_member_cached_after_update(self):
        """Test is_member_cached returns True after cache update."""
        data = SquareData()
        data.members.append(Member(id="user123", name="Test User"))
        data.update_member_cache_time()

        assert data.is_member_cached("user123") is True
        assert data.is_member_cached("other_user") is False

    def test_is_member_cached_expired(self):
        """Test is_member_cached returns False when cache expired."""
        import time

        data = SquareData()
        data.members.append(Member(id="user123", name="Test User"))
        # Set cache time to expired value
        data._member_cache_time = time.time() - data.MEMBER_CACHE_TTL - 10

        # Even though member exists, cache is expired
        assert data.is_member_cached("user123") is False

    def test_update_member_cache_time(self):
        """Test update_member_cache_time updates timestamp."""
        import time

        data = SquareData()
        assert data._member_cache_time == 0.0

        before = time.time()
        data.update_member_cache_time()
        after = time.time()

        assert before <= data._member_cache_time <= after

    def test_member_cache_ttl_configurable(self):
        """Test that MEMBER_CACHE_TTL is a class attribute."""
        data = SquareData()
        original_ttl = data.MEMBER_CACHE_TTL

        # Can be changed per instance if needed
        data.MEMBER_CACHE_TTL = 600.0
        assert data.MEMBER_CACHE_TTL == 600.0

        # Reset
        data.MEMBER_CACHE_TTL = original_ttl


class TestChatDataMessageDeduplication:
    """Tests for ChatData message deduplication functionality."""

    def test_processed_message_ids_default(self):
        """Test default processed_message_ids is empty."""
        data = SquareData()
        assert data._processed_message_ids == {}

    def test_is_message_processed_empty(self):
        """Test is_message_processed returns False for new chat."""
        data = SquareData()
        assert data.is_message_processed("msg123") is False

    def test_mark_message_processed(self):
        """Test marking a message as processed."""
        data = SquareData()
        data.mark_message_processed("msg123")
        assert data.is_message_processed("msg123") is True
        assert data.is_message_processed("msg456") is False

    def test_multiple_messages_processed(self):
        """Test marking multiple messages as processed."""
        data = SquareData()
        data.mark_message_processed("msg1")
        data.mark_message_processed("msg2")
        data.mark_message_processed("msg3")

        assert data.is_message_processed("msg1") is True
        assert data.is_message_processed("msg2") is True
        assert data.is_message_processed("msg3") is True
        assert data.is_message_processed("msg4") is False

    def test_duplicate_mark_is_idempotent(self):
        """Test that marking the same message twice is idempotent."""
        data = SquareData()
        data.mark_message_processed("msg123")
        data.mark_message_processed("msg123")  # Should not error

        assert data.is_message_processed("msg123") is True
        assert len(data._processed_message_ids) == 1

    def test_processed_message_ttl_expiry(self):
        """Test that processed message IDs expire after TTL."""
        import time

        data = SquareData()
        data.PROCESSED_MESSAGE_TTL = 1.0  # Short TTL for testing

        data.mark_message_processed("msg123")
        assert data.is_message_processed("msg123") is True

        # Manually set timestamp to expired
        data._processed_message_ids["msg123"] = time.time() - 2.0

        # Should be expired now
        assert data.is_message_processed("msg123") is False
        # Should be removed from dict
        assert "msg123" not in data._processed_message_ids

    def test_cleanup_expired_message_ids(self):
        """Test cleanup of expired message IDs."""
        import time

        data = SquareData()
        data.PROCESSED_MESSAGE_TTL = 1.0

        # Add some messages with old timestamps
        old_time = time.time() - 10.0
        data._processed_message_ids["old1"] = old_time
        data._processed_message_ids["old2"] = old_time
        data._processed_message_ids["new1"] = time.time()

        data._cleanup_expired_message_ids()

        assert "old1" not in data._processed_message_ids
        assert "old2" not in data._processed_message_ids
        assert "new1" in data._processed_message_ids

    def test_isolation_between_chats(self):
        """Test that processed IDs are isolated per ChatData instance."""
        chat1 = SquareData()
        chat2 = SquareData()

        chat1.mark_message_processed("msg123")

        assert chat1.is_message_processed("msg123") is True
        assert chat2.is_message_processed("msg123") is False

    def test_default_ttl_value(self):
        """Test default TTL is 30 seconds."""
        data = SquareData()
        assert data.PROCESSED_MESSAGE_TTL == 30.0
