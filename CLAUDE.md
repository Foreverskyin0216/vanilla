# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vanilla is a LINE chatbot that role-plays as an ancient palace lady (inspired by《甄嬛傳》) using OpenAI's language models and LangGraph for conversation management. The bot integrates with LINE's Square Chat platform and includes web search capabilities via Tavily.

## Development Commands

### Core Commands

- `uv run python -m src.main` - Start the chatbot application
- `uv run python scripts/test_ui.py` - Run interactive test UI (includes scheduler)
- `uv run ruff check .` - Run linting
- `uv run ruff format .` - Format code
- `uv run pytest` - Run tests

### Environment Setup

- Copy `.env.example` to `.env` and configure required variables:
  - `CATGIRL_NAME` - Bot's display name (default: "香草")
  - `LINE_EMAIL` and `LINE_PASSWORD` - LINE account credentials
  - `OPENAI_API_KEY` - OpenAI API key for LLM functionality
  - `TAVILY_API_KEY` - Tavily API key for web search functionality
  - `POSTGRES_URL` - PostgreSQL connection string for LangGraph checkpointer
  - `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST` - Langfuse credentials for LLM observability

### Installation

```bash
# Install dependencies using uv
uv sync

# Install with dev dependencies
uv sync --extra dev

# Or using pip
pip install -e .
```

## Architecture

### Project Structure

```
vanilla/
├── src/
│   ├── linepy/          # LINE client library (integrated)
│   │   ├── client/      # Client and login functionality
│   │   ├── e2ee/        # End-to-end encryption
│   │   ├── obs/         # Object storage (media)
│   │   ├── server/      # FastAPI server
│   │   ├── services/    # Talk and Square services
│   │   ├── storage/     # Storage backends
│   │   └── thrift/      # Thrift protocol
│   ├── bot.py           # ChatBot class
│   ├── graph.py         # LangGraph workflow
│   ├── helpers.py       # Helper functions and nodes
│   ├── main.py          # Entry point
│   ├── preferences.py   # User preferences store for persistent rules
│   ├── prompts.py       # Prompt templates
│   ├── scheduler.py     # Task scheduler for timed messages
│   ├── search.py        # Tavily search
│   ├── tools.py         # LangChain tools
│   └── types.py         # Type definitions
├── scripts/             # Utility scripts
│   └── test_ui.py       # Interactive test UI (Rich-based)
├── tests/               # Test files
├── pyproject.toml       # Project configuration
└── uv.lock              # Dependency lock file
```

### Core Components

**Main Entry Point** (`src/main.py`):

- Initializes ChatBot with environment-configured name
- Async entry point for the serve method

**ChatBot Class** (`src/bot.py`):

- Central orchestrator managing LINE client and conversation state
- Handles both Square Chat (OpenChat) and Talk (Group/DM) integration with asyncio queue
- Manages per-chat state including conversation history and member tracking
- Integrates with LangGraph workflow for response generation
- Contains `Scheduler` instance for timed message tasks
- Contains `UserPreferencesStore` instance for user preference rules
- Message sender callback for scheduler to send messages to chats

**Graph Workflow** (`src/graph.py`):

- LangGraph workflow with 3-node architecture:
  - `updateChatInfo`: Validates messages, updates Square/member state, checks mention/reply triggers
  - `addReaction`: Uses gpt-4.1-mini to select appropriate emoji reactions
  - `chat`: Generates responses using gpt-4.1 with tool support
- Uses `MessagesState` for state management
- Command-based routing between nodes

**Helper Functions** (`src/helpers.py`):

- Chat member and message management utilities (unified for Square and Talk)
- `_add_chat`, `_add_member`, `_add_chat_message` - Unified state management
- Mention and reply detection: `_is_mentioned`, `_is_reply`
- Content type handling: `_get_content_type`, `_get_sticker_info`
- Sticker vision analysis: `analyze_sticker_with_vision` - Uses GPT-4 Vision to analyze sticker images
- Sticker image fetching: `fetch_sticker_image`, `get_sticker_image_url` - Fetches sticker images from LINE CDN
- **Deferred sticker analysis**: `parse_pending_sticker`, `resolve_pending_stickers` - Sticker analysis is deferred to the chat node for faster trigger detection
- LangGraph node functions: `update_chat_info`, `add_reaction`, `chat`
- **Sticker trigger logic**: Stickers only trigger responses when they are replies to bot's messages (not on mentions)
- **Member caching**: Member lookups are cached per-chat with 5-minute TTL to reduce API calls

