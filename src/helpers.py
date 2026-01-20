"""Helper functions for the LangGraph workflow."""

import base64
import re
from typing import TYPE_CHECKING, Literal

import httpx
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel

from src import prompts
from src.linepy import SquareMessage
from src.logging import get_logger
from src.types import ChatContext, ChatData, Member, Message

if TYPE_CHECKING:
    from src.graph import VanillaContext

logger = get_logger(__name__)

# LINE content type constants
CONTENT_TYPE_NONE = 0
CONTENT_TYPE_IMAGE = 1
CONTENT_TYPE_VIDEO = 2
CONTENT_TYPE_AUDIO = 3
CONTENT_TYPE_STICKER = 7
CONTENT_TYPE_FILE = 14

# LINE sticker CDN URL template
LINE_STICKER_URL_TEMPLATE = (
    "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/iPhone/sticker@2x.png"
)

# Pending sticker analysis marker
# Format: [傳送了貼圖: PENDING:{sticker_id}:{alt_text}]
PENDING_STICKER_PREFIX = "PENDING:"

# Backwards compatibility aliases
SquareContext = ChatContext
SquareData = ChatData


def parse_pending_sticker(text: str) -> tuple[str, str] | None:
    """
    Parse pending sticker marker from message text.

    Args:
        text: Message text that may contain pending sticker marker.

    Returns:
        Tuple of (sticker_id, alt_text) if found, None otherwise.
    """
    if PENDING_STICKER_PREFIX not in text:
        return None

    # Extract content between [傳送了貼圖: PENDING:...] and ]
    import re

    pattern = rf"\[傳送了貼圖: {PENDING_STICKER_PREFIX}([^:\]]+):([^\]]*)\]"
    match = re.search(pattern, text)
    if match:
        return match.group(1), match.group(2)
    return None


async def resolve_pending_stickers(messages: list) -> list:
    """
    Resolve all pending sticker markers in messages by analyzing them with vision.

    This function processes messages in parallel for efficiency.

    Args:
        messages: List of message dicts with "role" and "content" keys.

    Returns:
        Updated messages list with pending stickers resolved.
    """
    import asyncio

    # Find all messages with pending stickers
    pending_indices = []
    pending_tasks = []

    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        parsed = parse_pending_sticker(content)
        if parsed:
            sticker_id, alt_text = parsed
            pending_indices.append((i, sticker_id, alt_text))
            pending_tasks.append(analyze_sticker_with_vision(sticker_id, alt_text))

    if not pending_tasks:
        return messages

    # Analyze all pending stickers in parallel
    results = await asyncio.gather(*pending_tasks, return_exceptions=True)

    # Update messages with resolved sticker descriptions
    for (i, sticker_id, alt_text), result in zip(pending_indices, results):
        if isinstance(result, Exception):
            # Fallback to alt text on error
            description = alt_text if alt_text else "貼圖"
        else:
            description = result

        old_marker = f"[傳送了貼圖: {PENDING_STICKER_PREFIX}{sticker_id}:{alt_text}]"
        new_text = f"[傳送了貼圖: {description}]"
        messages[i]["content"] = messages[i]["content"].replace(old_marker, new_text)

    return messages


# =============================================================================
# Sticker vision analysis functions
# =============================================================================


def get_sticker_image_url(sticker_id: str) -> str:
    """
    Generate the LINE sticker image URL from sticker ID.

    Args:
        sticker_id: The LINE sticker ID (STKID)

    Returns:
        URL to the sticker image
    """
    return LINE_STICKER_URL_TEMPLATE.format(sticker_id=sticker_id)


