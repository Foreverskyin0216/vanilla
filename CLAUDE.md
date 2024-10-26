# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vanilla is a LINE chatbot that role-plays as a cute catgirl using OpenAI's language models and LangGraph for conversation management. The bot integrates with LINE's Square Chat platform and includes web search capabilities via Tavily.

## Development Commands

### Core Commands

- `npm run start` - Start the chatbot application using tsx
- `npm run lint:fix` - Run ESLint with auto-fix
- `npm run format:fix` - Format code with Prettier
- `npm run pre-commit` - Run lint-staged (executed automatically via Husky)

### Environment Setup

- Copy `.env.example` to `.env` and configure required variables:
  - `CATGIRL_NAME` - Bot's display name (default: "香草")
  - `LINE_EMAIL` and `LINE_PASSWORD` - LINE account credentials
  - `OPENAI_API_KEY` - OpenAI API key for LLM functionality
  - `TAVILY_API_KEY` - Tavily API key for web search functionality

## Architecture

### Core Components

**Main Entry Point** (`src/main.ts`):

- Initializes ChatBot with environment-configured name
- Simple async wrapper for the serve method

**ChatBot Class** (`src/bot.ts`):

- Central orchestrator managing LINE client, AI, and conversation state
- Handles Square Chat integration with message queuing
- Manages per-chat state including conversation history and member tracking
- Integrates with LangGraph workflow for response generation

**AI System** (`src/ai.ts`):

- Wrapper around OpenAI ChatGPT (default model: gpt-4.1)
- Supports tool calling, structured output, and embeddings
- Instance caching for different model configurations

**Graph Workflow** (`src/graph.ts`):

- Enhanced LangGraph workflow with 4-node architecture
- Proper error handling and fallback mechanisms
- Integrated memory loading and post-processing
- Tool call loop prevention (max 3 calls)
- Structured conversation phases and state tracking

**Search Integration** (`src/search.ts`):

- Enhanced Tavily API wrapper with intelligent query optimization
- Dynamic search parameters based on query type (news, financial, tech)
- Automatic real-time data detection and optimized retrieval
- Multiple fallback strategies for improved accuracy
- Source validation and credible domain targeting
- Query preprocessing to remove noise and enhance relevance

**Long-Term Memory System** (`src/memory.ts`):

- Persistent JSON-based storage for user information and relationships
- AI-powered automatic memory evaluation and extraction
- Semantic search using embeddings for memory retrieval
- Token-efficient context loading (only relevant memories)
- Three memory types: personal facts, relationship dynamics, and events
- Automatic memory management with size limits and importance scoring

### Key Dependencies

- `@evex/linejs` - LINE messaging platform integration
- `@langchain/langgraph` - Conversation flow management
- `@langchain/openai` - OpenAI LLM and embeddings
- `@tavily/core` - Web search capabilities
- `p-queue` - Message processing queue management

### State Management

- Per-chat conversation history (max 100 messages)
- Per-member message tracking for reply detection
- Vector store integration for semantic search (MemoryVectorStore)
- Bot ID tracking for mention and reply detection
- Long-term memory persistence in `./data/memory.json`
- Automatic memory categorization and relationship tracking

### Enhanced Message Processing Flow

1. Message validation (text-only content)
2. Square/member/conversation state initialization
3. Mention/reply detection logic
4. **LangGraph Workflow Execution**:
   - **loadMemoryContext**: Retrieve relevant memories for user context
   - **processMessage**: Generate response with memory-enhanced context
   - **executeTools**: Execute tool calls with error handling (max 3 loops)
   - **postProcess**: Store conversation memories and cleanup
5. Response generation and reaction handling
6. **Built-in error handling**: Graceful fallbacks for each workflow stage

## Code Conventions

### TypeScript Configuration

- Target: ESNext with bundler module resolution
- Strict type checking enabled (noImplicitAny: false exception)
- Source maps and unused variable detection enabled

### Linting and Formatting

- ESLint with TypeScript-ESLint recommended configuration
- Prettier for code formatting
- Husky pre-commit hooks with lint-staged
- Commitlint with conventional commit format

### Architecture Patterns

- Dependency injection through LangGraph configurable parameters
- Queue-based message processing for thread safety
- State management with conversation history limits
- Tool-based extensibility through LangChain integration
