"""High-level LINE client with event handling."""

import asyncio
from collections.abc import Callable
from typing import Any

from src.logging import get_logger

from ..storage import BaseStorage
from .base_client import BaseClient, Profile
from .events import TypedEventEmitter

logger = get_logger(__name__)


class TalkMessage:
    """
    Wrapper for Talk (DM/Group) messages.

    Provides convenient methods for interacting with messages.
    """

    # Thrift field IDs for Message struct
    _FIELD_FROM = 1
    _FIELD_TO = 2
    _FIELD_TO_TYPE = 3  # MIDType enum: 0=USER, 1=ROOM, 2=GROUP
    _FIELD_ID = 4
    _FIELD_TEXT = 10
    _FIELD_CONTENT_TYPE = 15
    _FIELD_CONTENT_METADATA = 18
    _FIELD_CHUNKS = 20
    _FIELD_RELATED_MESSAGE_ID = 21

    def __init__(self, raw: dict, client: "Client"):
        self._raw = raw
        self._client = client

    @property
    def raw(self) -> dict:
        """Get the raw message data."""
        return self._raw

    @property
    def id(self) -> str:
        """Get the message ID."""
        # Try field ID first, then fall back to string key for compatibility
        return self._raw.get(self._FIELD_ID) or self._raw.get("id", "")

    @property
    def text(self) -> str:
        """Get the message text."""
        return self._raw.get(self._FIELD_TEXT) or self._raw.get("text", "")

    @property
    def from_mid(self) -> str:
        """Get the sender's MID."""
        return self._raw.get(self._FIELD_FROM) or self._raw.get("from", "")

    @property
    def to_mid(self) -> str:
        """Get the recipient's MID."""
        return self._raw.get(self._FIELD_TO) or self._raw.get("to", "")

    @property
    def to_type(self) -> int:
        """
        Get the recipient's type.

        Returns:
            MIDType enum: 0=USER, 1=ROOM, 2=GROUP
        """
        tt = self._raw.get(self._FIELD_TO_TYPE) or self._raw.get("toType", 0)
        if isinstance(tt, str):
            # Handle string enum values
            type_map = {"USER": 0, "ROOM": 1, "GROUP": 2}
            return type_map.get(tt, 0)
        return tt if tt is not None else 0

    @property
    def content_type(self) -> int:
        """Get the content type."""
        ct = self._raw.get(self._FIELD_CONTENT_TYPE) or self._raw.get("contentType", 0)
        if isinstance(ct, str):
            type_map = {"NONE": 0, "IMAGE": 1, "VIDEO": 2, "AUDIO": 3, "FILE": 14}
            return type_map.get(ct, 0)
        return ct if ct else 0

    @property
    def content_metadata(self) -> dict:
        """Get the content metadata."""
        return self._raw.get(self._FIELD_CONTENT_METADATA) or self._raw.get("contentMetadata", {})

    @property
    def is_my_message(self) -> bool:
        """Check if this message was sent by the current user."""
        if self._client.base.profile:
            return self.from_mid == self._client.base.profile.mid
        return False

    async def reply(
        self,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict | None = None,
        e2ee: bool | None = None,
    ) -> dict:
        """
        Reply to this message.

        Args:
            text: Reply text
            content_type: Content type
            content_metadata: Additional metadata
            e2ee: Use E2EE encryption (None = auto-detect from original message)

        Returns:
            Sent message object
        """
        # Use toType field from message to determine reply target
        # toType: 0=USER, 1=ROOM, 2=GROUP
        to_type = self.to_type

        # Auto-detect E2EE: only use E2EE for DM replies, not for group/room
        # Group E2EE can cause decryption issues for other members
        if e2ee is None:
            if to_type in (1, 2):  # ROOM or GROUP
                # Don't use E2EE for group/room messages to ensure all members can read
                e2ee = False
            else:
                # For DMs, check if original message was E2EE encrypted
                metadata = self.content_metadata
                e2ee = "e2eeVersion" in metadata if metadata else False

        logger.debug(
            f"reply: to_type={to_type} to_mid='{self.to_mid}' "
            f"from_mid='{self.from_mid}' id='{self.id}' e2ee={e2ee}"
        )

        if to_type in (1, 2):  # ROOM or GROUP
            # For group/room messages, reply to the chat
            to = self.to_mid
        else:
            # For DM messages (toType=0 or USER), reply to the sender if not our own message
            to = self.to_mid if self.is_my_message else self.from_mid

        # Fallback: if to is empty, try to determine from MID prefix
        if not to:
            to = self.to_mid or self.from_mid
            logger.warning(f"to_type={to_type}, using fallback to={to[:20] if to else 'EMPTY'}...")

        logger.debug(f"reply: Final to='{to}' e2ee={e2ee}")

        try:
            return await self._client.base.talk.send_message(
                to=to,
                text=text,
                content_type=content_type,
                content_metadata=content_metadata,
                related_message_id=self.id,
                e2ee=e2ee,
            )
        except Exception as e:
            # If E2EE encryption failed, try without E2EE
            if e2ee:
                logger.warning(f"E2EE send failed: {e}, retrying without E2EE...")
                return await self._client.base.talk.send_message(
                    to=to,
                    text=text,
                    content_type=content_type,
                    content_metadata=content_metadata,
                    related_message_id=self.id,
                    e2ee=False,
                )
            raise

    async def react(self, reaction_type: int) -> None:
        """
        React to this message.

        Args:
            reaction_type: Type of reaction
        """
        await self._client.base.talk.react(
            message_id=int(self.id),
            reaction_type=reaction_type,
        )

    async def unsend(self) -> None:
        """Unsend this message."""
        await self._client.base.talk.unsend_message(self.id)

    async def read(self) -> None:
        """Mark this message as read."""
        await self._client.base.talk.send_chat_checked(
            chat_mid=self.to_mid,
            last_message_id=self.id,
        )

    async def get_data(self, preview: bool = False) -> tuple[bytes, dict]:
        """
        Download the message attachment.

        Args:
            preview: Download preview instead of full file

        Returns:
            Tuple of (file_data, metadata)
        """
        # Check for E2EE (chunks is field 20)
        chunks = self._raw.get(self._FIELD_CHUNKS) or self._raw.get("chunks")
        if chunks:
            result = await self._client.base.obs.download_media_e2ee(self._raw)
            if result:
                data, filename = result
                return data, {"filename": filename}
            return b"", {}

        # Check for direct URL
        download_url = self.content_metadata.get("DOWNLOAD_URL")
        if download_url:
            url = (
                self.content_metadata.get("PREVIEW_URL", download_url) if preview else download_url
            )
            http_client = await self._client.base.request.get_http_client()
            response = await http_client.get(url)
            return response.content, {}

        # Standard OBS download
        return await self._client.base.obs.download_message_data(
            message_id=self.id,
            is_preview=preview,
            is_square=False,
        )


