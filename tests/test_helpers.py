"""Tests for helpers module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.helpers import (
    CONTENT_TYPE_FILE,
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_NONE,
    CONTENT_TYPE_STICKER,
    PENDING_STICKER_PREFIX,
    ReactionChoice,
    _add_square,
    _add_square_message,
    _get_content_type,
    _get_sticker_info,
    _is_mentioned,
    _is_reply,
    get_sticker_image_url,
    parse_pending_sticker,
    resolve_pending_stickers,
)
from src.types import ChatContext, ChatData, Member, Message

# Backwards compatibility aliases
SquareContext = ChatContext
SquareData = ChatData


@pytest.fixture
def mock_search():
    """Create a mock search instance."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock LINE client."""
    client = MagicMock()
    client.get_square_chat = AsyncMock()
    # Set profile.mid for _is_mentioned checks
    client.base.profile.mid = "bot_mid_123"
    return client


@pytest.fixture
def mock_event():
    """Create a mock Square event."""
    event = MagicMock()
    event.raw = {
        "message": {
            "id": "msg123",
            "from": "user123",
            "to": "chat456",
            "text": "Hello @TestBot",
            "contentType": "NONE",
            "contentMetadata": {},
        }
    }
    event.is_my_message = AsyncMock(return_value=False)
    event.react = AsyncMock()
    event.reply = AsyncMock()
    return event


@pytest.fixture
def context(mock_client, mock_search, mock_event):
    """Create a ChatContext for testing."""
    return ChatContext(
        bot_name="TestBot",
        client=mock_client,
        chats={},
        search=mock_search,
        event=mock_event,
    )


class TestContentType:
    """Tests for _get_content_type function."""

    def test_get_content_type_integer(self):
        """Test getting content type as integer."""
        assert _get_content_type({"contentType": 0}) == CONTENT_TYPE_NONE
        assert _get_content_type({"contentType": 1}) == CONTENT_TYPE_IMAGE
        assert _get_content_type({"contentType": 7}) == CONTENT_TYPE_STICKER
        assert _get_content_type({"contentType": 14}) == CONTENT_TYPE_FILE

    def test_get_content_type_string(self):
        """Test getting content type as string."""
        assert _get_content_type({"contentType": "NONE"}) == CONTENT_TYPE_NONE
        assert _get_content_type({"contentType": "IMAGE"}) == CONTENT_TYPE_IMAGE
        assert _get_content_type({"contentType": "STICKER"}) == CONTENT_TYPE_STICKER
        assert _get_content_type({"contentType": "FILE"}) == CONTENT_TYPE_FILE

    def test_get_content_type_missing(self):
        """Test getting content type when missing."""
        assert _get_content_type({}) == CONTENT_TYPE_NONE


class TestStickerInfo:
    """Tests for _get_sticker_info function."""

    def test_get_sticker_info_with_text(self):
        """Test extracting sticker info with alt text."""
        raw = {
            "contentType": 7,
            "contentMetadata": {
                "STKID": "12345",
                "STKPKGID": "100",
                "STKVER": "1",
                "STKTXT": "開心",
            },
        }
        info = _get_sticker_info(raw)
        assert info is not None
        assert info["id"] == "12345"
        assert info["package_id"] == "100"
        assert info["version"] == "1"
        assert info["text"] == "開心"

    def test_get_sticker_info_without_text(self):
        """Test extracting sticker info without alt text."""
        raw = {
            "contentType": 7,
            "contentMetadata": {
                "STKID": "12345",
                "STKPKGID": "100",
            },
        }
        info = _get_sticker_info(raw)
        assert info is not None
        assert info["id"] == "12345"
        assert info["text"] == ""

    def test_get_sticker_info_not_sticker(self):
        """Test _get_sticker_info returns None for non-sticker."""
        raw = {"contentType": 0}
        assert _get_sticker_info(raw) is None

    def test_get_sticker_info_string_type(self):
        """Test _get_sticker_info with string content type."""
        raw = {
            "contentType": "STICKER",
            "contentMetadata": {
                "STKID": "12345",
                "STKTXT": "可愛",
            },
        }
        info = _get_sticker_info(raw)
        assert info is not None
        assert info["id"] == "12345"
        assert info["text"] == "可愛"


class TestReactionChoice:
    """Tests for ReactionChoice model."""

    def test_valid_reactions(self):
        """Test all valid reaction types."""
        for reaction in ["ALL", "NICE", "LOVE", "FUN", "AMAZING", "SAD", "OMG"]:
            choice = ReactionChoice(reaction=reaction)
            assert choice.reaction == reaction

    def test_invalid_reaction(self):
        """Test invalid reaction raises error."""
        with pytest.raises(ValueError):
            ReactionChoice(reaction="INVALID")