async def fetch_sticker_image(sticker_id: str) -> bytes | None:
    """
    Fetch the sticker image data from LINE CDN.

    Args:
        sticker_id: The LINE sticker ID (STKID)

    Returns:
        Image bytes or None if fetch failed
    """
    url = get_sticker_image_url(sticker_id)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.content
            logger.warning(f"Failed to fetch sticker {sticker_id}: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"Error fetching sticker {sticker_id}: {e}")
    return None


async def analyze_sticker_with_vision(sticker_id: str, sticker_text: str = "") -> str:
    """
    Analyze a LINE sticker image using GPT-4 Vision to understand its meaning.

    Uses create_agent with vision model for consistency with other LLM calls.

    Args:
        sticker_id: The LINE sticker ID (STKID)
        sticker_text: Optional alt text provided by LINE (STKTXT)

    Returns:
        Description of what the sticker conveys
    """
    # Fetch the sticker image
    image_data = await fetch_sticker_image(sticker_id)

    if not image_data:
        # Fallback to alt text if available
        if sticker_text:
            return sticker_text
        return "貼圖 (無法取得圖片)"

    # Encode image to base64
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    # Create agent for sticker analysis (no tools needed)
    system_prompt = (
        "你是一個貼圖分析專家。請用簡短的中文描述這個貼圖表達的情緒或意思。"
        "只需要描述貼圖的內容和情感，不需要說「這是一個貼圖」之類的話。"
        "例如：「開心揮手」「生氣跺腳」「害羞捂臉」「愛心眼睛」「哭泣」等。"
        "回覆不超過10個字。"
    )

    agent = create_agent(
        model="openai:gpt-4.1-mini",
        tools=[],
        system_prompt=system_prompt,
    )

    # Build message with image content
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                },
                {
                    "type": "text",
                    "text": "這個貼圖表達什麼意思？",
                },
            ],
        },
    ]

    try:
        result = await agent.ainvoke({"messages": messages})
        # Extract the response from agent result
        result_messages = result.get("messages", [])
        description = ""
        for msg in reversed(result_messages):
            if hasattr(msg, "content") and msg.content:
                description = str(msg.content).strip()
                break

        if not description:
            description = "貼圖"

        # Combine with alt text if both available
        if sticker_text and sticker_text != description:
            return f"{description} ({sticker_text})"
        return description
    except Exception as e:
        logger.warning(f"Vision analysis failed for sticker {sticker_id}: {e}")
        # Fallback to alt text
        if sticker_text:
            return sticker_text
        return "貼圖"


class ReactionChoice(BaseModel):
    """Schema for reaction selection."""

    reaction: Literal["ALL", "NICE", "LOVE", "FUN", "AMAZING", "SAD", "OMG"]


# =============================================================================
# Helper functions for getting message data (unified for Square and Talk)
# =============================================================================


# Thrift field IDs for Message struct
_MSG_FIELD_FROM = 1
_MSG_FIELD_TO = 2
_MSG_FIELD_ID = 4
_MSG_FIELD_TEXT = 10
_MSG_FIELD_CONTENT_TYPE = 15
_MSG_FIELD_CONTENT_METADATA = 18
_MSG_FIELD_RELATED_MESSAGE_ID = 21

# Thrift field IDs for SquareMember struct
_SQUARE_MEMBER_FIELD_MID = 1  # squareMemberMid
_SQUARE_MEMBER_FIELD_DISPLAY_NAME = 3  # displayName

# Thrift field IDs for Contact struct
_CONTACT_FIELD_MID = 1  # mid
_CONTACT_FIELD_DISPLAY_NAME = 22  # displayName


def _get_content_type(raw: dict) -> int:
    """
    Get the content type from raw message data.

    Supports both string keys (field names) and numeric keys (thrift field IDs).

    Returns:
        Integer content type (0=NONE, 1=IMAGE, 2=VIDEO, 3=AUDIO, 7=STICKER, 14=FILE)
    """
    # Try numeric field ID first (thrift), then string key
    ct = raw.get(_MSG_FIELD_CONTENT_TYPE) or raw.get("contentType", 0)
    if isinstance(ct, str):
        type_map = {
            "NONE": 0,
            "IMAGE": 1,
            "VIDEO": 2,
            "AUDIO": 3,
            "STICKER": 7,
            "FILE": 14,
        }
        return type_map.get(ct, 0)
    return ct if ct else 0


def _get_content_metadata(raw: dict) -> dict:
    """
    Get content metadata from raw message data.

    Supports both string keys (field names) and numeric keys (thrift field IDs).

    Returns:
        Content metadata dictionary.
    """
    return raw.get(_MSG_FIELD_CONTENT_METADATA) or raw.get("contentMetadata", {}) or {}


