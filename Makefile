# Makefile for Vanilla Chatbot
# Usage: make help

.PHONY: all install setup-postgres setup-env run dev clean check-postgres stop-postgres help test lint format bg stop logs

# Default target
all: install setup-postgres run

# Install Python dependencies using uv
install:
	@echo "📦 Installing Python dependencies with uv..."
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "⚠️  uv not found. Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	uv sync

# Install with development dependencies
install-dev:
	@echo "📦 Installing Python dependencies with dev extras..."
	uv sync --extra dev

# Setup PostgreSQL database
setup-postgres:
	@echo "🐘 Setting up PostgreSQL..."
	@chmod +x ./scripts/setup-postgres.sh
	./scripts/setup-postgres.sh

# Check if PostgreSQL is running
check-postgres:
	@echo "🔍 Checking PostgreSQL status..."
	@if command -v brew >/dev/null 2>&1; then \
		brew services info postgresql@17 2>/dev/null || echo "PostgreSQL service not found"; \
	elif command -v systemctl >/dev/null 2>&1; then \
		systemctl status postgresql --no-pager || true; \
	else \
		pg_isready -h localhost -p 5432 || echo "PostgreSQL is not running"; \
	fi

# Stop PostgreSQL (macOS only via Homebrew)
stop-postgres:
	@echo "🛑 Stopping PostgreSQL..."
	@if command -v brew >/dev/null 2>&1; then \
		brew services stop postgresql@17; \
	elif command -v systemctl >/dev/null 2>&1; then \
		sudo systemctl stop postgresql; \
	else \
		echo "Please stop PostgreSQL manually"; \
	fi

# Setup .env file from example
setup-env:
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env from .env.example..."; \
		cp .env.example .env; \
		echo "⚠️  Please edit .env and fill in your credentials"; \
	else \
		echo "✅ .env already exists"; \
	fi

# Run the application
run:
	@echo "🚀 Starting Vanilla chatbot..."
	uv run python -m src.main

# Run in development mode with all setup
dev: install-dev setup-env setup-postgres
	@echo "🚀 Starting Vanilla chatbot in development mode..."
	uv run python -m src.main

# Run in background with log rotation
bg:
	@echo "🚀 Starting Vanilla chatbot in background..."
	@mkdir -p logs
	@# Rotate old logs if current log is > 10MB
	@if [ -f logs/vanilla.log ]; then \
		SIZE=$$(stat -f%z logs/vanilla.log 2>/dev/null || stat -c%s logs/vanilla.log 2>/dev/null || echo 0); \
		if [ "$$SIZE" -gt 10485760 ]; then \
			TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
			mv logs/vanilla.log logs/vanilla.$$TIMESTAMP.log; \
			gzip logs/vanilla.$$TIMESTAMP.log 2>/dev/null || true; \
			echo "📦 Rotated old log to logs/vanilla.$$TIMESTAMP.log.gz"; \
			ls -t logs/vanilla.*.log.gz 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true; \
		fi; \
	fi
	@PYTHONUNBUFFERED=1 nohup uv run python -m src.main >> logs/vanilla.log 2>&1 & echo $$! > .pid
	@echo "✅ Started with PID $$(cat .pid)"
	@echo "📄 Logs: logs/vanilla.log"
	@echo "💡 Use 'make logs' to view output or 'make stop' to stop"

# Stop background process
stop:
	@if [ -f .pid ]; then \
		PID=$$(cat .pid); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "🛑 Stopping process $$PID..."; \
			kill $$PID; \
			rm -f .pid; \
			echo "✅ Stopped"; \
		else \
			echo "⚠️  Process $$PID not running"; \
			rm -f .pid; \
		fi \
	else \
		echo "⚠️  No .pid file found"; \
	fi

# View logs
logs:
	@if [ -f logs/vanilla.log ]; then \
		tail -f logs/vanilla.log; \
	else \
		echo "⚠️  No log file found. Run 'make bg' first."; \
	fi

# Run interactive test UI
test-ui:
	@echo "🎭 Starting test UI..."
	uv run python scripts/test_ui.py

# Run tests
test:
	@echo "🧪 Running tests..."
	uv run pytest

# Run tests with coverage
test-cov:
	@echo "🧪 Running tests with coverage..."
	uv run pytest --cov=src --cov-report=term-missing

# Run linting
lint:
	@echo "🔍 Running linter..."
	uv run ruff check .

# Fix linting issues
lint-fix:
	@echo "🔧 Fixing linting issues..."
	uv run ruff check . --fix

# Run formatting
format:
	@echo "✨ Formatting code..."
	uv run ruff format .

# Check formatting (no changes)
format-check:
	@echo "🔍 Checking code format..."
	uv run ruff format . --check

# Clean build artifacts
clean:
	@echo "🧹 Cleaning..."
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Full setup (install + env + postgres)
setup: install-dev setup-env setup-postgres
	@echo "✅ Setup complete! Run 'make run' to start the application"

# Help
help:
	@echo "Vanilla Chatbot - Makefile Commands"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make setup          - Full setup (install deps, env, postgres)"
	@echo "  make install        - Install Python dependencies"
	@echo "  make install-dev    - Install with development dependencies"
	@echo "  make setup-env      - Create .env from .env.example"
	@echo "  make setup-postgres - Install and configure PostgreSQL"
	@echo ""
	@echo "Run Commands:"
	@echo "  make run            - Start the application"
	@echo "  make dev            - Setup everything and start"
	@echo "  make bg             - Start in background"
	@echo "  make stop           - Stop background process"
	@echo "  make logs           - View background logs (tail -f)"
	@echo "  make all            - Install, setup postgres, and start"
	@echo ""
	@echo "PostgreSQL Commands:"
	@echo "  make check-postgres - Check PostgreSQL status"
	@echo "  make stop-postgres  - Stop PostgreSQL service"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make test           - Run tests"
	@echo "  make test-cov       - Run tests with coverage report"
	@echo "  make test-ui        - Run interactive test UI"
	@echo ""
	@echo "Development Commands:"
	@echo "  make lint           - Run linter (ruff check)"
	@echo "  make lint-fix       - Fix linting issues"
	@echo "  make format         - Format code (ruff format)"
	@echo "  make format-check   - Check code format"
	@echo "  make clean          - Remove cache and build artifacts"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make setup       - Run full setup"
	@echo "  2. Edit .env        - Add your credentials"
	@echo "  3. make run         - Start the bot"