class SquareMessage:
    """
    Wrapper for Square (OpenChat) messages.

    Provides convenient methods for interacting with Square messages.
    """

    # Thrift field IDs for SquareMessage struct
    _FIELD_MESSAGE = 1

    # Thrift field IDs for Message struct (inner message)
    _MSG_FIELD_FROM = 1
    _MSG_FIELD_TO = 2
    _MSG_FIELD_ID = 4
    _MSG_FIELD_TEXT = 10
    _MSG_FIELD_CONTENT_TYPE = 15
    _MSG_FIELD_CONTENT_METADATA = 18

    def __init__(self, raw: dict, client: "Client", sender_display_name: str = ""):
        self._raw = raw
        self._client = client
        self._sender_display_name = sender_display_name

    def _get_message(self) -> dict:
        """Get the inner Message struct."""
        # Try field ID first (1), then fall back to "message" key for compatibility
        return self._raw.get(self._FIELD_MESSAGE) or self._raw.get("message") or self._raw

    @property
    def raw(self) -> dict:
        """Get the raw message data."""
        return self._raw

    @property
    def id(self) -> str:
        """Get the message ID."""
        msg = self._get_message()
        return msg.get(self._MSG_FIELD_ID) or msg.get("id", "")

    @property
    def text(self) -> str:
        """Get the message text."""
        msg = self._get_message()
        return msg.get(self._MSG_FIELD_TEXT) or msg.get("text", "")

    @property
    def from_mid(self) -> str:
        """Get the sender's Square member MID."""
        msg = self._get_message()
        return msg.get(self._MSG_FIELD_FROM) or msg.get("from", "")

    @property
    def sender_display_name(self) -> str:
        """Get the sender's display name from event notification."""
        return self._sender_display_name

    @property
    def square_chat_mid(self) -> str:
        """Get the Square chat MID."""
        msg = self._get_message()
        return msg.get(self._MSG_FIELD_TO) or msg.get("to", "")

    @property
    def content_type(self) -> int:
        """Get the content type."""
        msg = self._get_message()
        ct = msg.get(self._MSG_FIELD_CONTENT_TYPE) or msg.get("contentType", 0)
        if isinstance(ct, str):
            type_map = {"NONE": 0, "IMAGE": 1, "VIDEO": 2, "AUDIO": 3, "FILE": 14}
            return type_map.get(ct, 0)
        return ct if ct else 0

    @property
    def content_metadata(self) -> dict:
        """Get the content metadata."""
        msg = self._get_message()
        return msg.get(self._MSG_FIELD_CONTENT_METADATA) or msg.get("contentMetadata", {})

    async def is_my_message(self) -> bool:
        """Check if this message was sent by the current user.

        In Square, we need to compare against the bot's Square member MID,
        which is different from the regular LINE MID.
        """
        try:
            square_chat_mid = self.square_chat_mid

            # Check cache first
            cache = self._client._square_member_mid_cache
            if square_chat_mid in cache:
                return self.from_mid == cache[square_chat_mid]

            # Get SquareChat to find our Square member MID
            # GetSquareChatResponse fields:
            #   1: SquareChat
            #   2: SquareChatMember (our membership info)
            #   3: SquareChatStatus
            square_chat_response = await self._client.base.square.get_square_chat(square_chat_mid)
            # SquareChatMember is field 2
            # SquareChatMember.squareMemberMid is field 1
            square_chat_member = square_chat_response.get(2) or square_chat_response.get(
                "squareChatMember", {}
            )
            my_square_member_mid = square_chat_member.get(1) or square_chat_member.get(
                "squareMemberMid", ""
            )

            # Cache for future lookups
            if my_square_member_mid:
                cache[square_chat_mid] = my_square_member_mid

            return self.from_mid == my_square_member_mid
        except Exception:
            # Fallback to regular MID comparison (likely won't work for Square)
            if self._client.base.profile:
                return self.from_mid == self._client.base.profile.mid
            return False

    async def reply(
        self,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict | None = None,
    ) -> dict:
        """
        Reply to this message.

        Args:
            text: Reply text
            content_type: Content type
            content_metadata: Additional metadata

        Returns:
            Sent message object
        """
        return await self._client.base.square.send_message(
            square_chat_mid=self.square_chat_mid,
            text=text,
            content_type=content_type,
            content_metadata=content_metadata,
            related_message_id=self.id,
        )

    async def react(self, reaction_type: int) -> dict:
        """
        React to this message.

        Args:
            reaction_type: Type of reaction

        Returns:
            Response dict
        """
        return await self._client.base.square.react_to_message(
            square_chat_mid=self.square_chat_mid,
            message_id=self.id,
            reaction_type=reaction_type,
        )

    async def unsend(self) -> dict:
        """Unsend this message."""
        return await self._client.base.square.unsend_message(
            square_chat_mid=self.square_chat_mid,
            message_id=self.id,
        )

    async def delete(self) -> dict:
        """Delete this message (admin only)."""
        return await self._client.base.square.destroy_message(
            square_chat_mid=self.square_chat_mid,
            message_id=self.id,
        )

    async def read(self) -> dict:
        """Mark this message as read."""
        return await self._client.base.square.mark_as_read(
            square_chat_mid=self.square_chat_mid,
            message_id=self.id,
        )


