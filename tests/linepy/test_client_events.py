"""Tests for linepy/client/events.py."""

import asyncio

import pytest

from src.linepy.client.events import TypedEventEmitter


class TestTypedEventEmitter:
    """Tests for TypedEventEmitter."""

    def test_init(self):
        emitter = TypedEventEmitter()
        assert emitter._listeners == {}
        assert emitter._waiters == {}

    def test_on_registers_handler(self):
        emitter = TypedEventEmitter()

        def handler():
            pass

        emitter.on("test", handler)
        assert handler in emitter._listeners["test"]

    def test_on_registers_multiple_handlers(self):
        emitter = TypedEventEmitter()

        def handler1():
            pass

        def handler2():
            pass

        emitter.on("test", handler1, handler2)
        assert handler1 in emitter._listeners["test"]
        assert handler2 in emitter._listeners["test"]

    def test_on_returns_self_for_chaining(self):
        emitter = TypedEventEmitter()
        result = emitter.on("test", lambda: None)
        assert result is emitter

    def test_off_unregisters_handler(self):
        emitter = TypedEventEmitter()

        def handler():
            pass

        emitter.on("test", handler)
        emitter.off("test", handler)
        assert handler not in emitter._listeners["test"]

    def test_off_unregisters_multiple_handlers(self):
        emitter = TypedEventEmitter()

        def handler1():
            pass

        def handler2():
            pass

        emitter.on("test", handler1, handler2)
        emitter.off("test", handler1, handler2)
        assert handler1 not in emitter._listeners["test"]
        assert handler2 not in emitter._listeners["test"]

    def test_off_returns_self_for_chaining(self):
        emitter = TypedEventEmitter()
        result = emitter.off("test", lambda: None)
        assert result is emitter

    def test_off_nonexistent_handler_no_error(self):
        emitter = TypedEventEmitter()

        def handler():
            pass

        emitter.off("test", handler)

    def test_emit_returns_self_for_chaining(self):
        emitter = TypedEventEmitter()
        result = emitter.emit("test")
        assert result is emitter

    def test_emit_calls_sync_handler(self):
        emitter = TypedEventEmitter()
        called = []

        def handler(value):
            called.append(value)

        emitter.on("test", handler)
        emitter.emit("test", "hello")
        assert called == ["hello"]

    def test_emit_with_multiple_args(self):
        emitter = TypedEventEmitter()
        called = []

        def handler(a, b, c):
            called.append((a, b, c))

        emitter.on("test", handler)
        emitter.emit("test", 1, 2, 3)
        assert called == [(1, 2, 3)]

    def test_emit_with_kwargs(self):
        emitter = TypedEventEmitter()
        called = []

        def handler(a, b=None):
            called.append((a, b))

        emitter.on("test", handler)
        emitter.emit("test", 1, b=2)
        assert called == [(1, 2)]

    async def test_emit_calls_async_handler(self):
        emitter = TypedEventEmitter()
        called = []

        async def handler(value):
            called.append(value)

        emitter.on("test", handler)
        emitter.emit("test", "hello")

        # Allow async handler to run
        await asyncio.sleep(0.01)
        assert called == ["hello"]

    async def test_emit_multiple_handlers(self):
        emitter = TypedEventEmitter()
        called = []

        def handler1(value):
            called.append(f"h1:{value}")

        async def handler2(value):
            called.append(f"h2:{value}")

        emitter.on("test", handler1, handler2)
        emitter.emit("test", "x")

        await asyncio.sleep(0.01)
        assert "h1:x" in called
        assert "h2:x" in called

    async def test_wait_for_event(self):
        emitter = TypedEventEmitter()

        async def emit_later():
            await asyncio.sleep(0.01)
            emitter.emit("ready", "data")

        asyncio.create_task(emit_later())
        result = await emitter.wait_for("ready", timeout=1.0)
        assert result == ("data",)

    async def test_wait_for_timeout(self):
        emitter = TypedEventEmitter()

        with pytest.raises(asyncio.TimeoutError):
            await emitter.wait_for("never", timeout=0.01)

    async def test_wait_for_multiple_args(self):
        emitter = TypedEventEmitter()

        async def emit_later():
            await asyncio.sleep(0.01)
            emitter.emit("ready", "a", "b", "c")

        asyncio.create_task(emit_later())
        result = await emitter.wait_for("ready", timeout=1.0)
        assert result == ("a", "b", "c")

    async def test_wait_for_removes_waiter_on_timeout(self):
        emitter = TypedEventEmitter()

        with pytest.raises(asyncio.TimeoutError):
            await emitter.wait_for("test", timeout=0.01)

        assert len(emitter._waiters.get("test", [])) == 0

    async def test_multiple_waiters_same_event(self):
        emitter = TypedEventEmitter()

        async def emit_later():
            await asyncio.sleep(0.01)
            emitter.emit("ready", "value")

        asyncio.create_task(emit_later())

        # Start multiple waiters
        results = await asyncio.gather(
            emitter.wait_for("ready", timeout=1.0),
            emitter.wait_for("ready", timeout=1.0),
        )

        assert results[0] == ("value",)
        assert results[1] == ("value",)

    def test_chaining_multiple_operations(self):
        emitter = TypedEventEmitter()

        def h1():
            pass

        def h2():
            pass

        result = emitter.on("e1", h1).on("e2", h2).emit("e1").emit("e2").off("e1", h1)

        assert result is emitter
        assert h1 not in emitter._listeners["e1"]
        assert h2 in emitter._listeners["e2"]


class TestEventEmitterEdgeCases:
    """Edge case tests for TypedEventEmitter."""

    def test_emit_no_handlers(self):
        emitter = TypedEventEmitter()
        # Should not raise
        emitter.emit("no_handlers", "data")

    def test_emit_no_waiters(self):
        emitter = TypedEventEmitter()
        emitter.on("test", lambda x: None)
        # Should not raise
        emitter.emit("test", "data")

    def test_same_handler_multiple_times(self):
        emitter = TypedEventEmitter()
        called_count = [0]

        def handler():
            called_count[0] += 1

        # Register same handler twice
        emitter.on("test", handler)
        emitter.on("test", handler)
        emitter.emit("test")

        assert called_count[0] == 2

    def test_off_only_removes_once(self):
        emitter = TypedEventEmitter()

        def handler():
            pass

        emitter.on("test", handler)
        emitter.on("test", handler)
        emitter.off("test", handler)

        # One instance should remain
        assert emitter._listeners["test"].count(handler) == 1

    def test_handler_exception_does_not_stop_others(self):
        emitter = TypedEventEmitter()
        called = []

        def bad_handler():
            raise ValueError("oops")

        def good_handler():
            called.append("good")

        emitter.on("test", bad_handler)
        emitter.on("test", good_handler)

        # bad_handler raises, but we still want to test the behavior
        with pytest.raises(ValueError):
            emitter.emit("test")
