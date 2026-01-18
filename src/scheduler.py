"""Scheduler module for managing timed tasks and notifications with PostgreSQL persistence."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from zoneinfo import ZoneInfo

import psycopg
from croniter import croniter

from src.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

DEFAULT_TIMEZONE = "Asia/Taipei"


class TaskStatus(str, Enum):
    """Status of a scheduled task."""

    PENDING = "pending"  # Waiting to execute
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished
    CANCELLED = "cancelled"  # Cancelled by user


@dataclass
class ScheduledTask:
    """A scheduled task with timing and execution details.

    Supports cron-based scheduling for flexible timing configurations.
    """

    id: str
    chat_id: str  # Target chat ID
    message: str  # Message to send
    cron_expression: str  # Cron expression (minute hour day month weekday)
    start_at: datetime  # Start time for scheduling
    max_triggers: int = 1  # Max trigger count (-1 for unlimited)
    triggered_count: int = 0  # Number of times triggered
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo(DEFAULT_TIMEZONE)))
    description: str = ""  # Task description
    is_system: bool = False  # System task (hidden from users)
    callback: Callable[[], Coroutine[Any, Any, None]] | None = (
        None  # Custom callback (for system tasks)
    )
    _next_trigger: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Calculate initial next trigger time."""
        self._calculate_next_trigger()

    def _calculate_next_trigger(self) -> None:
        """Calculate the next trigger time based on cron expression."""
        if self.status != TaskStatus.PENDING:
            self._next_trigger = None
            return

        # Check if max triggers reached (unless unlimited with -1)
        if self.max_triggers != -1 and self.triggered_count >= self.max_triggers:
            self._next_trigger = None
            return

        try:
            tz = ZoneInfo(DEFAULT_TIMEZONE)
            # Use start_at as base time for first trigger, or current time for subsequent
            if self.triggered_count == 0:
                base_time = self.start_at
            else:
                base_time = datetime.now(tz)

            cron = croniter(self.cron_expression, base_time)
            self._next_trigger = cron.get_next(datetime)
            # Ensure timezone is set
            if self._next_trigger.tzinfo is None:
                self._next_trigger = self._next_trigger.replace(tzinfo=tz)
        except Exception:
            self._next_trigger = None

    @property
    def next_trigger_at(self) -> datetime | None:
        """Get the next trigger time."""
        return self._next_trigger

    @property
    def remaining_triggers(self) -> int | str:
        """Get remaining trigger count."""
        if self.max_triggers == -1:
            return "∞"
        return max(0, self.max_triggers - self.triggered_count)

    @property
    def is_unlimited(self) -> bool:
        """Check if task has unlimited triggers."""
        return self.max_triggers == -1

    def advance_trigger(self) -> None:
        """Advance to next trigger after execution."""
        self.triggered_count += 1
        self._calculate_next_trigger()

    def to_readable_string(self) -> str:
        """Convert task to a human-readable string."""
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        start_str = self.start_at.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")

        parts = [
            f"Task ID: {self.id[:8]}",
            f"Description: {self.description or 'N/A'}",
            f"Message: {self.message[:50]}{'...' if len(self.message) > 50 else ''}",
            f"Cron: {self.cron_expression}",
            f"Start time: {start_str}",
        ]

        if self._next_trigger:
            next_str = self._next_trigger.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            parts.append(f"Next trigger: {next_str}")

        remaining = self.remaining_triggers
        if self.max_triggers == -1:
            parts.append("Remaining: ∞ (unlimited)")
        else:
            parts.append(f"Remaining: {remaining}/{self.max_triggers}")

        parts.append(f"Status: {self._status_to_display()}")

        return "\n".join(parts)

    def _status_to_display(self) -> str:
        """Convert status to display string."""
        status_map = {
            TaskStatus.PENDING: "Pending",
            TaskStatus.RUNNING: "Running",
            TaskStatus.COMPLETED: "Completed",
            TaskStatus.CANCELLED: "Cancelled",
        }
        return status_map.get(self.status, str(self.status))