def _get_sticker_info(raw: dict) -> dict | None:
    """
    Extract sticker information from raw message data.

    Returns:
        Dict with sticker info (id, package_id, version, text) or None if not a sticker.
    """
    content_type = _get_content_type(raw)
    if content_type != CONTENT_TYPE_STICKER:
        return None

    metadata = _get_content_metadata(raw)
    sticker_id = metadata.get("STKID", "")
    package_id = metadata.get("STKPKGID", "")
    version = metadata.get("STKVER", "")
    sticker_text = metadata.get("STKTXT", "")

    if not sticker_id:
        return None

    return {
        "id": sticker_id,
        "package_id": package_id,
        "version": version,
        "text": sticker_text,
    }


def _get_message_data(context: ChatContext) -> tuple[str, str, str, dict]:
    """
    Extract message data from context (works for both Square and Talk).

    Supports both string keys (field names) and numeric keys (thrift field IDs).

    Returns:
        Tuple of (message_to, message_from, message_text, raw_message)
    """
    if not context.event:
        return "", "", "", {}

    if context.chat_type == "square":
        # Square messages have nested structure
        # SquareMessage field 1 = Message struct
        raw = context.event.raw.get(1) or context.event.raw.get("message") or context.event.raw
    else:
        # Talk messages have flat structure
        raw = context.event.raw

    # Extract fields using both numeric IDs and string keys
    message_to = raw.get(_MSG_FIELD_TO) or raw.get("to", "")
    message_from = raw.get(_MSG_FIELD_FROM) or raw.get("from", "")
    message_text = raw.get(_MSG_FIELD_TEXT) or raw.get("text", "")

    return (message_to, message_from, message_text, raw)


# =============================================================================
# Square-specific helper functions
# =============================================================================


async def _get_square_member(context: ChatContext) -> dict | None:
    """Get the Square member who sent the message."""
    if not context.event or context.chat_type != "square":
        return None

    message_to, message_from, _, _ = _get_message_data(context)

    chat = await context.client.get_square_chat(message_to)
    members = await chat.get_members()

    for member in members:
        # Try numeric field ID first (1), then string key for compatibility
        member_mid = member.get(_SQUARE_MEMBER_FIELD_MID) or member.get("squareMemberMid")
        if member_mid == message_from:
            return member
    return None


async def _add_square_member(context: ChatContext) -> None:
    """Add or update a Square member in the context."""
    if not context.event or context.chat_type != "square":
        return

    message_to, message_from, _, _ = _get_message_data(context)

    chat_data = context.chats.get(message_to)
    if not chat_data:
        return

    # Check if member is already cached (skip API call)
    if chat_data.is_member_cached(message_from):
        return

    square_member = await _get_square_member(context)
    if not square_member:
        return

    # Try numeric field ID first (3), then string key for compatibility
    display_name = square_member.get(_SQUARE_MEMBER_FIELD_DISPLAY_NAME) or square_member.get(
        "displayName", ""
    )

    # Find existing member
    for member in chat_data.members:
        if member.id == message_from:
            member.name = display_name
            chat_data.update_member_cache_time()
            return

    # Add new member
    chat_data.members.append(Member(id=message_from, name=display_name))
    chat_data.update_member_cache_time()


# =============================================================================
# Talk-specific helper functions
# =============================================================================


async def _get_talk_member(context: ChatContext) -> dict | None:
    """Get the Talk member who sent the message."""
    if not context.event or context.chat_type != "talk":
        return None

    _, message_from, _, _ = _get_message_data(context)

    try:
        contact = await context.client.get_contact(message_from)
        return contact
    except Exception:
        return None


async def _add_talk_member(context: ChatContext) -> None:
    """Add or update a Talk member in the context."""
    if not context.event or context.chat_type != "talk":
        return

    message_to, message_from, _, _ = _get_message_data(context)

    chat_data = context.chats.get(message_to)
    if not chat_data:
        return

    # Check if member is already cached (skip API call)
    if chat_data.is_member_cached(message_from):
        return

    talk_member = await _get_talk_member(context)
    if not talk_member:
        return

    # Try numeric field ID first (22), then string key for compatibility
    display_name = talk_member.get(_CONTACT_FIELD_DISPLAY_NAME) or talk_member.get(
        "displayName", message_from
    )

    # Find existing member
    for member in chat_data.members:
        if member.id == message_from:
            member.name = display_name
            chat_data.update_member_cache_time()
            return

    # Add new member
    chat_data.members.append(Member(id=message_from, name=display_name))
    chat_data.update_member_cache_time()


# =============================================================================
# Unified helper functions (work for both Square and Talk)
# =============================================================================