**LINE Client** (`src/linepy/`):

- Integrated LINE client library for Square Chat and Talk (Group/DM)
- Supports login via password, QR code, or token
- E2EE encryption support for both Talk and Square messages
- Media upload/download via OBS
- Event listeners: `_listen_talk()` and `_listen_square()` for real-time message processing

**Scheduler** (`src/scheduler.py`):

- Manages timed tasks for sending scheduled messages using cron expressions
- **PostgreSQL Persistence**: Tasks are stored in PostgreSQL and survive service restarts
  - Table: `scheduled_tasks` with columns for id, chat_id, message, cron_expression, status, etc.
  - Automatically creates table on first startup
  - Loads pending tasks from database when scheduler starts
- `Scheduler` class with background worker for task execution
- `ScheduledTask` dataclass with support for:
  - Cron-based scheduling (minute hour day month weekday)
  - One-time and recurring tasks with configurable max trigger counts
  - Unlimited execution with `max_triggers=-1`
  - Task states: pending, running, completed, cancelled
- Helper functions:
  - `parse_cron_expression`: Validate and parse cron expressions
  - `parse_start_time`: Parse start time strings ("now", "14:30", "2024-01-15 14:30")
- Cron expression examples:
  - `* * * * *` - Every minute
  - `0 * * * *` - Every hour at :00
  - `0 9 * * *` - Every day at 9:00
  - `*/5 * * * *` - Every 5 minutes
  - `0 9 * * 1` - Every Monday at 9:00
  - `0 9,18 * * *` - Every day at 9:00 and 18:00
- Integrated with ChatBot via message sender callback
- **Note**: Scheduler tools are only available when `scheduler` and `chat_id` are passed to `create_tools()`
- **Note**: System tasks (like daily cleanup) are NOT persisted to database

**User Preferences** (`src/preferences.py`):

- Manages persistent user-specific rules and settings (chat-specific, no global rules)
- **PostgreSQL Persistence**: Preferences are stored in PostgreSQL and survive service restarts
  - Table: `user_preferences` with columns for id, user_id, chat_id, rule_type, rule_key, rule_value, etc.
  - Automatically creates table on first startup
- `UserPreference` dataclass with support for:
  - Rule types: `nickname`, `trigger`, `behavior`, `custom`
  - **Chat-specific scope only** (each rule only applies to the chat where it was set)
  - Soft delete via `is_active` flag
- `UserPreferencesStore` class with async methods:
  - `set_preference(user_id, chat_id, rule_type, rule_key, rule_value)`: Create or update a preference
  - `get_preference(user_id, chat_id, rule_type, rule_key)`: Get a specific preference
  - `get_preferences_for_user(user_id, chat_id)`: Get all preferences for a user in a chat
  - `delete_preference(user_id, chat_id, rule_type, rule_key)`: Soft delete a preference
- `format_preferences_for_prompt()`: Format preferences for injection into system prompt
- **Note**: Preference tools are only available when `preferences_store`, `user_id`, and `chat_id` are passed to `create_tools()`

**Search Integration** (`src/search.py`):

- Tavily API wrapper for web search
- Advanced search depth for comprehensive results
- Returns direct answers from search queries

**Prompts** (`src/prompts.py`):

- `VANILLA_PERSONALITY`: Ancient palace lady persona with classical Chinese speech patterns
- `ADD_REACTION_INSTRUCTIONS`: Reaction selection guidance with emoji mapping

**Tools** (`src/tools.py`):

- `websearch`: Web search tool using Tavily for real-time information
- `get_datetime`: DateTime tool for current time queries
- `schedule_task`: Create timed tasks using cron expressions (requires scheduler)
  - Parameters: `message`, `cron`, `start_time`, `description`, `max_triggers`
  - `max_triggers=-1` for unlimited execution