# Type alias for message sender callback
MessageSender = Callable[[str, str], Coroutine[Any, Any, None]]


class Scheduler:
    """
    Scheduler for managing timed tasks with cron-based scheduling and PostgreSQL persistence.

    Handles creation, execution, and management of scheduled tasks.
    Tasks are persisted to PostgreSQL so they survive service restarts.
    """

    def __init__(self, postgres_url: str | None = None, timezone: str = DEFAULT_TIMEZONE):
        """
        Initialize the scheduler.

        Args:
            postgres_url: PostgreSQL connection string for persistence.
            timezone: Default timezone for scheduling.
        """
        self.timezone = ZoneInfo(timezone)
        self.tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._message_sender: MessageSender | None = None
        self._postgres_url = postgres_url

    async def setup(self) -> None:
        """Set up the scheduler database table."""
        if not self._postgres_url:
            await logger.awarning("No PostgreSQL URL provided, tasks will not be persisted")
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS scheduled_tasks (
                            id VARCHAR(36) PRIMARY KEY,
                            chat_id VARCHAR(255) NOT NULL,
                            message TEXT NOT NULL,
                            cron_expression VARCHAR(100) NOT NULL,
                            start_at TIMESTAMPTZ NOT NULL,
                            max_triggers INTEGER NOT NULL DEFAULT 1,
                            triggered_count INTEGER NOT NULL DEFAULT 0,
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            description TEXT DEFAULT '',
                            is_system BOOLEAN NOT NULL DEFAULT FALSE
                        )
                    """)
                    # Create index for efficient querying
                    await cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status
                        ON scheduled_tasks(status)
                    """)
                    await cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_chat_id
                        ON scheduled_tasks(chat_id)
                    """)
                    await conn.commit()
            await logger.ainfo("Scheduler database table set up successfully")
        except Exception as e:
            await logger.aerror(f"Failed to set up scheduler database: {e}")
            raise

    async def load_tasks(self) -> None:
        """Load all pending tasks from the database on startup."""
        if not self._postgres_url:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    # Load pending and running tasks (running tasks should be retried)
                    await cur.execute("""
                        SELECT id, chat_id, message, cron_expression, start_at,
                               max_triggers, triggered_count, status, created_at,
                               description, is_system
                        FROM scheduled_tasks
                        WHERE status IN ('pending', 'running')
                          AND is_system = FALSE
                    """)
                    rows = await cur.fetchall()

                    for row in rows:
                        task = ScheduledTask(
                            id=row[0],
                            chat_id=row[1],
                            message=row[2],
                            cron_expression=row[3],
                            start_at=row[4],
                            max_triggers=row[5],
                            triggered_count=row[6],
                            status=TaskStatus(row[7]),
                            created_at=row[8],
                            description=row[9] or "",
                            is_system=row[10],
                        )
                        # Reset running tasks to pending
                        if task.status == TaskStatus.RUNNING:
                            task.status = TaskStatus.PENDING
                        self.tasks[task.id] = task

                    await logger.ainfo(f"Loaded {len(rows)} tasks from database")
        except Exception as e:
            await logger.aerror(f"Failed to load tasks from database: {e}")

    async def _save_task(self, task: ScheduledTask) -> None:
        """Save a task to the database."""
        if not self._postgres_url or task.is_system:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO scheduled_tasks
                            (id, chat_id, message, cron_expression, start_at,
                             max_triggers, triggered_count, status, created_at,
                             description, is_system)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            triggered_count = EXCLUDED.triggered_count,
                            status = EXCLUDED.status
                        """,
                        (
                            task.id,
                            task.chat_id,
                            task.message,
                            task.cron_expression,
                            task.start_at,
                            task.max_triggers,
                            task.triggered_count,
                            task.status.value,
                            task.created_at,
                            task.description,
                            task.is_system,
                        ),
                    )
                    await conn.commit()
        except Exception as e:
            await logger.aerror(f"Failed to save task {task.id}: {e}")

    async def _update_task_status(self, task: ScheduledTask) -> None:
        """Update task status and triggered_count in the database."""
        if not self._postgres_url or task.is_system:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE scheduled_tasks
                        SET status = %s, triggered_count = %s
                        WHERE id = %s
                        """,
                        (task.status.value, task.triggered_count, task.id),
                    )
                    await conn.commit()
        except Exception as e:
            await logger.aerror(f"Failed to update task status {task.id}: {e}")

    def set_message_sender(self, sender: MessageSender) -> None:
        """
        Set the callback for sending messages.

        Args:
            sender: Async function that takes (chat_id, message) and sends the message.
        """
        self._message_sender = sender

    async def create_task(
        self,
        chat_id: str,
        message: str,
        cron_expression: str,
        start_at: datetime | None = None,
        max_triggers: int = 1,
        description: str = "",
    ) -> ScheduledTask:
        """
        Create a new scheduled task with cron-based scheduling.

        Args:
            chat_id: Target chat ID.
            message: Message to send.
            cron_expression: Cron expression (minute hour day month weekday).
            start_at: Start time for scheduling (default: now).
            max_triggers: Maximum number of triggers (-1 for unlimited).
            description: Task description.

        Returns:
            The created task.

        Raises:
            ValueError: If cron expression is invalid.
        """
        # Validate cron expression
        if not croniter.is_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        if start_at is None:
            start_at = datetime.now(self.timezone)

        task_id = str(uuid.uuid4())
        task = ScheduledTask(
            id=task_id,
            chat_id=chat_id,
            message=message,
            cron_expression=cron_expression,
            start_at=start_at,
            max_triggers=max_triggers,
            description=description,
        )
        self.tasks[task_id] = task

        # Persist to database
        await self._save_task(task)

        await logger.ainfo(
            f"Created task {task_id[:8]}: chat={chat_id[:8]}, cron={cron_expression}, "
            f"next_trigger={task.next_trigger_at}, max={max_triggers}"
        )
        return task

    def create_system_task(
        self,
        task_id: str,
        callback: Callable[[], Coroutine[Any, Any, None]],
        cron_expression: str,
        start_at: datetime | None = None,
        max_triggers: int = -1,
        description: str = "",
    ) -> ScheduledTask:
        """
        Create a system task that won't be visible to users.

        System tasks use a callback instead of sending messages.
        System tasks are NOT persisted to the database.

        Args:
            task_id: Unique task ID (should be descriptive, e.g., "system:cleanup").
            callback: Async function to execute.
            cron_expression: Cron expression for scheduling.
            start_at: Start time for scheduling (default: now).
            max_triggers: Maximum number of triggers (-1 for unlimited).
            description: Task description.

        Returns:
            The created task.
        """
        # Validate cron expression
        if not croniter.is_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        # Remove existing task with same ID if any
        if task_id in self.tasks:
            del self.tasks[task_id]

        if start_at is None:
            start_at = datetime.now(self.timezone)

        task = ScheduledTask(
            id=task_id,
            chat_id="system",
            message="",
            cron_expression=cron_expression,
            start_at=start_at,
            max_triggers=max_triggers,
            description=description,
            is_system=True,
            callback=callback,
        )
        self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_tasks_for_chat(self, chat_id: str, include_system: bool = False) -> list[ScheduledTask]:
        """Get all tasks for a specific chat.

        Args:
            chat_id: The chat ID to filter by.
            include_system: Whether to include system tasks (default: False).
        """
        return [
            t
            for t in self.tasks.values()
            if t.chat_id == chat_id and (include_system or not t.is_system)
        ]

    def get_pending_tasks(self, include_system: bool = True) -> list[ScheduledTask]:
        """Get all pending tasks.

        Args:
            include_system: Whether to include system tasks (default: True).
        """
        return [
            t
            for t in self.tasks.values()
            if t.status == TaskStatus.PENDING and (include_system or not t.is_system)
        ]

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.

        Args:
            task_id: Task ID to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        task = self.tasks.get(task_id)
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            await self._update_task_status(task)
            return True
        return False

    async def update_task(
        self,
        task_id: str,
        message: str | None = None,
        cron_expression: str | None = None,
        description: str | None = None,
    ) -> ScheduledTask | None:
        """
        Update an existing task's message, cron expression, or description.

        Args:
            task_id: Task ID to update.
            message: New message content (optional).
            cron_expression: New cron expression (optional).
            description: New description (optional).

        Returns:
            Updated task if successful, None if not found or not pending.

        Raises:
            ValueError: If cron expression is invalid.
        """
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return None

        # Validate cron expression if provided
        if cron_expression is not None:
            if not croniter.is_valid(cron_expression):
                raise ValueError(f"Invalid cron expression: {cron_expression}")
            task.cron_expression = cron_expression
            # Recalculate next trigger time
            task._calculate_next_trigger()

        if message is not None:
            task.message = message

        if description is not None:
            task.description = description

        # Persist changes to database
        await self._save_task_full(task)

        await logger.ainfo(
            f"Updated task {task_id[:8]}: message={message is not None}, "
            f"cron={cron_expression is not None}, desc={description is not None}"
        )
        return task

    async def _save_task_full(self, task: ScheduledTask) -> None:
        """Save all task fields to the database (for updates)."""
        if not self._postgres_url or task.is_system:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE scheduled_tasks
                        SET message = %s, cron_expression = %s, description = %s,
                            triggered_count = %s, status = %s
                        WHERE id = %s
                        """,
                        (
                            task.message,
                            task.cron_expression,
                            task.description,
                            task.triggered_count,
                            task.status.value,
                            task.id,
                        ),
                    )
                    await conn.commit()
        except Exception as e:
            await logger.aerror(f"Failed to save task {task.id}: {e}")

    def list_tasks(self, chat_id: str | None = None, include_system: bool = False) -> str:
        """
        List tasks as a readable string.

        Args:
            chat_id: Optional chat ID to filter tasks.
            include_system: Whether to include system tasks (default: False).

        Returns:
            Formatted string of tasks.
        """
        if chat_id:
            tasks = self.get_tasks_for_chat(chat_id, include_system=include_system)
        else:
            tasks = [t for t in self.tasks.values() if include_system or not t.is_system]

        if not tasks:
            return "No scheduled tasks."

        pending = [t for t in tasks if t.status == TaskStatus.PENDING]
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        cancelled = [t for t in tasks if t.status == TaskStatus.CANCELLED]

        parts = []
        if pending:
            parts.append(f"[Pending Tasks] ({len(pending)} tasks)")
            for t in pending:
                parts.append(t.to_readable_string())
                parts.append("---")

        if completed:
            parts.append(f"\n[Completed Tasks] ({len(completed)} tasks)")
            for t in completed[-5:]:  # Only show last 5
                parts.append(t.to_readable_string())
                parts.append("---")

        if cancelled:
            parts.append(f"\n[Cancelled Tasks] ({len(cancelled)} tasks)")
            for t in cancelled[-3:]:  # Only show last 3
                parts.append(t.to_readable_string())
                parts.append("---")

        return "\n".join(parts)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a single task."""
        await logger.ainfo(f"Executing task {task.id[:8]}: {task.description or task.message[:30]}")
        try:
            task.status = TaskStatus.RUNNING
            await self._update_task_status(task)

            # System tasks use callback, regular tasks use message sender
            if task.is_system and task.callback:
                await logger.adebug(f"Task {task.id[:8]} is system task, calling callback")
                await task.callback()
            elif self._message_sender:
                await logger.adebug(
                    f"Task {task.id[:8]} sending message to {task.chat_id[:8]}: {task.message[:50]}"
                )
                await self._message_sender(task.chat_id, task.message)
            else:
                await logger.awarning(f"No message sender set, cannot execute task {task.id}")
                task.status = TaskStatus.PENDING
                await self._update_task_status(task)
                return

            # Increment triggered count
            task.triggered_count += 1
            await logger.ainfo(
                f"Task {task.id[:8]} executed successfully, triggered_count={task.triggered_count}"
            )

            # Check if task should continue
            if task.max_triggers != -1 and task.triggered_count >= task.max_triggers:
                task.status = TaskStatus.COMPLETED
                task._next_trigger = None
                await logger.ainfo(f"Task {task.id[:8]} completed (max triggers reached)")
            else:
                # Set status to PENDING first, then calculate next trigger
                task.status = TaskStatus.PENDING
                task._calculate_next_trigger()

            await self._update_task_status(task)
        except Exception as e:
            await logger.aerror(f"Error executing task {task.id}: {e}", exc_info=True)
            task.status = TaskStatus.PENDING  # Retry on next check
            await self._update_task_status(task)

    async def _worker(self) -> None:
        """Background worker that checks and executes tasks."""
        await logger.ainfo("Scheduler worker started")
        while self._running:
            try:
                now = datetime.now(self.timezone)

                for task in list(self.tasks.values()):
                    if task.status != TaskStatus.PENDING:
                        continue

                    next_trigger = task.next_trigger_at
                    if next_trigger and next_trigger <= now:
                        await logger.adebug(
                            f"Task {task.id[:8]} ready to execute: "
                            f"next_trigger={next_trigger}, now={now}"
                        )
                        await self._execute_task(task)

                # Check every second
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                await logger.ainfo("Scheduler worker cancelled")
                break
            except Exception as e:
                await logger.aerror(f"Scheduler worker error: {e}", exc_info=True)
                await asyncio.sleep(1)
        await logger.ainfo("Scheduler worker stopped")

    async def start(self) -> None:
        """Start the scheduler worker."""
        if self._running:
            await logger.adebug("Scheduler already running")
            return

        # Set up database and load existing tasks
        await self.setup()
        await self.load_tasks()

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        await logger.ainfo("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
        await logger.ainfo("Scheduler stopped")


def parse_cron_expression(cron_str: str) -> str:
    """
    Parse and validate a cron expression.

    Cron format: minute hour day month weekday

    Examples:
    - "* * * * *" - Every minute
    - "0 * * * *" - Every hour
    - "0 9 * * *" - Every day at 9:00
    - "0 9 * * 1" - Every Monday at 9:00
    - "*/5 * * * *" - Every 5 minutes
    - "0 9,18 * * *" - At 9:00 and 18:00 every day
    - "0 9 1 * *" - First day of every month at 9:00

    Args:
        cron_str: Cron expression string.

    Returns:
        Validated cron expression.

    Raises:
        ValueError: If cron expression is invalid.
    """
    cron_str = cron_str.strip()

    if not croniter.is_valid(cron_str):
        raise ValueError(
            f"Invalid cron expression: {cron_str}\n"
            "Format: minute hour day month weekday\n"
            "Examples:\n"
            "  * * * * * - Every minute\n"
            "  0 * * * * - Every hour\n"
            "  0 9 * * * - Every day at 9:00\n"
            "  */5 * * * * - Every 5 minutes\n"
            "  0 9 * * 1 - Every Monday at 9:00"
        )

    return cron_str


def parse_start_time(time_str: str, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """
    Parse a start time string into a datetime.

    Supports formats:
    - "now" - Current time
    - "2024-01-15 14:30" - Absolute datetime
    - "14:30" - Today at this time (or tomorrow if past)

    Args:
        time_str: Time string to parse.
        timezone: Timezone for parsing.

    Returns:
        Parsed datetime.

    Raises:
        ValueError: If format is invalid.
    """
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)

    time_str = time_str.strip().lower()

    # "now" - current time
    if time_str == "now":
        return now

    # Time only: 14:30
    if ":" in time_str and len(time_str) <= 5:
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            from datetime import timedelta

            result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If time is in the past, schedule for tomorrow
            if result <= now:
                result += timedelta(days=1)
            return result
        except (ValueError, IndexError):
            raise ValueError(f"Invalid time format: {time_str}")

    # Full datetime: 2024-01-15 14:30
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        pass

    raise ValueError(
        f"Cannot parse time: {time_str} (supported formats: 'now', '14:30', '2024-01-15 14:30')"
    )