async def _add_member(context: ChatContext) -> None:
    """Add or update a member in the context (unified for Square and Talk)."""
    if context.chat_type == "square":
        await _add_square_member(context)
    else:
        await _add_talk_member(context)


def _add_chat_message(context: ChatContext) -> None:
    """Add a message to the chat's message history (unified for Square and Talk)."""
    if not context.event:
        return

    bot_name = context.bot_name
    message_to, message_from, message_text, raw = _get_message_data(context)

    # Find member name and create a unique identifier
    # Format: "DisplayName#abc123" where abc123 is the first 6 chars of the member ID
    # This helps distinguish between users with the same display name
    member_name = message_from
    short_member_id = message_from[:6] if message_from else ""
    chat_data = context.chats.get(message_to)
    if chat_data:
        for member in chat_data.members:
            if member.id == message_from:
                member_name = member.name
                break

    # Combine display name with short ID for unique identification
    member_identifier = f"{member_name}#{short_member_id}"

    # Handle different content types
    content_type = _get_content_type(raw)
    sticker_info = _get_sticker_info(raw)

    if sticker_info:
        # Defer sticker analysis to chat node for faster trigger detection
        # Format: PENDING:{sticker_id}:{alt_text}
        sticker_id = sticker_info.get("id", "")
        sticker_alt_text = sticker_info.get("text", "")
        text = f"[傳送了貼圖: {PENDING_STICKER_PREFIX}{sticker_id}:{sticker_alt_text}]"
    elif content_type == CONTENT_TYPE_IMAGE:
        text = "[傳送了圖片]"
    elif content_type == CONTENT_TYPE_VIDEO:
        text = "[傳送了影片]"
    elif content_type == CONTENT_TYPE_AUDIO:
        text = "[傳送了語音訊息]"
    elif content_type == CONTENT_TYPE_FILE:
        text = "[傳送了檔案]"
    else:
        # Regular text message - clean the text
        text = message_text.replace(f"@{bot_name}", "").strip()

        # Check if message was E2EE encrypted but couldn't be decrypted
        # E2EE messages have contentMetadata.e2eeVersion and chunks field (20)
        metadata = _get_content_metadata(raw)
        e2ee_version = metadata.get("e2eeVersion")
        has_chunks = raw.get(20) or raw.get("chunks")

        if not text and e2ee_version and has_chunks:
            # Message was E2EE encrypted but couldn't be decrypted
            text = "[訊息已加密，無法讀取內容]"
            logger.warning("E2EE message could not be decrypted - using placeholder text")

    new_message = HumanMessage(content=f"{member_identifier}: {text}")

    # Extract message ID using both numeric field ID and string key
    message_id = raw.get(_MSG_FIELD_ID) or raw.get("id", "")

    context.chats[message_to].messages.append(new_message)
    context.chats[message_to].history.append(Message(id=message_id, content=text))


# Backwards compatibility alias
_add_square_message = _add_chat_message


def _add_chat(context: ChatContext) -> None:
    """Initialize chat data if not exists (unified for Square and Talk)."""
    if not context.event:
        return

    message_to, _, _, _ = _get_message_data(context)

    if message_to not in context.chats:
        context.chats[message_to] = ChatData()


# Backwards compatibility alias
_add_square = _add_chat


def _is_mentioned(context: ChatContext) -> bool:
    """Check if the bot is mentioned in the message."""
    if not context.event:
        return False

    message_to, _, message_text, raw = _get_message_data(context)
    metadata = _get_content_metadata(raw)

    chat_data = context.chats.get(message_to)
    if not chat_data:
        logger.debug("_is_mentioned: no chat_data")
        return False

    # For Talk messages, also check if it's a direct message (DM)
    # In DMs, we respond to all messages from the other user
    if context.chat_type == "talk" and context.client:
        to_type = context.client.base.get_to_type(message_to)
        if to_type == 0:  # USER (direct message)
            return True

    # Check MENTION metadata first - this works even for E2EE encrypted messages
    # because contentMetadata is not encrypted
    mention_data = metadata.get("MENTION", "")
    if mention_data:
        # Check if the bot's MID is in the mention data
        bot_mid = (
            context.client.base.profile.mid
            if context.client and context.client.base.profile
            else None
        )
        if bot_mid and bot_mid in mention_data:
            return True

    # Check if the message contains the bot's name (with or without @)
    has_name = f"@{context.bot_name}" in message_text or context.bot_name in message_text

    # For Talk messages, be more lenient - just check for name in text
    if context.chat_type == "talk":
        return has_name

    # For Square messages, check the MENTION metadata
    if not chat_data.bot_id:
        # Check by name if bot_id not set
        has_mention = "MENTION" in metadata
        return has_mention and has_name

    # Check by bot_id
    return "MENTION" in metadata and chat_data.bot_id in mention_data


