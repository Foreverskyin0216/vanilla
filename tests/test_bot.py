"""Tests for bot module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot import ChatBot


class TestChatBotInit:
    """Tests for ChatBot initialization."""

    def test_init_default_device(self):
        """Test ChatBot initialization with default device."""
        bot = ChatBot("TestBot")
        assert bot.bot_name == "TestBot"
        assert bot.device == "DESKTOPMAC"
        assert bot.client is None
        assert bot.checkpointer is None
        assert bot.app is None
        assert bot._running is False

    def test_init_custom_device(self):
        """Test ChatBot initialization with custom device."""
        bot = ChatBot("TestBot", device="ANDROID")
        assert bot.device == "ANDROID"

    def test_init_queue_created(self):
        """Test that message queue is created on init."""
        bot = ChatBot("TestBot")
        assert isinstance(bot.queue, asyncio.Queue)

    def test_init_chat_context_none(self):
        """Test that chat_context starts as None."""
        bot = ChatBot("TestBot")
        assert bot.chat_context is None


class TestOnSquareMessage:
    """Tests for _on_square_message method."""

    def test_on_square_message_adds_to_queue(self):
        """Test that incoming messages are added to queue."""
        bot = ChatBot("TestBot")
        mock_event = MagicMock()
        mock_event.text = "Hello"

        bot._on_square_message(mock_event)

        assert bot.queue.qsize() == 1

    def test_on_square_message_multiple_messages(self):
        """Test multiple messages are queued."""
        bot = ChatBot("TestBot")

        for i in range(3):
            mock_event = MagicMock()
            mock_event.text = f"Message {i}"
            bot._on_square_message(mock_event)

        assert bot.queue.qsize() == 3


class TestProcessMessage:
    """Tests for _process_message method."""

    @pytest.mark.asyncio
    async def test_process_message_no_app(self):
        """Test _process_message returns early when app is None."""
        bot = ChatBot("TestBot")
        mock_event = MagicMock()

        # Should not raise, just return
        await bot._process_message(mock_event, "square")

    @pytest.mark.asyncio
    async def test_process_message_no_context(self):
        """Test _process_message returns early when context is None."""
        bot = ChatBot("TestBot")
        bot.app = MagicMock()  # App exists but context is None
        mock_event = MagicMock()

        # Should not raise, just return
        await bot._process_message(mock_event, "square")

    @pytest.mark.asyncio
    async def test_process_message_with_app_and_context(self):
        """Test _process_message invokes the app."""
        bot = ChatBot("TestBot")
        bot.app = MagicMock()
        bot.app.ainvoke = AsyncMock(return_value={})

        bot.chat_context = MagicMock()
        bot.chat_context.bot_name = "TestBot"
        bot.chat_context.client = MagicMock()
        bot.chat_context.chats = {}
        bot.chat_context.search = MagicMock()

        mock_event = MagicMock()
        mock_event.text = "Hello"
        mock_event.square_chat_mid = "chat123"

        await bot._process_message(mock_event, "square")

        bot.app.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_handles_exception(self, caplog):
        """Test _process_message handles exceptions gracefully."""
        import logging

        bot = ChatBot("TestBot")
        bot.app = MagicMock()
        bot.app.ainvoke = AsyncMock(side_effect=Exception("Test error"))

        bot.chat_context = MagicMock()
        bot.chat_context.bot_name = "TestBot"
        bot.chat_context.client = MagicMock()
        bot.chat_context.chats = {}
        bot.chat_context.search = MagicMock()

        mock_event = MagicMock()
        mock_event.text = "Hello"
        mock_event.square_chat_mid = "chat123"

        with caplog.at_level(logging.ERROR):
            await bot._process_message(mock_event, "square")

        assert any("Error processing" in record.message for record in caplog.records)


class TestMessageWorker:
    """Tests for _message_worker method."""

    @pytest.mark.asyncio
    async def test_message_worker_processes_queue(self):
        """Test worker processes messages from queue."""
        bot = ChatBot("TestBot")
        bot._running = True
        bot.app = MagicMock()
        bot.app.ainvoke = AsyncMock(return_value={})

        bot.chat_context = MagicMock()
        bot.chat_context.bot_name = "TestBot"
        bot.chat_context.client = MagicMock()
        bot.chat_context.chats = {}
        bot.chat_context.search = MagicMock()

        mock_event = MagicMock()
        mock_event.text = "Hello"
        mock_event.square_chat_mid = "chat123"

        await bot.queue.put((mock_event, "square"))

        # Run worker for a short time
        async def stop_worker():
            await asyncio.sleep(0.1)
            bot._running = False

        await asyncio.gather(
            bot._message_worker(),
            stop_worker(),
        )

        assert bot.queue.empty()

    @pytest.mark.asyncio
    async def test_message_worker_handles_timeout(self):
        """Test worker handles timeout when queue is empty."""
        bot = ChatBot("TestBot")
        bot._running = True

        async def stop_worker():
            await asyncio.sleep(1.5)  # Let it timeout once
            bot._running = False

        # Should not raise
        await asyncio.gather(
            bot._message_worker(),
            stop_worker(),
        )
