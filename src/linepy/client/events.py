"""Event system for the LINE client."""

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")
# EventHandler can be async or sync (sync handlers that return None or coroutine)
EventHandler = Callable[..., Coroutine[Any, Any, None] | None]


class TypedEventEmitter:
    """
    A typed event emitter supporting async event handlers.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[EventHandler]] = defaultdict(list)
        self._waiters: dict[str, list[asyncio.Future[Any]]] = defaultdict(list)

    def on(self, event: str, *handlers: EventHandler) -> "TypedEventEmitter":
        """
        Register event handlers.

        Args:
            event: The event name
            *handlers: Handler coroutines to register

        Returns:
            Self for chaining
        """
        for handler in handlers:
            self._listeners[event].append(handler)
        return self

    def off(self, event: str, *handlers: EventHandler) -> "TypedEventEmitter":
        """
        Unregister event handlers.

        Args:
            event: The event name
            *handlers: Handler coroutines to unregister

        Returns:
            Self for chaining
        """
        for handler in handlers:
            if handler in self._listeners[event]:
                self._listeners[event].remove(handler)
        return self

    def emit(self, event: str, *args: Any, **kwargs: Any) -> "TypedEventEmitter":
        """
        Emit an event to all registered handlers.

        Args:
            event: The event name
            *args: Positional arguments to pass to handlers
            **kwargs: Keyword arguments to pass to handlers

        Returns:
            Self for chaining
        """
        # Notify waiters
        for future in self._waiters.pop(event, []):
            if not future.done():
                future.set_result(args)

        # Call handlers
        for handler in self._listeners[event]:
            if asyncio.iscoroutinefunction(handler):
                # Async handler - schedule as task if there's a running loop
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(handler(*args, **kwargs))
                except RuntimeError:
                    # No running event loop - use asyncio.run() for Python 3.10+
                    asyncio.run(handler(*args, **kwargs))
            else:
                # Sync handler - call directly
                result = handler(*args, **kwargs)
                # If handler returns a coroutine, schedule it
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)

        return self

    async def wait_for(self, event: str, timeout: float | None = None) -> tuple[Any, ...]:
        """
        Wait for an event to be emitted.

        Args:
            event: The event name to wait for
            timeout: Optional timeout in seconds

        Returns:
            The arguments passed to emit()

        Raises:
            asyncio.TimeoutError: If timeout is reached
        """
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiters[event].append(future)

        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            self._waiters[event].remove(future)
            raise