async def _is_reply(context: ChatContext) -> bool:
    """Check if the message is a reply to one of the bot's messages."""
    if not context.event:
        return False

    message_to, message_from, _, raw = _get_message_data(context)
    # Try numeric field ID first (21), then string key
    related_message_id = raw.get(_MSG_FIELD_RELATED_MESSAGE_ID) or raw.get("relatedMessageId")

    chat_data = context.chats.get(message_to)
    if not related_message_id or not chat_data:
        return False

    # Check if replying to one of the bot's messages (fast path)
    if related_message_id in chat_data.bot_message_ids:
        return True

    # Fallback: if bot_id is set but bot_message_ids is empty/doesn't have this ID,
    # fetch recent messages to check if the replied message is from the bot
    if chat_data.bot_id and context.client and context.chat_type == "square":
        try:
            # Fetch recent messages to find the replied message
            result = await context.client.base.square.fetch_square_chat_events(
                square_chat_mid=message_to,
                limit=50,  # Fetch last 50 messages
                direction=2,  # BACKWARD (most recent first)
            )
            events = result.get(2) or result.get("events", [])

            for event in events:
                # Get event type (field 3)
                event_type = event.get(3) or event.get("eventType")
                # SquareEventType: RECEIVE_MESSAGE = 0, SEND_MESSAGE = 1
                if event_type not in (0, 1):
                    continue

                payload = event.get(4) or event.get("payload", {})
                # Get message from payload (field 1 for receiveMessage, field 2 for sendMessage)
                msg_wrapper = payload.get(1) or payload.get(2) or {}
                sq_msg = msg_wrapper.get(2) or msg_wrapper.get("squareMessage", {})
                inner_msg = sq_msg.get(1) or sq_msg.get("message", {})

                msg_id = inner_msg.get(4) or inner_msg.get("id", "")
                if msg_id == related_message_id:
                    # Found the replied message, check if sender is bot
                    sender_mid = inner_msg.get(1) or inner_msg.get("from", "")
                    if sender_mid == chat_data.bot_id:
                        # Cache this for future checks
                        chat_data.bot_message_ids.add(msg_id)
                        logger.debug(f"_is_reply: found bot message via API, ID={msg_id[:20]}...")
                        return True
                    break
        except Exception as e:
            logger.debug(f"_is_reply: fallback API check failed: {e}")

    return False


async def should_trigger_response(context: ChatContext) -> bool:
    """
    Check if a message should trigger a bot response.

    This is a lightweight pre-check that can be used before graph invocation
    to determine if Langfuse tracing should be enabled. It does NOT modify
    any state (unlike update_chat_info which adds chat/member data).

    Args:
        context: Chat context with event data.

    Returns:
        True if the message should trigger a response, False otherwise.
    """
    if not context.event:
        return False

    _, _, _, raw = _get_message_data(context)
    content_type = _get_content_type(raw)

    # Only process text messages and stickers
    if content_type not in (CONTENT_TYPE_NONE, CONTENT_TYPE_STICKER):
        return False

    # Check if this is the bot's own message
    if isinstance(context.event, SquareMessage):
        is_bot_message = await context.event.is_my_message()
    else:
        is_bot_message = context.event.is_my_message

    if is_bot_message:
        return False

    # Check trigger conditions
    is_mentioned = _is_mentioned(context)
    is_reply = await _is_reply(context)

    # For stickers, only respond if it's a reply to bot's message
    if content_type == CONTENT_TYPE_STICKER:
        return is_reply
    else:
        return is_mentioned or is_reply


