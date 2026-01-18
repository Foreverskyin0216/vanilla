"""Tests for scheduler module."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from src.scheduler import (
    DEFAULT_TIMEZONE,
    ScheduledTask,
    Scheduler,
    TaskStatus,
    parse_cron_expression,
    parse_start_time,
)


class TestScheduledTask:
    """Tests for ScheduledTask dataclass."""

    def test_task_creation(self):
        """Test basic task creation."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello world",
            cron_expression="0 9 * * *",  # Every day at 9:00
            start_at=now,
        )
        assert task.id == "test-id"
        assert task.chat_id == "chat123"
        assert task.message == "Hello world"
        assert task.status == TaskStatus.PENDING
        assert task.triggered_count == 0
        assert task.max_triggers == 1
        assert task.cron_expression == "0 9 * * *"

    def test_next_trigger_at_calculated(self):
        """Test next_trigger_at is calculated from cron expression."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",  # Every minute
            start_at=now,
        )
        # Next trigger should be in the future
        assert task.next_trigger_at is not None
        assert task.next_trigger_at > now

    def test_next_trigger_at_completed(self):
        """Test next_trigger_at when task is completed."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            start_at=datetime.now(tz),
        )
        task.status = TaskStatus.COMPLETED
        task._calculate_next_trigger()
        assert task.next_trigger_at is None

    def test_remaining_triggers(self):
        """Test remaining_triggers calculation."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            start_at=datetime.now(tz),
            max_triggers=5,
        )
        assert task.remaining_triggers == 5
        task.triggered_count = 2
        assert task.remaining_triggers == 3

    def test_remaining_triggers_unlimited(self):
        """Test remaining_triggers with unlimited (-1)."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            start_at=datetime.now(tz),
            max_triggers=-1,  # Unlimited
        )
        assert task.remaining_triggers == "∞"
        assert task.is_unlimited is True

    def test_advance_trigger(self):
        """Test advance_trigger increments count."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        task = ScheduledTask(
            id="test-id",
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            start_at=datetime.now(tz),
            max_triggers=3,
        )
        assert task.triggered_count == 0
        task.advance_trigger()
        assert task.triggered_count == 1

    def test_to_readable_string(self):
        """Test readable string output."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        task = ScheduledTask(
            id="12345678-abcd-efgh",
            chat_id="chat123",
            message="Test message",
            cron_expression="0 9 * * *",
            start_at=datetime.now(tz),
            description="Test task",
        )
        readable = task.to_readable_string()
        assert "Task ID: 12345678" in readable
        assert "Description: Test task" in readable
        assert "Message: Test message" in readable
        assert "Cron: 0 9 * * *" in readable
        assert "Pending" in readable