- `list_scheduled_tasks`: List all scheduled tasks for current chat (requires scheduler)
- `cancel_scheduled_task`: Cancel a scheduled task by ID (requires scheduler)
- `update_scheduled_task`: Update message, cron, or description of a task (requires scheduler)
- `set_user_preference`: Save a user preference rule (requires preferences_store)
  - Parameters: `rule_type`, `rule_key`, `rule_value`
  - Rule types: `nickname`, `trigger`, `behavior`, `custom`
- `get_user_preferences`: List all preferences for the current user (requires preferences_store)
- `delete_user_preference`: Delete a preference by type and key (requires preferences_store)
- Factory function `create_tools(search, scheduler?, chat_id?, preferences_store?, user_id?)` for tool instantiation

**Types** (`src/types.py`):

- `Message`, `Member`, `ChatData` (alias: `SquareData`): Data classes for state management
- `ChatData` includes per-chat member caching with `is_member_cached()` and `update_member_cache_time()` methods
- `ChatContext`: Context dataclass for graph node functions

**Test UI** (`scripts/test_ui.py`):

- Rich-based terminal UI for testing the chatbot
- Direct LLM interaction without LINE client
- Displays tool usage in formatted tables
- Includes scheduler support with background worker
- Commands: `/help`, `/clear`, `/history`, `/tasks`, `/quit`
- Scheduled messages display in console with yellow border

### Key Dependencies

- `httpx` - HTTP client for LINE API
- `pycryptodome` / `pynacl` - Cryptography for E2EE
- `langgraph` - Conversation flow management with Command routing
- `langchain-openai` - OpenAI LLM integration
- `tavily-python` - Web search capabilities
- `langfuse` - LLM observability and tracing
- `python-dotenv` - Environment variable management
- `croniter` - Cron expression parsing for scheduler

### State Management

- Per-chat conversation state via `SquareData` dataclass
- Per-member tracking with name and message history
- Bot ID tracking for mention and reply detection
- Async PostgreSQL checkpointer for state persistence

### Message Processing Flow

1. Message received via `_listen_talk()` or `_listen_square()` and queued for processing via asyncio.Queue
2. **updateChatInfo**: Validate content type, update chat state, check triggers
   - Supported content types: text (NONE) and stickers
   - **Stickers**: Creates a pending marker `[傳送了貼圖: PENDING:{sticker_id}:{alt_text}]` for deferred analysis
   - Sticker image URL: `https://stickershop.line-scdn.net/stickershop/v1/sticker/{STKID}/iPhone/sticker@2x.png`
   - **Member caching**: Member lookups are cached per-chat (5-minute TTL) to avoid redundant API calls
   - Other media (images, videos, audio, files): Logged but not processed for responses
3. Trigger conditions:
   - **Text messages**: Trigger if mentioned OR replied to bot's message
   - **Stickers**: Trigger ONLY if replied to bot's message (mentions are ignored for stickers)
4. If triggered:
   - **addReaction**: Select and apply emoji reaction (parallel)
   - **chat**: Resolves pending sticker analyses using GPT-4 Vision, then generates response with personality prompt (parallel)
5. Reply sent via LINE API (Square Chat or Talk)

### Content Type Constants

- `CONTENT_TYPE_NONE (0)`: Text messages
- `CONTENT_TYPE_IMAGE (1)`: Images
- `CONTENT_TYPE_VIDEO (2)`: Videos
- `CONTENT_TYPE_AUDIO (3)`: Audio messages
- `CONTENT_TYPE_STICKER (7)`: Stickers (processed with GPT-4 Vision)
- `CONTENT_TYPE_FILE (14)`: Files

## Code Conventions

### Python Configuration

- Python 3.11+ required
- Type hints used throughout
- Async/await for all I/O operations

### Logging Configuration

- Default log level: INFO (configurable via `LOG_LEVEL` environment variable)
- Set `LOG_LEVEL=DEBUG` for verbose debugging output
- Noisy libraries are silenced: `httpx`, `httpcore`, `langchain`, `langgraph`, `openai`
- Background execution (`make bg`) includes automatic log rotation:
  - Rotates logs when file exceeds 10MB
  - Keeps 5 most recent rotated logs
  - Old logs are gzip compressed

### Linting and Formatting

- Ruff for linting and formatting
- mypy for type checking

### Architecture Patterns

- Dataclasses for structured data
- LangGraph `Command` for explicit node routing
- Queue-based message processing for thread safety
- Tool-based extensibility through LangChain tools