class TestAddSquare:
    """Tests for _add_square function."""

    def test_add_square_creates_new(self, context):
        """Test adding a new Square creates SquareData."""
        assert "chat456" not in context.square
        _add_square(context)
        assert "chat456" in context.square
        assert isinstance(context.square["chat456"], SquareData)

    def test_add_square_does_not_overwrite(self, context):
        """Test adding existing Square does not overwrite."""
        context.square["chat456"] = SquareData(bot_id="existing")
        _add_square(context)
        assert context.square["chat456"].bot_id == "existing"

    def test_add_square_no_event(self, mock_client, mock_search):
        """Test _add_square with no event does nothing."""
        ctx = SquareContext(
            bot_name="TestBot",
            client=mock_client,
            chats={},
            search=mock_search,
            event=None,
        )
        _add_square(ctx)
        assert len(ctx.chats) == 0


class TestStickerUrl:
    """Tests for sticker URL generation."""

    def test_get_sticker_image_url(self):
        """Test sticker URL generation."""
        url = get_sticker_image_url("12345")
        assert "12345" in url
        assert "stickershop.line-scdn.net" in url
        assert ".png" in url


class TestAddSquareMessage:
    """Tests for _add_square_message function."""

    @pytest.mark.asyncio
    async def test_add_message_to_history(self, context):
        """Test adding a message to history."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        _add_square_message(context)

        assert len(context.square["chat456"].messages) == 1
        assert len(context.square["chat456"].history) == 1
        assert "Test User" in context.square["chat456"].messages[0].content
        assert context.square["chat456"].history[0].id == "msg123"

    @pytest.mark.asyncio
    async def test_add_message_strips_bot_mention(self, context):
        """Test bot mention is stripped from message."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        _add_square_message(context)

        # The @TestBot should be stripped
        assert context.square["chat456"].history[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_add_message_no_event(self, mock_client, mock_search):
        """Test _add_square_message with no event does nothing."""
        ctx = SquareContext(
            bot_name="TestBot",
            client=mock_client,
            chats={"chat456": SquareData()},
            search=mock_search,
            event=None,
        )
        _add_square_message(ctx)
        assert len(ctx.chats["chat456"].messages) == 0

    @pytest.mark.asyncio
    async def test_add_sticker_message_creates_pending(self, context):
        """Test adding a sticker message creates pending marker (deferred analysis)."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        # Update event to be a sticker
        context.event.raw["message"]["contentType"] = 7
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["contentMetadata"] = {
            "STKID": "12345",
            "STKTXT": "開心",
        }

        _add_square_message(context)

        assert len(context.square["chat456"].messages) == 1
        # Now creates pending marker instead of calling vision directly
        assert "[傳送了貼圖: PENDING:12345:開心]" in context.square["chat456"].messages[0].content

    @pytest.mark.asyncio
    async def test_add_sticker_message_without_text_creates_pending(self, context):
        """Test adding a sticker message without alt text creates pending marker."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        # Update event to be a sticker without alt text
        context.event.raw["message"]["contentType"] = 7
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["contentMetadata"] = {
            "STKID": "12345",
        }

        _add_square_message(context)

        # Pending marker with empty alt text
        assert "[傳送了貼圖: PENDING:12345:]" in context.square["chat456"].messages[0].content

    @pytest.mark.asyncio
    async def test_add_image_message(self, context):
        """Test adding an image message."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        context.event.raw["message"]["contentType"] = 1
        context.event.raw["message"]["text"] = ""

        _add_square_message(context)

        assert "[傳送了圖片]" in context.square["chat456"].messages[0].content


class TestIsMentioned:
    """Tests for _is_mentioned function."""

    @pytest.mark.asyncio
    async def test_mentioned_by_name(self, context):
        """Test detection of mention by name."""
        context.square["chat456"] = SquareData()  # No bot_id set
        context.event.raw["message"]["contentMetadata"] = {"MENTION": "some data"}
        context.event.raw["message"]["text"] = "Hey @TestBot how are you?"

        assert _is_mentioned(context) is True

    @pytest.mark.asyncio
    async def test_not_mentioned_no_mention_metadata(self, context):
        """Test no mention when MENTION metadata is missing."""
        context.square["chat456"] = SquareData()
        context.event.raw["message"]["contentMetadata"] = {}

        assert _is_mentioned(context) is False

    @pytest.mark.asyncio
    async def test_not_mentioned_no_name(self, context):
        """Test no mention when bot name is not in text."""
        context.square["chat456"] = SquareData()
        context.event.raw["message"]["contentMetadata"] = {"MENTION": "some data"}
        context.event.raw["message"]["text"] = "Hey @OtherBot"

        assert _is_mentioned(context) is False

    @pytest.mark.asyncio
    async def test_mentioned_by_bot_id(self, context):
        """Test detection of mention by bot_id."""
        context.square["chat456"] = SquareData(bot_id="bot789")
        context.event.raw["message"]["contentMetadata"] = {"MENTION": "bot789"}

        assert _is_mentioned(context) is True

    @pytest.mark.asyncio
    async def test_not_mentioned_wrong_bot_id(self, context):
        """Test no mention when bot_id doesn't match."""
        context.square["chat456"] = SquareData(bot_id="bot789")
        context.event.raw["message"]["contentMetadata"] = {"MENTION": "other_bot"}

        assert _is_mentioned(context) is False

    @pytest.mark.asyncio
    async def test_not_mentioned_no_event(self, mock_client, mock_search):
        """Test _is_mentioned with no event returns False."""
        ctx = SquareContext(
            bot_name="TestBot",
            client=mock_client,
            chats={},
            search=mock_search,
            event=None,
        )
        assert _is_mentioned(ctx) is False

    @pytest.mark.asyncio
    async def test_not_mentioned_no_square_data(self, context):
        """Test _is_mentioned with no square data returns False."""
        # square is empty, no data for chat456
        assert _is_mentioned(context) is False


class TestIsReply:
    """Tests for _is_reply function."""

    def test_is_reply_to_bot_message(self, context):
        """Test detection of reply to bot's message."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))
        context.square["chat456"].history.append(Message(id="prev_msg", content="Previous"))
        context.square["chat456"].bot_message_ids.add("prev_msg")

        context.event.raw["message"]["relatedMessageId"] = "prev_msg"

        assert _is_reply(context) is True

    def test_not_reply_no_related_id(self, context):
        """Test not a reply when no relatedMessageId."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        assert _is_reply(context) is False

    def test_not_reply_unknown_member(self, context):
        """Test not a reply when sender is unknown member."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].history.append(Message(id="prev_msg", content="Previous"))
        # No member with id="user123"

        context.event.raw["message"]["relatedMessageId"] = "prev_msg"

        assert _is_reply(context) is False

    def test_not_reply_message_not_in_history(self, context):
        """Test not a reply when related message not in history."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))
        context.square["chat456"].history.append(Message(id="other_msg", content="Other"))

        context.event.raw["message"]["relatedMessageId"] = "prev_msg"

        assert _is_reply(context) is False

    def test_not_reply_no_event(self, mock_client, mock_search):
        """Test _is_reply with no event returns False."""
        ctx = SquareContext(
            bot_name="TestBot",
            client=mock_client,
            chats={},
            search=mock_search,
            event=None,
        )
        assert _is_reply(ctx) is False


class TestStickerReplyLogic:
    """Tests for sticker reply trigger logic.

    Stickers should only trigger bot response when they are replies to bot's messages.
    Mentions should not trigger response for stickers (you can't mention in a sticker).
    """

    @pytest.mark.asyncio
    async def test_sticker_reply_triggers_response(self, context):
        """Test that sticker as reply to bot's message triggers response."""
        # Setup: sticker is a reply to bot's previous message
        context.chats["chat456"] = ChatData()
        context.chats["chat456"].members.append(Member(id="user123", name="Test User"))
        context.chats["chat456"].history.append(Message(id="bot_prev_msg", content="Hello"))
        context.chats["chat456"].bot_message_ids.add("bot_prev_msg")

        # Update event to be a sticker reply
        context.event.raw["message"]["contentType"] = 7  # STICKER
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["relatedMessageId"] = "bot_prev_msg"
        context.event.raw["message"]["contentMetadata"] = {"STKID": "12345"}

        # Verify _is_reply returns True for this sticker
        assert _is_reply(context) is True

    @pytest.mark.asyncio
    async def test_sticker_without_reply_does_not_trigger(self, context):
        """Test that sticker without reply does not trigger response."""
        # Setup: sticker is NOT a reply (no relatedMessageId)
        context.chats["chat456"] = ChatData()
        context.chats["chat456"].members.append(Member(id="user123", name="Test User"))

        # Update event to be a sticker without reply
        context.event.raw["message"]["contentType"] = 7  # STICKER
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["contentMetadata"] = {"STKID": "12345"}
        # No relatedMessageId

        # Verify _is_reply returns False for this sticker
        assert _is_reply(context) is False

    @pytest.mark.asyncio
    async def test_sticker_mention_ignored(self, context):
        """Test that mention check is effectively ignored for stickers.

        Stickers don't have text, so they can't contain bot name mentions.
        Even if MENTION metadata exists, stickers have no text content.
        """
        context.chats["chat456"] = ChatData(bot_id="bot789")

        # Sticker message - no text even if MENTION metadata present
        context.event.raw["message"]["contentType"] = 7  # STICKER
        context.event.raw["message"]["text"] = ""  # Stickers have no text
        context.event.raw["message"]["contentMetadata"] = {
            "STKID": "12345",
            "MENTION": "bot789",  # Even if this exists, it shouldn't matter
        }

        # For stickers, the key behavior is in update_chat_info:
        # Even if _is_mentioned returns True (due to MENTION metadata matching),
        # update_chat_info ignores is_mentioned for stickers and only checks is_reply.
        # Here we just verify the function runs without error.
        _is_mentioned(context)  # May return True due to MENTION metadata, but ignored for stickers


class TestPendingStickerParsing:
    """Tests for pending sticker parsing and resolution."""

    def test_parse_pending_sticker_with_alt_text(self):
        """Test parsing pending sticker marker with alt text."""
        text = "User: [傳送了貼圖: PENDING:12345:開心]"
        result = parse_pending_sticker(text)
        assert result is not None
        assert result == ("12345", "開心")

    def test_parse_pending_sticker_without_alt_text(self):
        """Test parsing pending sticker marker without alt text."""
        text = "User: [傳送了貼圖: PENDING:12345:]"
        result = parse_pending_sticker(text)
        assert result is not None
        assert result == ("12345", "")

    def test_parse_pending_sticker_no_match(self):
        """Test parsing returns None when no pending sticker marker."""
        text = "User: Hello world"
        result = parse_pending_sticker(text)
        assert result is None

    def test_parse_pending_sticker_resolved(self):
        """Test parsing returns None for already resolved sticker."""
        text = "User: [傳送了貼圖: 開心揮手]"
        result = parse_pending_sticker(text)
        assert result is None


class TestResolvePendingStickers:
    """Tests for resolve_pending_stickers function."""

    @pytest.mark.asyncio
    @patch("src.helpers.analyze_sticker_with_vision")
    async def test_resolve_single_pending_sticker(self, mock_vision):
        """Test resolving a single pending sticker."""
        mock_vision.return_value = "開心揮手"

        messages = [
            {"role": "user", "content": "User: [傳送了貼圖: PENDING:12345:開心]"},
        ]

        result = await resolve_pending_stickers(messages)

        assert "[傳送了貼圖: 開心揮手]" in result[0]["content"]
        assert "PENDING:" not in result[0]["content"]
        mock_vision.assert_called_once_with("12345", "開心")

    @pytest.mark.asyncio
    @patch("src.helpers.analyze_sticker_with_vision")
    async def test_resolve_multiple_pending_stickers(self, mock_vision):
        """Test resolving multiple pending stickers in parallel."""
        mock_vision.side_effect = ["開心揮手", "害羞捂臉"]

        messages = [
            {"role": "user", "content": "User1: [傳送了貼圖: PENDING:12345:開心]"},
            {"role": "assistant", "content": "Assistant: 你好!"},
            {"role": "user", "content": "User2: [傳送了貼圖: PENDING:67890:]"},
        ]

        result = await resolve_pending_stickers(messages)

        assert "[傳送了貼圖: 開心揮手]" in result[0]["content"]
        assert "[傳送了貼圖: 害羞捂臉]" in result[2]["content"]
        assert mock_vision.call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_no_pending_stickers(self):
        """Test that messages without pending stickers are unchanged."""
        messages = [
            {"role": "user", "content": "User: Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        result = await resolve_pending_stickers(messages)

        assert result == messages

    @pytest.mark.asyncio
    @patch("src.helpers.analyze_sticker_with_vision")
    async def test_resolve_with_vision_error_fallback(self, mock_vision):
        """Test fallback to alt text when vision analysis fails."""
        mock_vision.side_effect = Exception("Vision API error")

        messages = [
            {"role": "user", "content": "User: [傳送了貼圖: PENDING:12345:開心]"},
        ]

        result = await resolve_pending_stickers(messages)

        # Should fallback to alt text "開心"
        assert "[傳送了貼圖: 開心]" in result[0]["content"]

    @pytest.mark.asyncio
    @patch("src.helpers.analyze_sticker_with_vision")
    async def test_resolve_with_vision_error_no_alt_text(self, mock_vision):
        """Test fallback to default when vision fails and no alt text."""
        mock_vision.side_effect = Exception("Vision API error")

        messages = [
            {"role": "user", "content": "User: [傳送了貼圖: PENDING:12345:]"},
        ]

        result = await resolve_pending_stickers(messages)

        # Should fallback to "貼圖"
        assert "[傳送了貼圖: 貼圖]" in result[0]["content"]


class TestMemberCache:
    """Tests for member caching functionality."""

    def test_chat_data_member_cache_check(self):
        """Test is_member_cached returns False for new chat."""
        chat_data = ChatData()
        assert chat_data.is_member_cached("user123") is False

    def test_chat_data_member_cache_after_add(self):
        """Test is_member_cached returns True after adding member."""
        chat_data = ChatData()
        chat_data.members.append(Member(id="user123", name="Test User"))
        chat_data.update_member_cache_time()

        assert chat_data.is_member_cached("user123") is True
        assert chat_data.is_member_cached("unknown_user") is False

    def test_chat_data_member_cache_expiry(self):
        """Test is_member_cached returns False after cache expires."""
        import time

        chat_data = ChatData()
        chat_data.members.append(Member(id="user123", name="Test User"))
        # Set cache time to old value (expired)
        chat_data._member_cache_time = time.time() - chat_data.MEMBER_CACHE_TTL - 1

        assert chat_data.is_member_cached("user123") is False


class TestDeferredStickerAnalysis:
    """Tests for deferred sticker analysis in _add_chat_message."""

    @pytest.mark.asyncio
    async def test_sticker_creates_pending_marker(self, context):
        """Test that sticker message creates a pending marker instead of calling vision."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        # Update event to be a sticker
        context.event.raw["message"]["contentType"] = 7
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["contentMetadata"] = {
            "STKID": "12345",
            "STKTXT": "開心",
        }

        # This should NOT call analyze_sticker_with_vision
        with patch("src.helpers.analyze_sticker_with_vision") as mock_vision:
            _add_square_message(context)
            mock_vision.assert_not_called()

        # Check that pending marker was created
        assert len(context.square["chat456"].messages) == 1
        assert "PENDING:12345:開心" in context.square["chat456"].messages[0].content

    @pytest.mark.asyncio
    async def test_sticker_pending_marker_format(self, context):
        """Test the format of pending sticker marker."""
        context.square["chat456"] = SquareData()
        context.square["chat456"].members.append(Member(id="user123", name="Test User"))

        context.event.raw["message"]["contentType"] = 7
        context.event.raw["message"]["text"] = ""
        context.event.raw["message"]["contentMetadata"] = {
            "STKID": "99999",
            "STKTXT": "可愛貓咪",
        }

        _add_square_message(context)

        content = context.square["chat456"].messages[0].content
        assert f"[傳送了貼圖: {PENDING_STICKER_PREFIX}99999:可愛貓咪]" in content


class TestMessageDeduplication:
    """Tests for message deduplication in ChatData."""

    def test_is_message_processed_new_chat(self):
        """Test is_message_processed returns False for new chat."""
        chat_data = ChatData()
        assert chat_data.is_message_processed("msg123") is False

    def test_mark_and_check_message_processed(self):
        """Test marking and checking a message as processed."""
        chat_data = ChatData()
        chat_data.mark_message_processed("msg123")
        assert chat_data.is_message_processed("msg123") is True
        assert chat_data.is_message_processed("msg456") is False

    def test_deduplication_isolation_between_chats(self):
        """Test that processed message IDs are isolated per chat."""
        chat1 = ChatData()
        chat2 = ChatData()

        chat1.mark_message_processed("msg123")

        assert chat1.is_message_processed("msg123") is True
        assert chat2.is_message_processed("msg123") is False

    def test_duplicate_processing_prevention(self):
        """Test that marking the same message twice doesn't cause issues."""
        chat_data = ChatData()
        chat_data.mark_message_processed("msg123")
        chat_data.mark_message_processed("msg123")  # Should be idempotent

        assert chat_data.is_message_processed("msg123") is True
        assert len(chat_data._processed_message_ids) == 1

    def test_processed_message_ttl_expiry(self):
        """Test that processed message IDs expire after TTL."""
        import time

        chat_data = ChatData()
        chat_data.PROCESSED_MESSAGE_TTL = 1.0  # Short TTL for testing

        chat_data.mark_message_processed("msg123")
        assert chat_data.is_message_processed("msg123") is True

        # Manually set timestamp to expired
        chat_data._processed_message_ids["msg123"] = time.time() - 2.0

        # Should be expired now
        assert chat_data.is_message_processed("msg123") is False