async def update_chat_info(
    state: MessagesState, runtime: Runtime["VanillaContext"]
) -> Command[Literal["addReaction", "chat", "__end__"]]:
    """
    Update chat info and determine next steps.

    This node validates messages, updates chat state, and checks mention/reply triggers.
    Works for both Square and Talk messages.
    """
    context = runtime.context.chat_context
    if not context.event:
        return Command(goto="__end__")

    message_to, message_from, message_text, raw = _get_message_data(context)
    content_type = _get_content_type(raw)

    # Process text messages and stickers, skip other content types
    if content_type not in (CONTENT_TYPE_NONE, CONTENT_TYPE_STICKER):
        return Command(goto="__end__")

    # Update chat state (unified for Square and Talk)
    _add_chat(context)

    # Check for duplicate message processing
    # Extract message ID early for deduplication check
    message_id = raw.get(_MSG_FIELD_ID) or raw.get("id", "")
    chat_data = context.chats.get(message_to)
    if chat_data and message_id:
        if chat_data.is_message_processed(message_id):
            logger.debug(f"update_chat_info: skipping duplicate message {message_id[:20]}...")
            return Command(goto="__end__")
        # Mark as processed before any further handling
        chat_data.mark_message_processed(message_id)

    await _add_member(context)
    _add_chat_message(context)

    # Check if this is the bot's own message
    if isinstance(context.event, SquareMessage):
        is_bot_reply = await context.event.is_my_message()
        # Set bot_id from cache after is_my_message() populates it
        if chat_data and context.client:
            cache = context.client._square_member_mid_cache
            if message_to in cache and not chat_data.bot_id:
                chat_data.bot_id = cache[message_to]
                logger.debug(f"update_chat_info: set bot_id={chat_data.bot_id[:20]}...")
    else:
        is_bot_reply = context.event.is_my_message

    if is_bot_reply:
        # Record bot's own message ID for reply detection
        # This helps when service restarts and bot_message_ids is empty
        if chat_data and message_id:
            chat_data.bot_message_ids.add(message_id)
            logger.debug(f"update_chat_info: recorded bot message ID {message_id[:20]}...")
        return Command(goto="__end__")

    # Check if mentioned or replied to
    is_mentioned = _is_mentioned(context)
    is_reply = await _is_reply(context)

    # For stickers, only respond if it's a reply to bot's message
    # (you can't mention someone in a sticker, so is_mentioned is not applicable)
    if content_type == CONTENT_TYPE_STICKER:
        if not is_reply:
            return Command(goto="__end__")
    elif not is_mentioned and not is_reply:
        return Command(goto="__end__")

    logger.info(
        f"update_chat_info: triggered for '{message_text[:50]}...' from {message_from[:20]}..."
    )
    return Command(goto=["addReaction", "chat"])


def _create_reaction_tool():
    """Create a tool for selecting reactions."""
    from langchain_core.tools import tool

    @tool
    def select_reaction(
        reaction: Literal["ALL", "NICE", "LOVE", "FUN", "AMAZING", "SAD", "OMG"],
    ) -> str:
        """
        Select a reaction emoji based on the message content.

        Args:
            reaction: The reaction type to apply. Options:
                - ALL: No reaction (skip)
                - NICE: 👍 Thumbs up for agreement or approval
                - LOVE: ❤️ Heart for affection or love
                - FUN: 😄 Smile for funny or amusing content
                - AMAZING: 😮 Wow for impressive or surprising content
                - SAD: 😢 Sad for sad or disappointing content
                - OMG: 😱 Shocked for shocking or unbelievable content

        Returns:
            Confirmation message.
        """
        return f"Selected reaction: {reaction}"

    return select_reaction