class TestScheduler:
    """Tests for Scheduler class."""

    def test_scheduler_init(self):
        """Test scheduler initialization."""
        scheduler = Scheduler()
        assert len(scheduler.tasks) == 0
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_create_task(self):
        """Test task creation."""
        scheduler = Scheduler()

        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="0 9 * * *",
            description="Test",
        )

        assert task.id in scheduler.tasks
        assert task.chat_id == "chat123"
        assert task.message == "Hello"
        assert task.cron_expression == "0 9 * * *"

    @pytest.mark.asyncio
    async def test_create_task_invalid_cron(self):
        """Test task creation with invalid cron expression."""
        scheduler = Scheduler()

        with pytest.raises(ValueError):
            await scheduler.create_task(
                chat_id="chat123",
                message="Hello",
                cron_expression="invalid cron",
            )

    @pytest.mark.asyncio
    async def test_create_task_unlimited(self):
        """Test task creation with unlimited triggers."""
        scheduler = Scheduler()

        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            max_triggers=-1,
        )

        assert task.max_triggers == -1
        assert task.is_unlimited is True

    @pytest.mark.asyncio
    async def test_get_task(self):
        """Test getting a task by ID."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
        )

        retrieved = scheduler.get_task(task.id)
        assert retrieved == task

        not_found = scheduler.get_task("nonexistent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_get_tasks_for_chat(self):
        """Test getting tasks for a specific chat."""
        scheduler = Scheduler()

        await scheduler.create_task(chat_id="chat1", message="A", cron_expression="* * * * *")
        await scheduler.create_task(chat_id="chat1", message="B", cron_expression="* * * * *")
        await scheduler.create_task(chat_id="chat2", message="C", cron_expression="* * * * *")

        chat1_tasks = scheduler.get_tasks_for_chat("chat1")
        assert len(chat1_tasks) == 2

        chat2_tasks = scheduler.get_tasks_for_chat("chat2")
        assert len(chat2_tasks) == 1

    @pytest.mark.asyncio
    async def test_get_pending_tasks(self):
        """Test getting pending tasks."""
        scheduler = Scheduler()

        task1 = await scheduler.create_task(
            chat_id="chat1", message="A", cron_expression="* * * * *"
        )
        task2 = await scheduler.create_task(
            chat_id="chat1", message="B", cron_expression="* * * * *"
        )
        task2.status = TaskStatus.COMPLETED

        pending = scheduler.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0] == task1

    @pytest.mark.asyncio
    async def test_create_system_task(self):
        """Test creating a system task."""
        scheduler = Scheduler()

        async def dummy_callback():
            pass

        task = scheduler.create_system_task(
            task_id="system:test",
            callback=dummy_callback,
            cron_expression="0 3 * * *",  # Every day at 3 AM
            max_triggers=-1,  # Unlimited
            description="Test system task",
        )

        assert task.id == "system:test"
        assert task.is_system is True
        assert task.callback is dummy_callback
        assert task.chat_id == "system"
        assert task.max_triggers == -1

    @pytest.mark.asyncio
    async def test_system_task_not_in_user_list(self):
        """Test that system tasks are hidden from user-facing list."""
        scheduler = Scheduler()

        # Create regular task
        await scheduler.create_task(
            chat_id="chat1",
            message="User message",
            cron_expression="* * * * *",
            description="User task",
        )

        # Create system task
        async def dummy_callback():
            pass

        scheduler.create_system_task(
            task_id="system:cleanup",
            callback=dummy_callback,
            cron_expression="0 3 * * *",
            description="System cleanup",
        )

        # list_tasks should only show user task by default
        result = scheduler.list_tasks(chat_id="chat1")
        assert "User task" in result
        assert "System cleanup" not in result

        # get_tasks_for_chat should only return user tasks by default
        tasks = scheduler.get_tasks_for_chat("chat1")
        assert len(tasks) == 1
        assert tasks[0].description == "User task"

        # With include_system=True, system tasks should be visible
        all_tasks = scheduler.get_tasks_for_chat("system", include_system=True)
        assert len(all_tasks) == 1
        assert all_tasks[0].is_system is True

    @pytest.mark.asyncio
    async def test_execute_system_task(self):
        """Test executing a system task with callback."""
        scheduler = Scheduler()

        # Track callback execution
        callback_executed = []

        async def test_callback():
            callback_executed.append(True)

        task = scheduler.create_system_task(
            task_id="system:test",
            callback=test_callback,
            cron_expression="* * * * *",
            max_triggers=1,
            description="Test",
        )

        await scheduler._execute_task(task)

        assert len(callback_executed) == 1
        assert task.triggered_count == 1
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Test cancelling a task."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="* * * * *",
        )

        result = await scheduler.cancel_task(task.id)
        assert result is True
        assert task.status == TaskStatus.CANCELLED

        # Can't cancel already cancelled task
        result = await scheduler.cancel_task(task.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_update_task_message(self):
        """Test updating task message."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Original message",
            cron_expression="0 9 * * *",
        )

        updated = await scheduler.update_task(task.id, message="New message")
        assert updated is not None
        assert updated.message == "New message"
        assert updated.cron_expression == "0 9 * * *"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_task_cron(self):
        """Test updating task cron expression."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="0 9 * * *",
        )
        original_next_trigger = task.next_trigger_at

        updated = await scheduler.update_task(task.id, cron_expression="0 14 * * *")
        assert updated is not None
        assert updated.cron_expression == "0 14 * * *"
        assert updated.message == "Hello"  # Unchanged
        # Next trigger should be recalculated
        assert updated.next_trigger_at != original_next_trigger

    @pytest.mark.asyncio
    async def test_update_task_description(self):
        """Test updating task description."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="0 9 * * *",
            description="Old description",
        )

        updated = await scheduler.update_task(task.id, description="New description")
        assert updated is not None
        assert updated.description == "New description"

    @pytest.mark.asyncio
    async def test_update_task_multiple_fields(self):
        """Test updating multiple fields at once."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Old",
            cron_expression="0 9 * * *",
            description="Old desc",
        )

        updated = await scheduler.update_task(
            task.id,
            message="New message",
            cron_expression="0 18 * * *",
            description="New desc",
        )
        assert updated is not None
        assert updated.message == "New message"
        assert updated.cron_expression == "0 18 * * *"
        assert updated.description == "New desc"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self):
        """Test updating non-existent task."""
        scheduler = Scheduler()
        result = await scheduler.update_task("nonexistent", message="Test")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_completed(self):
        """Test cannot update completed task."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="* * * * *",
        )
        task.status = TaskStatus.COMPLETED

        result = await scheduler.update_task(task.id, message="New")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_invalid_cron(self):
        """Test updating with invalid cron expression."""
        scheduler = Scheduler()
        task = await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="0 9 * * *",
        )

        with pytest.raises(ValueError):
            await scheduler.update_task(task.id, cron_expression="invalid cron")

    def test_list_tasks_empty(self):
        """Test listing tasks when empty."""
        scheduler = Scheduler()
        result = scheduler.list_tasks()
        assert "No scheduled tasks" in result

    @pytest.mark.asyncio
    async def test_list_tasks_with_tasks(self):
        """Test listing tasks."""
        scheduler = Scheduler()
        await scheduler.create_task(
            chat_id="chat1",
            message="Hello",
            cron_expression="0 9 * * *",
            description="Test task",
        )

        result = scheduler.list_tasks()
        assert "Pending Tasks" in result
        assert "Test task" in result

    @pytest.mark.asyncio
    async def test_execute_task(self):
        """Test task execution."""
        scheduler = Scheduler()
        sender = AsyncMock()
        scheduler.set_message_sender(sender)

        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
        )

        await scheduler._execute_task(task)

        sender.assert_called_once_with("chat123", "Hello")
        assert task.triggered_count == 1
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_task_multiple_triggers(self):
        """Test task with multiple triggers."""
        scheduler = Scheduler()
        sender = AsyncMock()
        scheduler.set_message_sender(sender)

        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            max_triggers=3,
        )

        await scheduler._execute_task(task)
        assert task.triggered_count == 1
        assert task.status == TaskStatus.PENDING

        await scheduler._execute_task(task)
        assert task.triggered_count == 2
        assert task.status == TaskStatus.PENDING

        await scheduler._execute_task(task)
        assert task.triggered_count == 3
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_task_unlimited(self):
        """Test task with unlimited triggers."""
        scheduler = Scheduler()
        sender = AsyncMock()
        scheduler.set_message_sender(sender)

        task = await scheduler.create_task(
            chat_id="chat123",
            message="Hello",
            cron_expression="* * * * *",
            max_triggers=-1,  # Unlimited
        )

        # Execute multiple times
        for _ in range(5):
            await scheduler._execute_task(task)

        assert task.triggered_count == 5
        assert task.status == TaskStatus.PENDING  # Still pending, never completes

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping the scheduler."""
        scheduler = Scheduler()
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._worker_task is not None

        # Let the worker run briefly
        await asyncio.sleep(0.1)

        await scheduler.stop()
        assert scheduler._running is False


class TestParseCronExpression:
    """Tests for parse_cron_expression function."""

    def test_valid_every_minute(self):
        """Test every minute cron."""
        result = parse_cron_expression("* * * * *")
        assert result == "* * * * *"

    def test_valid_every_hour(self):
        """Test every hour cron."""
        result = parse_cron_expression("0 * * * *")
        assert result == "0 * * * *"

    def test_valid_daily(self):
        """Test daily at 9 AM cron."""
        result = parse_cron_expression("0 9 * * *")
        assert result == "0 9 * * *"

    def test_valid_every_5_minutes(self):
        """Test every 5 minutes cron."""
        result = parse_cron_expression("*/5 * * * *")
        assert result == "*/5 * * * *"

    def test_valid_weekly(self):
        """Test weekly on Monday cron."""
        result = parse_cron_expression("0 9 * * 1")
        assert result == "0 9 * * 1"

    def test_valid_multiple_hours(self):
        """Test cron with multiple hours."""
        result = parse_cron_expression("0 9,18 * * *")
        assert result == "0 9,18 * * *"

    def test_valid_monthly(self):
        """Test monthly on 1st day cron."""
        result = parse_cron_expression("0 9 1 * *")
        assert result == "0 9 1 * *"

    def test_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError):
            parse_cron_expression("invalid")

    def test_invalid_too_few_fields(self):
        """Test too few fields raises error."""
        with pytest.raises(ValueError):
            parse_cron_expression("* * *")

    def test_strips_whitespace(self):
        """Test whitespace is stripped."""
        result = parse_cron_expression("  * * * * *  ")
        assert result == "* * * * *"


class TestParseStartTime:
    """Tests for parse_start_time function."""

    def test_now(self):
        """Test parsing 'now'."""
        result = parse_start_time("now")
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        diff = abs((result - now).total_seconds())
        assert diff < 2  # Within 2 seconds

    def test_time_only(self):
        """Test parsing time only."""
        result = parse_start_time("14:30")
        assert result.hour == 14
        assert result.minute == 30

    def test_full_datetime(self):
        """Test parsing full datetime."""
        result = parse_start_time("2025-06-15 14:30")
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

    def test_case_insensitive_now(self):
        """Test 'NOW' works too."""
        result = parse_start_time("NOW")
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        diff = abs((result - now).total_seconds())
        assert diff < 2

    def test_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError):
            parse_start_time("invalid")

    def test_invalid_time_format(self):
        """Test invalid time format."""
        with pytest.raises(ValueError):
            parse_start_time("25:99")
