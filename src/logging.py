"""Async logging utilities for the Vanilla chatbot."""

import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

# Thread pool for async logging
_log_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="async_logger")


class AsyncLogger:
    """
    Async wrapper for Python's logging module.

    This wrapper provides both sync and async logging methods.
    Use async methods (ainfo, adebug, etc.) in async contexts for non-blocking logging.
    Use sync methods (info, debug, etc.) when await is not possible (e.g., in callbacks).
    """

    def __init__(self, name: str):
        """
        Initialize the async logger.

        Args:
            name: Logger name (typically __name__).
        """
        self._logger = logging.getLogger(name)

    def _log_sync(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """Synchronous logging call."""
        self._logger.log(level, msg, *args, **kwargs)

    async def _alog(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """Async logging call that runs in thread pool."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            _log_executor,
            partial(self._log_sync, level, msg, *args, **kwargs),
        )

    # Sync methods (use in callbacks, lambdas, or when await is not possible)
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message (sync)."""
        self._log_sync(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message (sync)."""
        self._log_sync(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message (sync)."""
        self._log_sync(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message (sync)."""
        self._log_sync(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message with exception info (sync)."""
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        self._log_sync(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical message (sync)."""
        self._log_sync(logging.CRITICAL, msg, *args, **kwargs)

    # Async methods (use in async functions for non-blocking logging)
    async def adebug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message (async, non-blocking)."""
        await self._alog(logging.DEBUG, msg, *args, **kwargs)

    async def ainfo(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message (async, non-blocking)."""
        await self._alog(logging.INFO, msg, *args, **kwargs)

    async def awarning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message (async, non-blocking)."""
        await self._alog(logging.WARNING, msg, *args, **kwargs)

    async def aerror(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message (async, non-blocking)."""
        await self._alog(logging.ERROR, msg, *args, **kwargs)

    async def aexception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message with exception info (async, non-blocking)."""
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        await self._alog(logging.ERROR, msg, *args, **kwargs)

    async def acritical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical message (async, non-blocking)."""
        await self._alog(logging.CRITICAL, msg, *args, **kwargs)

    @property
    def level(self) -> int:
        """Get the effective log level."""
        return self._logger.getEffectiveLevel()

    def setLevel(self, level: int) -> None:
        """Set the log level."""
        self._logger.setLevel(level)

    def isEnabledFor(self, level: int) -> bool:
        """Check if a log level is enabled."""
        return self._logger.isEnabledFor(level)


def get_logger(name: str) -> AsyncLogger:
    """
    Get an async logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        AsyncLogger instance.
    """
    return AsyncLogger(name)


def configure_logging(level: str = "INFO") -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # Reduce verbosity of noisy libraries
    for lib in ["httpx", "httpcore", "langchain", "langgraph", "openai"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