async def add_reaction(
    state: MessagesState, runtime: Runtime["VanillaContext"]
) -> Command[Literal["__end__"]]:
    """
    Add a reaction to the message using create_agent to select appropriate emoji.
    Works for both Square and Talk messages.
    """
    context = runtime.context.chat_context
    if not context.event:
        return Command(goto="__end__")

    message_to, _, message_text, raw = _get_message_data(context)
    # Try numeric field ID first (21), then string key
    related_message_id = raw.get(_MSG_FIELD_RELATED_MESSAGE_ID) or raw.get("relatedMessageId")

    chat_data = context.chats.get(message_to)
    if not chat_data:
        return Command(goto="__end__")

    # Build input text
    text = message_text.replace(f"@{context.bot_name}", "").strip()

    # Check if it's a reply
    related_content = None
    for m in chat_data.history:
        if m.id == related_message_id:
            related_content = m.content
            break

    if related_content:
        input_text = f"引用: {related_content}\n回覆: {text}"
    else:
        input_text = text

    # Create agent with reaction tool
    reaction_tool = _create_reaction_tool()
    agent = create_agent(
        model="openai:gpt-4.1-mini",
        tools=[reaction_tool],
        system_prompt=prompts.ADD_REACTION_INSTRUCTIONS,
    )

    # Invoke agent to select reaction
    result = await agent.ainvoke({"messages": [{"role": "user", "content": input_text}]})

    # Extract reaction from tool call
    reaction = "ALL"  # Default to no reaction
    result_messages = result.get("messages", [])
    for msg in result_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "select_reaction":
                    args = tool_call.get("args", {})
                    reaction = args.get("reaction", "ALL")
                    break

    # Apply reaction if not "ALL"
    if reaction != "ALL":
        reaction_map = {
            "NICE": 2,
            "LOVE": 3,
            "FUN": 4,
            "AMAZING": 5,
            "SAD": 6,
            "OMG": 7,
        }
        reaction_type = reaction_map.get(reaction, 2)
        await context.event.react(reaction_type)

    return Command(goto="__end__")


async def chat(
    state: MessagesState, runtime: Runtime["VanillaContext"]
) -> Command[Literal["__end__"]]:
    """
    Generate and send a response using create_agent with SummarizationMiddleware.
    Works for both Square and Talk messages.
    """
    from src.graph import build_chat_agent

    context = runtime.context.chat_context
    chat_id = runtime.context.chat_id

    if not context.event:
        return Command(goto="__end__")

    bot_name = context.bot_name
    message_to, message_from, _, _ = _get_message_data(context)

    chat_data = context.chats.get(message_to)
    if not chat_data:
        return Command(goto="__end__")

    # Build the chat agent with SummarizationMiddleware
    # Pass user_id (message_from) for user preference tools
    agent = await build_chat_agent(context, chat_id, user_id=message_from)

    # Build messages for the agent
    messages = []
    for msg in chat_data.messages:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})

    # Resolve any pending sticker analyses (deferred from updateChatInfo)
    # This runs sticker vision analysis in parallel while the agent is being built
    messages = await resolve_pending_stickers(messages)

    logger.debug(f"chat: invoking agent with {len(messages)} messages")

    # Invoke the agent
    result = await agent.ainvoke({"messages": messages})

    # Extract the last AI response
    final_messages = result.get("messages", [])
    answer = ""
    for msg in reversed(final_messages):
        if hasattr(msg, "content") and msg.content:
            # Skip tool messages
            if hasattr(msg, "type") and msg.type == "tool":
                continue
            answer = str(msg.content)
            break

    clean_answer = answer.replace(f"{bot_name}:", "").replace(f"{bot_name}：", "").strip()

    # Filter out member ID suffixes (e.g., "#abc123") that may leak into the response
    # The ID suffix format is "#" followed by 6 alphanumeric characters
    clean_answer = re.sub(r"#[a-zA-Z0-9]{6}\b", "", clean_answer)

    logger.info(f"chat: response='{clean_answer[:80]}...'")

    # Send reply
    try:
        result = await context.event.reply(text=clean_answer)
        # Store bot's message ID for reply detection
        # Response structure varies: Square returns nested structure, Talk returns flat
        # Try to extract message ID from the response
        sent_message_id = None
        if isinstance(result, dict):
            # Square: SendMessageResponse -> squareMessage (field 1) -> message (field 1) -> id (field 4)
            sq_msg = result.get(1) or result.get("squareMessage")
            if isinstance(sq_msg, dict):
                msg = sq_msg.get(1) or sq_msg.get("message")
                if isinstance(msg, dict):
                    sent_message_id = msg.get(4) or msg.get("id")
            # Talk: Message struct directly -> id (field 4)
            if not sent_message_id:
                sent_message_id = result.get(4) or result.get("id")
        if sent_message_id:
            chat_data.bot_message_ids.add(sent_message_id)
            logger.debug(f"chat: stored bot message ID {sent_message_id[:20]}...")
    except Exception as e:
        logger.error(f"chat: reply failed: {e}")

    # Update state with response
    ai_response = AIMessage(content=clean_answer)
    chat_data.messages.append(ai_response)

    return Command(goto="__end__", update={"messages": [ai_response]})
