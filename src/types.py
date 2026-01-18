"""Type definitions for Vanilla chatbot."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Union

from langchain_core.messages import BaseMessage

from src.linepy import Client, SquareMessage, TalkMessage

if TYPE_CHECKING:
    from src.preferences import UserPreferencesStore
    from src.scheduler import Scheduler
    from src.search import Search


@dataclass
class Message:
    """A message with ID and content."""

    id: str
    content: str


@dataclass
class Member:
    """A chat member with ID and name."""

    id: str
    name: str


@dataclass
class ChatData:
    """Data for a chat (Square or Talk)."""

    bot_id: str = ""
    messages: list[BaseMessage] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    history: list[Message] = field(default_factory=list)
    # Set of message IDs sent by the bot (for reply detection)
    bot_message_ids: set[str] = field(default_factory=set)
    # Member cache timestamp (Unix time)
    _member_cache_time: float = 0.0
    # Dict of processed message IDs to timestamps for TTL-based expiry
    # Format: {message_id: timestamp}
    _processed_message_ids: dict[str, float] = field(default_factory=dict)

    # Cache TTL in seconds (5 minutes)
    MEMBER_CACHE_TTL: float = 300.0
    # TTL for processed message IDs in seconds (30 seconds)
    # Duplicate messages from LINE server typically arrive within a few seconds
    PROCESSED_MESSAGE_TTL: float = 30.0

    def is_member_cached(self, member_id: str) -> bool:
        """Check if a member is in the cache and not expired."""
        import time

        if time.time() - self._member_cache_time > self.MEMBER_CACHE_TTL:
            return False
        return any(m.id == member_id for m in self.members)

    def update_member_cache_time(self) -> None:
        """Update the member cache timestamp."""
        import time

        self._member_cache_time = time.time()

    def is_message_processed(self, message_id: str) -> bool:
        """Check if a message has already been processed (within TTL)."""
        import time

        if message_id not in self._processed_message_ids:
            return False

        # Check if entry has expired
        timestamp = self._processed_message_ids[message_id]
        if time.time() - timestamp > self.PROCESSED_MESSAGE_TTL:
            # Expired, remove it
            del self._processed_message_ids[message_id]
            return False

        return True

    def mark_message_processed(self, message_id: str) -> None:
        """Mark a message as processed to prevent duplicate handling."""
        import time

        current_time = time.time()
        self._processed_message_ids[message_id] = current_time

        # Clean up expired entries periodically (every 10 new entries)
        if len(self._processed_message_ids) % 10 == 0:
            self._cleanup_expired_message_ids(current_time)

    def _cleanup_expired_message_ids(self, current_time: float | None = None) -> None:
        """Remove expired message IDs from the cache."""
        import time

        if current_time is None:
            current_time = time.time()

        expired_ids = [
            msg_id
            for msg_id, timestamp in self._processed_message_ids.items()
            if current_time - timestamp > self.PROCESSED_MESSAGE_TTL
        ]
        for msg_id in expired_ids:
            del self._processed_message_ids[msg_id]


# Alias for backwards compatibility
SquareData = ChatData

# Chat dictionary type: maps chat ID to ChatData
ChatStore = dict[str, ChatData]
# Alias for backwards compatibility
Square = ChatStore

# Chat type enum
ChatType = Literal["square", "talk"]

# Combined message type
ChatMessage = Union[SquareMessage, TalkMessage]


@dataclass
class ChatContext:
    """Context for chat processing (both Square and Talk)."""

    bot_name: str
    client: Client
    chats: ChatStore
    search: "Search"
    scheduler: "Scheduler | None" = None
    preferences_store: "UserPreferencesStore | None" = None
    chat_type: ChatType = "square"
    event: ChatMessage | None = None

    @property
    def square(self) -> ChatStore:
        """Backwards compatibility alias for chats."""
        return self.chats


# Alias for backwards compatibility
SquareContext = ChatContext


def create_context(
    bot_name: str,
    client: Client,
    search: "Search",
    chats: ChatStore | None = None,
    square: ChatStore | None = None,
    chat_type: ChatType = "square",
    event: ChatMessage | None = None,
) -> ChatContext:
    """
    Factory function to create ChatContext with backwards compatibility.

    Args:
        bot_name: The bot's display name.
        client: The LINE client.
        search: The search instance.
        chats: Chat store (preferred).
        square: Chat store (deprecated, use chats instead).
        chat_type: Type of chat ("square" or "talk").
        event: The message event.

    Returns:
        ChatContext instance.
    """
    # Use chats if provided, otherwise fall back to square
    store = chats if chats is not None else (square if square is not None else {})
    return ChatContext(
        bot_name=bot_name,
        client=client,
        chats=store,
        search=search,
        chat_type=chat_type,
        event=event,
    )