class Chat:
    """
    Wrapper for Talk chat (DM/Group).

    Provides convenient methods for chat operations.
    """

    # Thrift field IDs for Chat struct
    _FIELD_TYPE = 1
    _FIELD_CHAT_MID = 2
    _FIELD_CHAT_NAME = 6

    def __init__(self, raw: dict, client: "Client"):
        self._raw = raw
        self._client = client

    @property
    def raw(self) -> dict:
        """Get the raw chat data."""
        return self._raw

    @property
    def mid(self) -> str:
        """Get the chat MID."""
        return self._raw.get(self._FIELD_CHAT_MID) or self._raw.get("chatMid", "")

    @property
    def name(self) -> str:
        """Get the chat name."""
        return self._raw.get(self._FIELD_CHAT_NAME) or self._raw.get("chatName", "")

    @property
    def chat_type(self) -> int:
        """Get the chat type (1=GROUP, 2=ROOM)."""
        ct = self._raw.get(self._FIELD_TYPE) or self._raw.get("type", 0)
        return ct if ct else 0

    async def send_message(
        self,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict | None = None,
        related_message_id: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Send a message to this chat.

        Args:
            text: Message text
            content_type: Content type
            content_metadata: Additional metadata
            related_message_id: ID of message to reply to
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        return await self._client.base.talk.send_message(
            to=self.mid,
            text=text,
            content_type=content_type,
            content_metadata=content_metadata,
            related_message_id=related_message_id,
            e2ee=e2ee,
        )

    async def update_name(self, name: str) -> dict:
        """
        Update the chat name.

        Args:
            name: New chat name

        Returns:
            Response dict
        """
        return await self._client.base.talk.update_chat(
            chat_mid=self.mid,
            name=name,
        )

    async def invite(self, user_mids: list[str]) -> dict:
        """
        Invite users to this chat.

        Args:
            user_mids: List of user MIDs to invite

        Returns:
            Response dict
        """
        return await self._client.base.talk.invite_into_chat(
            chat_mid=self.mid,
            target_user_mids=user_mids,
        )

    async def leave(self) -> dict:
        """Leave this chat."""
        return await self._client.base.talk.delete_self_from_chat(self.mid)


class Square:
    """
    Wrapper for Square (OpenChat).

    Provides convenient methods for Square operations.
    """

    def __init__(self, raw: dict, client: "Client"):
        self._raw = raw
        self._client = client

    # Thrift field IDs for Square struct
    _FIELD_MID = 1
    _FIELD_NAME = 2

    @property
    def raw(self) -> dict:
        """Get the raw Square data."""
        return self._raw

    @property
    def mid(self) -> str:
        """Get the Square MID."""
        return self._raw.get(self._FIELD_MID) or self._raw.get("mid", "")

    @property
    def name(self) -> str:
        """Get the Square name."""
        return self._raw.get(self._FIELD_NAME) or self._raw.get("name", "")

    async def update_name(self, name: str) -> dict:
        """
        Update the Square name.

        Args:
            name: New Square name

        Returns:
            Response dict
        """
        return await self._client.base.square.update_square(
            square_mid=self.mid,
            name=name,
        )

    async def leave(self) -> dict:
        """Leave this Square."""
        return await self._client.base.square.leave_square(self.mid)


class SquareChat:
    """
    Wrapper for Square chat (OpenChat channel).

    Provides convenient methods for Square chat operations.
    Supports individual listening for this specific chat.
    """

    # Thrift field IDs for SquareChat struct
    _FIELD_SQUARE_CHAT_MID = 1
    _FIELD_NAME = 4

    def __init__(self, raw: dict, client: "Client"):
        self._raw = raw
        self._client = client
        self._listeners: dict[str, list[Callable]] = {}
        self._is_polling = False

    @property
    def raw(self) -> dict:
        """Get the raw Square chat data."""
        return self._raw

    @property
    def mid(self) -> str:
        """Get the Square chat MID."""
        return self._raw.get(self._FIELD_SQUARE_CHAT_MID) or self._raw.get("squareChatMid", "")

    @property
    def name(self) -> str:
        """Get the Square chat name."""
        return self._raw.get(self._FIELD_NAME) or self._raw.get("name", "")

    def on(self, event: str, callback: Callable) -> "SquareChat":
        """
        Register an event listener.

        Args:
            event: Event name ("message", "event", etc.)
            callback: Callback function

        Returns:
            Self for chaining
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return self

    def emit(self, event: str, *args: Any) -> None:
        """
        Emit an event.

        Args:
            event: Event name
            *args: Event arguments
        """
        for callback in self._listeners.get(event, []):
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(*args))
            else:
                callback(*args)

    async def send_message(
        self,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict | None = None,
        related_message_id: str | None = None,
    ) -> dict:
        """
        Send a message to this Square chat.

        Args:
            text: Message text
            content_type: Content type
            content_metadata: Additional metadata
            related_message_id: ID of message to reply to

        Returns:
            Sent message object
        """
        return await self._client.base.square.send_message(
            square_chat_mid=self.mid,
            text=text,
            content_type=content_type,
            content_metadata=content_metadata,
            related_message_id=related_message_id,
        )

    async def update_name(self, name: str) -> dict:
        """
        Update the Square chat name.

        Args:
            name: New chat name

        Returns:
            Response dict
        """
        return await self._client.base.square.update_square_chat(
            square_chat_mid=self.mid,
            name=name,
        )

    async def get_members(self, limit: int = 100) -> list[dict]:
        """
        Get members of this Square chat.

        Args:
            limit: Maximum number of members

        Returns:
            List of member objects
        """
        result = await self._client.base.square.get_square_chat_members(
            square_chat_mid=self.mid,
            limit=limit,
        )
        # GetSquareChatMembersResponse: field 1 = squareChatMembers
        return result.get(1) or result.get("squareChatMembers", [])

    async def leave(self) -> dict:
        """Leave this Square chat."""
        return await self._client.base.square.leave_square_chat(self.mid)

    async def listen(
        self,
        sync_token: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Start listening to events for this specific Square chat.

        Args:
            sync_token: Initial sync token
            on_error: Error callback
        """
        if self._is_polling:
            raise RuntimeError("Already listening")

        self._is_polling = True
        current_token = sync_token

        # Thrift field IDs for FetchSquareChatEventsResponse
        FIELD_EVENTS = 2
        FIELD_SYNC_TOKEN = 3

        # Thrift field IDs for SquareEvent
        EVENT_FIELD_TYPE = 3
        EVENT_FIELD_PAYLOAD = 4

        # SquareEventType enum values
        RECEIVE_MESSAGE = 0
        SEND_MESSAGE = 1

        # Thrift field IDs for SquareEventPayload
        PAYLOAD_RECEIVE_MESSAGE = 1
        PAYLOAD_SEND_MESSAGE = 2

        # Thrift field ID for squareMessage in ReceiveMessage/SendMessage
        MSG_FIELD_SQUARE_MESSAGE = 2

        # Catch up on initial events
        if not current_token:
            while True:
                result = await self._client.base.square.fetch_square_chat_events(
                    square_chat_mid=self.mid,
                    sync_token=current_token,
                )
                current_token = result.get(FIELD_SYNC_TOKEN)
                events = result.get(FIELD_EVENTS, [])
                if not events:
                    break

        self.emit("update:syncToken", current_token)

        # Continuous polling loop
        while self._is_polling and self._client.base.auth_token:
            try:
                result = await self._client.base.square.fetch_square_chat_events(
                    square_chat_mid=self.mid,
                    sync_token=current_token,
                )

                new_token = result.get(FIELD_SYNC_TOKEN)
                if new_token != current_token:
                    self.emit("update:syncToken", new_token)
                    current_token = new_token

                for event in result.get(FIELD_EVENTS, []):
                    self.emit("event", event)

                    # Get event type (field 3) - this is an enum value (int)
                    event_type = event.get(EVENT_FIELD_TYPE)
                    # Get payload (field 4)
                    payload = event.get(EVENT_FIELD_PAYLOAD, {})

                    if event_type == SEND_MESSAGE:
                        # sendMessage is field 2
                        send_msg = payload.get(PAYLOAD_SEND_MESSAGE, {})
                        sq_msg = send_msg.get(MSG_FIELD_SQUARE_MESSAGE)
                        if sq_msg:
                            message = SquareMessage(sq_msg, self._client)
                            self.emit("message", message)
                    elif event_type == RECEIVE_MESSAGE:
                        # receiveMessage is field 1
                        recv_msg = payload.get(PAYLOAD_RECEIVE_MESSAGE, {})
                        sq_msg = recv_msg.get(MSG_FIELD_SQUARE_MESSAGE)
                        if sq_msg:
                            message = SquareMessage(sq_msg, self._client)
                            self.emit("message", message)

                await asyncio.sleep(1)

            except Exception as e:
                if on_error:
                    on_error(e)
                await asyncio.sleep(2)

    def stop_listening(self) -> None:
        """Stop listening to events."""
        self._is_polling = False


class Client(TypedEventEmitter):
    """
    High-level LINE client with event handling.

    This provides a user-friendly API for LINE messaging.
    """

    def __init__(self, base: BaseClient):
        """
        Initialize the client.

        Args:
            base: Low-level BaseClient instance
        """
        super().__init__()
        self.base = base
        # Cache for Square member MIDs (square_chat_mid -> my_square_member_mid)
        self._square_member_mid_cache: dict[str, str] = {}
        # Listener task tracking for health monitoring
        self._talk_listener_task: asyncio.Task | None = None
        self._square_listener_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._listener_enabled = {"talk": False, "square": False}
        self._listener_restart_count = {"talk": 0, "square": 0}
        self._max_restarts = 10  # Max restarts before giving up

    @property
    def profile(self) -> Profile | None:
        """Get the current user's profile."""
        return self.base.profile

    async def get_profile(self) -> dict:
        """
        Get the current user's profile.

        Returns:
            Profile dict
        """
        return await self.base.talk.get_profile()

    async def get_contact(self, mid: str) -> dict:
        """
        Get contact information.

        Args:
            mid: User MID

        Returns:
            Contact dict
        """
        return await self.base.talk.get_contact(mid)

    async def get_chat(self, chat_mid: str) -> Chat:
        """
        Get a chat by MID.

        Args:
            chat_mid: Chat MID

        Returns:
            Chat object
        """
        result = await self.base.talk.get_chat(chat_mid)
        return Chat(result, self)

    async def get_all_chats(self) -> list[Chat]:
        """
        Get all chats the user is part of.

        Returns:
            List of Chat objects
        """
        result = await self.base.talk.get_all_chat_mids()
        # Field 1 = memberChatMids (try numeric first, then string)
        member_mids = result.get(1) or result.get("memberChatMids", [])

        if not member_mids:
            return []

        chats_result = await self.base.talk.get_chats(list(member_mids))
        # Field 1 = chats (try numeric first, then string)
        chats = chats_result.get(1) or chats_result.get("chats", [])
        return [Chat(c, self) for c in chats]

    async def get_joined_squares(self, limit: int = 100) -> list[Square]:
        """
        Get joined Squares.

        Args:
            limit: Maximum number of Squares

        Returns:
            List of Square objects
        """
        result = await self.base.square.get_joined_squares(limit=limit)
        # Field 1 = squares (try numeric first, then string)
        squares = result.get(1) or result.get("squares", [])
        return [Square(s, self) for s in squares]

    async def get_square(self, square_mid: str) -> Square:
        """
        Get a Square by MID.

        Args:
            square_mid: Square MID

        Returns:
            Square object
        """
        result = await self.base.square.get_square(square_mid)
        # GetSquareResponse: field 1 = square
        square_data = result.get(1) or result.get("square", {})
        return Square(square_data, self)

    async def get_square_chat(self, square_chat_mid: str) -> SquareChat:
        """
        Get a Square chat by MID.

        Args:
            square_chat_mid: Square chat MID

        Returns:
            SquareChat object
        """
        result = await self.base.square.get_square_chat(square_chat_mid)
        # GetSquareChatResponse: field 1 = squareChat
        square_chat_data = result.get(1) or result.get("squareChat", {})
        return SquareChat(square_chat_data, self)

    async def send_message(
        self,
        to: str,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict | None = None,
        related_message_id: str | None = None,
        e2ee: bool = False,
    ) -> TalkMessage:
        """
        Send a message.

        Args:
            to: Recipient MID
            text: Message text
            content_type: Content type
            content_metadata: Additional metadata
            related_message_id: ID of message to reply to
            e2ee: Use E2EE encryption

        Returns:
            TalkMessage object
        """
        result = await self.base.talk.send_message(
            to=to,
            text=text,
            content_type=content_type,
            content_metadata=content_metadata,
            related_message_id=related_message_id,
            e2ee=e2ee,
        )
        return TalkMessage(result, self)

    async def send_image(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Send an image.

        Args:
            to: Recipient MID
            data: Image data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        return await self.base.obs.upload_talk_image(to, data, filename, e2ee)

    async def send_video(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Send a video.

        Args:
            to: Recipient MID
            data: Video data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        return await self.base.obs.upload_talk_video(to, data, filename, e2ee)

    async def send_audio(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Send an audio file.

        Args:
            to: Recipient MID
            data: Audio data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        return await self.base.obs.upload_talk_audio(to, data, filename, e2ee)

    async def send_file(
        self,
        to: str,
        data: bytes,
        filename: str,
        e2ee: bool = False,
    ) -> dict:
        """
        Send a file.

        Args:
            to: Recipient MID
            data: File data
            filename: Filename (required)
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        return await self.base.obs.upload_talk_file(to, data, filename, e2ee)

    def listen(
        self,
        talk: bool = True,
        square: bool = True,
    ) -> None:
        """
        Start listening for events.

        Args:
            talk: Listen to Talk events (DM/Group)
            square: Listen to Square events (OpenChat)
        """
        self._listener_enabled["talk"] = talk
        self._listener_enabled["square"] = square

        if talk:
            self._talk_listener_task = asyncio.create_task(
                self._listen_talk(), name="talk_listener"
            )
        if square:
            self._square_listener_task = asyncio.create_task(
                self._listen_square(), name="square_listener"
            )

        # Start watchdog to monitor listener health
        self._watchdog_task = asyncio.create_task(
            self._listener_watchdog(), name="listener_watchdog"
        )

    async def _listener_watchdog(self) -> None:
        """Monitor listener tasks and restart them if they die unexpectedly."""
        while self.base.auth_token:
            await asyncio.sleep(5)  # Check every 5 seconds

            # Check Talk listener
            if self._listener_enabled["talk"]:
                if self._talk_listener_task is None or self._talk_listener_task.done():
                    if self._listener_restart_count["talk"] < self._max_restarts:
                        self._listener_restart_count["talk"] += 1
                        logger.warning(
                            f"[Talk] Listener died, restarting "
                            f"(attempt {self._listener_restart_count['talk']}/{self._max_restarts})"
                        )
                        self._talk_listener_task = asyncio.create_task(
                            self._listen_talk(), name="talk_listener"
                        )
                    elif self._listener_restart_count["talk"] == self._max_restarts:
                        self._listener_restart_count["talk"] += 1  # Only log once
                        logger.error(
                            f"[Talk] Listener exceeded max restarts ({self._max_restarts}), giving up"
                        )

            # Check Square listener
            if self._listener_enabled["square"]:
                if self._square_listener_task is None or self._square_listener_task.done():
                    if self._listener_restart_count["square"] < self._max_restarts:
                        self._listener_restart_count["square"] += 1
                        logger.warning(
                            f"[Square] Listener died, restarting "
                            f"(attempt {self._listener_restart_count['square']}/{self._max_restarts})"
                        )
                        self._square_listener_task = asyncio.create_task(
                            self._listen_square(), name="square_listener"
                        )
                    elif self._listener_restart_count["square"] == self._max_restarts:
                        self._listener_restart_count["square"] += 1  # Only log once
                        logger.error(
                            f"[Square] Listener exceeded max restarts ({self._max_restarts}), giving up"
                        )

    async def _listen_talk(self) -> None:
        """Listen to Talk events."""
        logger.info("[Talk] Event listener started")
        revision = 0
        global_rev = 0
        individual_rev = 0

        # Thrift field IDs for SyncResponse
        FIELD_OPERATION_RESPONSE = 1
        FIELD_FULL_SYNC_RESPONSE = 2

        # Thrift field IDs for OperationResponse
        OP_RESPONSE_FIELD_OPERATIONS = 1
        OP_RESPONSE_FIELD_GLOBAL_EVENTS = 3
        OP_RESPONSE_FIELD_INDIVIDUAL_EVENTS = 4

        # Thrift field IDs for TGlobalEvents / TIndividualEvents
        EVENTS_FIELD_LAST_REVISION = 2

        # Thrift field IDs for FullSyncResponse
        FULL_SYNC_FIELD_NEXT_REVISION = 2

        # Thrift field IDs for Operation
        OP_FIELD_REVISION = 1
        OP_FIELD_TYPE = 3
        OP_FIELD_MESSAGE = 20

        # OpType enum values
        SEND_MESSAGE = 25
        RECEIVE_MESSAGE = 26

        while self.base.auth_token:
            try:
                result = await self.base.talk.sync(
                    limit=100,
                    revision=revision,
                    global_rev=global_rev,
                    individual_rev=individual_rev,
                )

                # Check for full sync response (field 2)
                full_sync = result.get(FIELD_FULL_SYNC_RESPONSE, {})
                if full_sync:
                    # Get next revision (field 2)
                    next_rev = full_sync.get(FULL_SYNC_FIELD_NEXT_REVISION)
                    if next_rev:
                        revision = next_rev

                # Get operation response (field 1)
                op_response = result.get(FIELD_OPERATION_RESPONSE, {})

                # Update globalRev from globalEvents (field 3)
                global_events = op_response.get(OP_RESPONSE_FIELD_GLOBAL_EVENTS, {})
                if global_events and isinstance(global_events, dict):
                    new_global_rev = global_events.get(EVENTS_FIELD_LAST_REVISION)
                    if new_global_rev:
                        global_rev = new_global_rev

                # Update individualRev from individualEvents (field 4)
                individual_events = op_response.get(OP_RESPONSE_FIELD_INDIVIDUAL_EVENTS, {})
                if individual_events and isinstance(individual_events, dict):
                    new_individual_rev = individual_events.get(EVENTS_FIELD_LAST_REVISION)
                    if new_individual_rev:
                        individual_rev = new_individual_rev

                # Process operations (field 1 of OperationResponse)
                operations = op_response.get(OP_RESPONSE_FIELD_OPERATIONS, [])
                for op in operations:
                    self.emit("event", op)

                    # Update revision from operation (field 1)
                    op_revision = op.get(OP_FIELD_REVISION)
                    if op_revision and op_revision > revision:
                        revision = op_revision

                    # Get operation type (field 3) - this is an enum value (int)
                    op_type = op.get(OP_FIELD_TYPE)
                    if op_type in (SEND_MESSAGE, RECEIVE_MESSAGE):
                        # Get message (field 20)
                        message = op.get(OP_FIELD_MESSAGE, {})

                        # Check for E2EE using contentMetadata.e2eeVersion (like linejs)
                        # Field 18 = contentMetadata
                        content_metadata = message.get(18) or message.get("contentMetadata", {})
                        e2ee_version = (
                            content_metadata.get("e2eeVersion") if content_metadata else None
                        )

                        # Decrypt if e2eeVersion is set (linejs just checks e2eeVersion)
                        if e2ee_version:
                            try:
                                message = await self.base.e2ee.decrypt_e2ee_message(message)
                            except Exception as e:
                                # Log E2EE decryption error but still emit the message
                                logger.warning(f"[Talk] E2EE decrypt failed: {e}")

                        self.emit("message", TalkMessage(message, self))

                # No sleep needed - long polling returns immediately when events available
                # Only add minimal delay to prevent tight loop on empty responses

            except Exception as e:
                self.emit("error", e)
                await asyncio.sleep(1)

    async def _listen_square(self) -> None:
        """Listen to Square events."""
        sync_token: str | None = None
        continuation_token: str | None = None
        subscription_id: int | None = None
        consecutive_errors = 0
        max_consecutive_errors = 10  # Increased from 5 to allow more recovery attempts
        base_backoff = 1.0  # Base delay in seconds
        max_backoff = 60.0  # Maximum delay in seconds

        # Thrift field IDs for FetchMyEventsResponse
        FIELD_SUBSCRIPTION = 1
        FIELD_EVENTS = 2
        FIELD_SYNC_TOKEN = 3
        FIELD_CONTINUATION_TOKEN = 4

        # Thrift field IDs for SquareEvent
        EVENT_FIELD_TYPE = 3
        EVENT_FIELD_PAYLOAD = 4

        # SquareEventType enum value
        NOTIFICATION_MESSAGE = 29

        # Thrift field ID for SquareEventPayload.notificationMessage
        PAYLOAD_NOTIFICATION_MESSAGE = 30

        # Thrift field IDs for SquareEventNotificationMessage
        # Note: linejs uses fid 3 for squareMessage and fid 4 for senderDisplayName
        # winbotscript/line-protocol uses fid 2 and 3 respectively
        # We try both to support different protocol versions
        NOTIFICATION_FIELD_SQUARE_MESSAGE_V1 = 2  # winbotscript
        NOTIFICATION_FIELD_SQUARE_MESSAGE_V2 = 3  # linejs
        NOTIFICATION_FIELD_SENDER_DISPLAY_NAME_V1 = 3  # winbotscript
        NOTIFICATION_FIELD_SENDER_DISPLAY_NAME_V2 = 4  # linejs

        logger.info("[Square] Event listener started")

        while self.base.auth_token:
            try:
                result = await self.base.square.fetch_my_events(
                    sync_token=sync_token,
                    continuation_token=continuation_token,
                    subscription_id=subscription_id,
                )

                # Reset error counter on success
                consecutive_errors = 0

                # Extract syncToken (field 3) and continuationToken (field 4)
                new_sync_token = result.get(FIELD_SYNC_TOKEN)
                new_continuation_token = result.get(FIELD_CONTINUATION_TOKEN)

                # Extract subscription.subscriptionId (field 1, then subscriptionId)
                subscription = result.get(FIELD_SUBSCRIPTION, {})
                if isinstance(subscription, dict):
                    # subscriptionId is field 1 in SubscriptionState
                    subscription_id = subscription.get(1)

                # Process events (field 2)
                events = result.get(FIELD_EVENTS, [])
                for event in events:
                    self.emit("square:event", event)

                    # Get event type (field 3) - this is an enum value (int)
                    event_type = event.get(EVENT_FIELD_TYPE)
                    # Get payload (field 4)
                    payload = event.get(EVENT_FIELD_PAYLOAD, {})

                    if event_type == NOTIFICATION_MESSAGE:
                        # Get notificationMessage (field 30)
                        notification_msg = payload.get(PAYLOAD_NOTIFICATION_MESSAGE, {})
                        # Get squareMessage - try both field IDs for protocol compatibility
                        sq_msg = notification_msg.get(
                            NOTIFICATION_FIELD_SQUARE_MESSAGE_V1
                        ) or notification_msg.get(NOTIFICATION_FIELD_SQUARE_MESSAGE_V2)
                        # Get senderDisplayName - try both field IDs for protocol compatibility
                        sender_display_name = notification_msg.get(
                            NOTIFICATION_FIELD_SENDER_DISPLAY_NAME_V1, ""
                        ) or notification_msg.get(NOTIFICATION_FIELD_SENDER_DISPLAY_NAME_V2, "")
                        if sq_msg:
                            self.emit(
                                "square:message",
                                SquareMessage(sq_msg, self, sender_display_name),
                            )

                # Handle pagination: if there's a continuation token, keep fetching
                # until all pending events are retrieved before going to long polling
                if new_continuation_token:
                    # More events to fetch - use continuation token
                    continuation_token = new_continuation_token
                    # Update sync token if provided
                    if new_sync_token:
                        sync_token = new_sync_token
                else:
                    # No more pending events - reset continuation token and update sync token
                    continuation_token = None
                    if new_sync_token:
                        sync_token = new_sync_token

                # No sleep needed - long polling returns immediately when events available

            except Exception as e:
                consecutive_errors += 1
                self.emit("square:error", e)

                error_msg = str(e)
                error_type = type(e).__name__

                # Classify error type for better handling
                is_transient = any(
                    keyword in error_msg.lower()
                    for keyword in ["timeout", "connection", "network", "reset", "refused"]
                ) or error_type in ["TimeoutError", "ConnectionError", "HTTPError"]

                if is_transient:
                    # Exponential backoff for transient errors
                    backoff_delay = min(base_backoff * (2 ** (consecutive_errors - 1)), max_backoff)
                    logger.warning(
                        f"[Square] Transient error ({error_type}): {error_msg[:100]}. "
                        f"Retry {consecutive_errors}/{max_consecutive_errors} in {backoff_delay:.1f}s"
                    )
                    await asyncio.sleep(backoff_delay)
                else:
                    # API errors - check if we should stop
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            f"[Square] Stopping listener after {consecutive_errors} consecutive errors. "
                            f"Last error: {error_msg}"
                        )
                        logger.error(
                            "[Square] This may indicate the account has no Squares or "
                            "the device type doesn't support Square API."
                        )
                        break

                    logger.warning(
                        f"[Square] API error ({error_type}): {error_msg[:100]}. "
                        f"Retry {consecutive_errors}/{max_consecutive_errors}"
                    )
                    await asyncio.sleep(2)  # Fixed delay for API errors

    async def close(self) -> None:
        """Close the client and release resources."""
        # Cancel listener tasks
        for task in [
            self._talk_listener_task,
            self._square_listener_task,
            self._watchdog_task,
        ]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self.base.close()


# Login helper functions


async def login_with_qr(
    device: str = "DESKTOPWIN",
    version: str | None = None,
    endpoint: str = "legy.line-apps.com",
    storage: BaseStorage | None = None,
    storage_path: str | None = None,
    on_qr_url: Callable[[str], None] | None = None,
    on_pincode: Callable[[str], None] | None = None,
) -> Client:
    """
    Login with QR code.

    Args:
        device: Device type
        version: App version
        endpoint: API endpoint
        storage: Storage implementation (if None, uses FileStorage with storage_path)
        storage_path: Path for FileStorage (default: ./.line_storage.json)
        on_qr_url: Callback for QR code URL
        on_pincode: Callback for pincode

    Returns:
        Logged in Client
    """
    from ..storage import FileStorage

    # Use FileStorage by default for persistent token storage
    if storage is None:
        storage_file = storage_path or "./.line_storage.json"
        storage = FileStorage(storage_file)

    base = BaseClient(device, version, endpoint, storage)

    # Set up event handler to persist authToken to storage
    async def save_auth_token(token: str) -> None:
        await storage.set("authToken", token)

    base.on("update:authtoken", lambda token: asyncio.create_task(save_auth_token(token)))

    if on_qr_url:
        base.on("qrcall", on_qr_url)
    if on_pincode:
        base.on("pincall", on_pincode)

    await base.login_process.login(qr=True)
    return Client(base)


async def login_with_password(
    email: str,
    password: str,
    device: str = "DESKTOPWIN",
    version: str | None = None,
    endpoint: str = "legy.line-apps.com",
    storage: BaseStorage | None = None,
    storage_path: str | None = None,
    pincode: str | None = None,
    on_pincode: Callable[[str], None] | None = None,
    on_qr_url: Callable[[str], None] | None = None,
    fallback_to_qr: bool = True,
) -> Client:
    """
    Login with email and password.

    Attempts to use a stored refresh token first to avoid repeated logins.
    Falls back to password login if refresh token is unavailable or expired.
    If password login fails with internal error and fallback_to_qr is True,
    will attempt QR code login as final fallback.

    Args:
        email: Email address
        password: Password
        device: Device type
        version: App version
        endpoint: API endpoint
        storage: Storage implementation (if None, uses FileStorage with storage_path)
        storage_path: Path for FileStorage (default: ./.line_storage.json)
        pincode: Constant pincode (optional)
        on_pincode: Callback for pincode
        on_qr_url: Callback for QR code URL (for fallback)
        fallback_to_qr: Whether to fall back to QR login on password failure

    Returns:
        Logged in Client
    """
    from ..storage import FileStorage
    from .exceptions import InternalError

    # Use FileStorage by default for persistent token storage
    if storage is None:
        storage_file = storage_path or "./.line_storage.json"
        storage = FileStorage(storage_file)

    base = BaseClient(device, version, endpoint, storage)

    # Set up event handler to persist authToken to storage
    async def save_auth_token(token: str) -> None:
        await storage.set("authToken", token)

    base.on("update:authtoken", lambda token: asyncio.create_task(save_auth_token(token)))

    if on_pincode:
        base.on("pincall", on_pincode)
    if on_qr_url:
        base.on("qrcall", on_qr_url)

    # Try to load stored auth token first
    stored_auth_token = await storage.get("authToken")
    if stored_auth_token and isinstance(stored_auth_token, str):
        base.auth_token = stored_auth_token

    # Try to refresh token first
    try:
        refresh_token = await storage.get("refreshToken")
        if refresh_token:
            base.log("login", {"method": "refresh_token", "email": email})
            await base.auth.try_refresh_token()
            await base.login_process.ready()
            base.log("login", {"status": "success", "method": "refresh_token"})
            return Client(base)
    except Exception as e:
        base.log("login", {"error": "refresh_failed", "message": str(e), "fallback": "password"})
        # Fall through to password login

    # Try password login
    try:
        await base.login_process.login(email=email, password=password, pincode=pincode)
        return Client(base)
    except InternalError as e:
        # Check if this is an internal error (code 20) which often means rate limiting
        error_code = e.data.get("code") if e.data else None
        if error_code == 20 and fallback_to_qr:
            logger.warning("Password login failed (Internal Error - likely rate limited)")
            logger.info("Falling back to QR code login...")
            logger.info("Please scan the QR code with your LINE mobile app.")

            # Fall back to QR login
            if not on_qr_url:
                # Default QR URL handler if none provided (sync callback)
                base.on("qrcall", lambda url: logger.info(f"Scan this QR code URL: {url}"))

            await base.login_process.login(qr=True)
            return Client(base)
        raise


async def login_with_token(
    auth_token: str,
    device: str = "DESKTOPWIN",
    version: str | None = None,
    endpoint: str = "legy.line-apps.com",
    storage: BaseStorage | None = None,
    storage_path: str | None = None,
) -> Client:
    """
    Login with an existing auth token.

    Args:
        auth_token: Auth token
        device: Device type
        version: App version
        endpoint: API endpoint
        storage: Storage implementation (if None, uses FileStorage with storage_path)
        storage_path: Path for FileStorage (default: ./.line_storage.json)

    Returns:
        Logged in Client
    """
    from ..storage import FileStorage

    # Use FileStorage by default for persistent token storage
    if storage is None:
        storage_file = storage_path or "./.line_storage.json"
        storage = FileStorage(storage_file)

    base = BaseClient(device, version, endpoint, storage)

    # Set up event handler to persist authToken to storage
    async def save_auth_token(token: str) -> None:
        await storage.set("authToken", token)

    base.on("update:authtoken", lambda token: asyncio.create_task(save_auth_token(token)))

    await base.login_process.login(auth_token=auth_token)
    return Client(base)
