# Vanilla

> !!**Built with Vibe Coding - AI-assisted development**!!

Vanilla is a LINE chatbot that role-plays as an ancient palace lady (inspired by the Chinese TV drama "Legend of Zhen Huan"), powered by OpenAI language models and LangGraph for conversation management. The bot integrates with LINE's Square Chat platform and includes web search capabilities via Tavily.

## Features

- Ancient palace lady persona with classical Chinese speech patterns
- Conversation state management via LangGraph
- LINE Square Chat (OpenChat) and Talk (Group/DM) integration
- End-to-end encryption (E2EE) support for messages
- Web search functionality via Tavily
- Sticker analysis with GPT-4 Vision
- Automatic LINE reactions to messages
- Cron-based task scheduler for timed messages
- User preferences persistence (nicknames, custom rules)
- PostgreSQL persistence for conversation state and user data
- Langfuse LLM observability and tracing

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- PostgreSQL 17+
- LINE account (with "Login with password" and "Letter Sealing" enabled)

## Quick Start

### One-Command Setup

```bash
# Full setup (install packages + create .env + configure PostgreSQL)
make setup

# Edit .env and fill in the required credentials
cp .env.example .env
vi .env

# Start the service
make run
```

### Manual Installation

1. **Install uv** (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **Install Python packages**

```bash
uv sync
```

3. **Configure environment variables**

```bash
cp .env.example .env
# Edit .env and fill in the required credentials
```

4. **Set up PostgreSQL**

```bash
./scripts/setup-postgres.sh
```

5. **Start the service**

```bash
uv run python -m src.main
```

## Environment Variables

Copy `.env.example` to `.env` and configure the following:

| Variable | Description | Required |
|----------|-------------|----------|
| `CATGIRL_NAME` | Bot display name (default: 香草) | No |
| `LINE_EMAIL` | LINE account email | Yes |
| `LINE_PASSWORD` | LINE account password | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `OPENAI_API_ENDPOINT` | Custom OpenAI API endpoint | No |
| `TAVILY_API_KEY` | Tavily API key for web search | Yes |
| `POSTGRES_URL` | PostgreSQL connection string | Yes |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | No |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | No |
| `LANGFUSE_HOST` | Langfuse host URL | No |
| `LOG_LEVEL` | Logging level (default: INFO, set to DEBUG for verbose output) | No |

## Makefile Commands

```bash
make help          # Show all available commands
```

### Setup Commands

| Command | Description |
|---------|-------------|
| `make setup` | Full setup (packages + env + PostgreSQL) |
| `make install` | Install Python packages |
| `make install-dev` | Install with dev dependencies |
| `make setup-env` | Create .env from .env.example |
| `make setup-postgres` | Install and configure PostgreSQL |

### Run Commands

| Command | Description |
|---------|-------------|
| `make run` | Start the service |
| `make dev` | Full setup and start |
| `make bg` | Run in background |
| `make stop` | Stop background process |
| `make logs` | View background logs |

### Test Commands

| Command | Description |
|---------|-------------|
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage report |
| `make test-ui` | Start interactive test UI |

### Development Commands

| Command | Description |
|---------|-------------|
| `make lint` | Run linting |
| `make lint-fix` | Fix linting issues |
| `make format` | Format code |
| `make clean` | Clean cache and build files |

## Project Structure

```
vanilla/
├── src/
│   ├── linepy/          # LINE client library
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
│   ├── preferences.py   # User preferences store
│   ├── prompts.py       # Prompt templates
│   ├── scheduler.py     # Task scheduler
│   ├── search.py        # Tavily search
│   ├── tools.py         # LangChain tools
│   └── types.py         # Type definitions
├── tests/               # Test files
│   ├── linepy/          # linepy module tests
│   └── ...
├── scripts/             # Setup scripts
├── pyproject.toml       # Project configuration
├── Makefile             # Make commands
└── .env.example         # Environment variables template
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LINE Server                                    │
│                         (Square Chat / Talk)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          │  Thrift Protocol  │
                          │   (HTTP/HTTPS)    │
                          └─────────┬─────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                               linepy/                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         LineClient                                  │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐    │    │
│  │  │  TalkService  │  │ SquareService │  │  E2EE (Encryption)    │    │    │
│  │  │  - sync()     │  │ - fetchEvents │  │  - encrypt/decrypt    │    │    │
│  │  │  - sendMsg()  │  │ - sendMessage │  │  - key management     │    │    │
│  │  └───────────────┘  └───────────────┘  └───────────────────────┘    │    │
│  │                                                                     │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │              Event Listeners (asyncio)                        │  │    │
│  │  │   _listen_talk()  ←──┬──→  _listen_square()                   │  │    │
│  │  │         │            │            │                           │  │    │
│  │  │   emit("message")    │    emit("message")                     │  │    │
│  │  └──────────┬───────────┴────────────┬───────────────────────────┘  │    │
│  └─────────────┼────────────────────────┼──────────────────────────────┘    │
│                │                        │                                   │
└────────────────┼────────────────────────┼───────────────────────────────────┘
                 │                        │
                 └──────────┬─────────────┘
                            │
                      ┌─────▼─────┐
                      │  asyncio  │
                      │   Queue   │
                      └─────┬─────┘
                            │
┌───────────────────────────┼──────────────────────────────────────────────────┐
│                           │           vanilla/                               │
│                     ┌─────▼─────┐                                            │
│                     │  ChatBot  │  (src/bot.py)                              │
│                     │ _process_ │                                            │
│                     │ _message()│                                            │
│                     └─────┬─────┘                                            │
│                           │                                                  │
│         ┌─────────────────┼─────────────────┐                                │
│         │                 │                 │                                │
│   ┌─────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐                         │
│   │ LangGraph │    │  Scheduler  │   │PostgreSQL   │                         │
│   │ Workflow  │    │  Message    │   │Checkpointer │                         │
│   └─────┬─────┘    └─────────────┘   └─────────────┘                         │
│         │                                                                    │
│   ┌─────▼─────────────────────────────────────────────┐                      │
│   │                  Graph Nodes                      │                      │
│   │  ┌────────────────────┐  ┌────────────────┐  ┌───────────────┐           │
│   │  │ updateChatInfo     │→ │addReaction     │→ │  chat         │           │
│   │  │ - Check Messages   │  │ - Add Reaction │  │ - AI Response │           │
│   │  │ - Check Status     │  │ - LLM          │  │ - Tools       │           │
│   │  │ - Check Condition  │  │                │  │ - LLM         │           │
│   │  └────────────────────┘  └────────────────┘  └───────────────┘           │
│   └───────────────────────────────────────────────────┘                      │
│                           │                                                  │
│                     ┌─────▼─────┐                                            │
│                     │   Tools   │                                            │
│                     │- websearch│                                            │
│                     │- datetime │                                            │
│                     │- schedule │                                            │
│                     │- prefs    │                                            │
│                     └───────────┘                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Message Processing

### Trigger Conditions

| Message Type | Trigger Condition | Description |
|--------------|-------------------|-------------|
| Text | `@mention` or `reply` | Triggered when @mentioned or replying to bot's message |
| Sticker | `reply` only | Only triggered when replying to bot's message |
| Image/Video/Audio/File | Not triggered | Logged but no response generated |

### Processing Flow

```
Message Received
    │
    ▼
┌─────────────────────┐
│   updateChatInfo    │
│  - Check Messages   │
│  - Check Status     │
│  - Check Condition  │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │ Trigger?  │
     └─────┬─────┘
      No   │      Yes
      ▼    │       ▼
     End   │       ┌──────────────────────┐
           │       │ Parallel Execution   │
           │       │                      │
           │       ▼                      ▼
           │  addReaction               chat
           │       │                      │
           │       ▼                      ▼
           │   Send Reaction        Send Response
           │       │                      │
           └───────┴──────────────────────┘
                       │
                       ▼
                      End
```

### Detailed Steps

1. **Message Reception**: Received via `_listen_talk()` or `_listen_square()`
2. **Queue**: Messages are queued for processing via asyncio.Queue
3. **updateChatInfo**:
   - Validate content type (only text and stickers processed)
   - Update chat state and member information
   - Check for mentions or replies
   - Stickers only trigger when replying to bot's message
4. **addReaction** (parallel): Select and apply emoji reaction
5. **chat** (parallel): Generate AI response with persona
6. **Send Response**: Reply via LINE API

## Development

### Interactive Test UI

A Rich-based terminal interface for direct LLM interaction and tool usage inspection:

```bash
make test-ui
```

Features:
- Send messages and interact with the AI
- View AI responses
- Inspect tool usage and parameters
- Commands: `/help`, `/clear`, `/history`, `/tasks`, `/quit`

### Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov
```

### Code Quality

```bash
# Check code style
make lint

# Format code
make format
```

## References

- https://langchain-ai.github.io/langgraph/
- https://python.langchain.com/docs/introduction/
- https://docs.astral.sh/uv
- https://github.com/evex-dev/linejs

## License

MIT
