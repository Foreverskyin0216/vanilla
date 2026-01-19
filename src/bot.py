"""ChatBot class for managing the LINE bot."""

import asyncio
import os
import time
from typing import Any

from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.checkpoint_cleanup import cleanup_old_checkpoints
from src.graph import VanillaContext, build_graph
from src.helpers import should_trigger_response
from src.linepy import Client, SquareMessage, TalkMessage, login_with_password
from src.logging import get_logger
from src.preferences import UserPreferencesStore
from src.scheduler import Scheduler
from src.search import Search
from src.types import ChatContext, ChatMessage

logger = get_logger(__name__)

# Default checkpoint retention period in days
CHECKPOINT_RETENTION_DAYS = 30

# System task ID for checkpoint cleanup
CLEANUP_TASK_ID = "system:checkpoint-cleanup"

# Backwards compatibility alias
SquareContext = ChatContext


class ChatBot:
    """
    Central orchestrator managing LINE client and conversation state.

    Handles both Square Chat (OpenChat) and Talk (Group/DM) integration
    with message queuing and integrates with LangGraph workflow for
    response generation. Both use the same graph.
    """

    def __init__(
        self,
        bot_name: str,
        device: str = "DESKTOPMAC",
        enable_square: bool = True,
        enable_talk: bool = True,
    ):
        """
        Initialize the chatbot.

        Args:
            bot_name: The bot's display name.
            device: Device type for LINE client.
            enable_square: Enable Square (OpenChat) message handling.
            enable_talk: Enable Talk (Group/DM) message handling.
        """
        self.bot_name = bot_name
        self.device = device
        self.enable_square = enable_square
        self.enable_talk = enable_talk
        self.client: Client | None = None
        self.checkpointer: AsyncPostgresSaver | None = None
        self.app: Any = None
        self.langfuse_handler = CallbackHandler()
        # Queue stores tuples of (event, chat_type)
        self.queue: asyncio.Queue[tuple[ChatMessage, str]] = asyncio.Queue()
        self.chat_context: ChatContext | None = None
        # Scheduler will be initialized in serve() with postgres_url
        self.scheduler: Scheduler | None = None
        # User preferences store for persistent user rules
        self.preferences_store: UserPreferencesStore | None = None
        self._running = False

    async def _init(self, checkpointer: AsyncPostgresSaver) -> None:
        """Initialize the bot components.

        Args:
            checkpointer: The PostgreSQL checkpointer for state persistence.
        """
        # Login to LINE
        self.client = await login_with_password(
            email=os.environ["LINE_EMAIL"],
            password=os.environ["LINE_PASSWORD"],
            device=self.device,
            on_pincode=lambda pin: logger.info(f"Enter PIN: {pin}"),
        )

        # Initialize context (shared for both Square and Talk)
        self.chat_context = ChatContext(
            bot_name=self.bot_name,
            client=self.client,
            chats={},
            search=Search(),
            scheduler=self.scheduler,
            preferences_store=self.preferences_store,
        )

        # Set up scheduler message sender
        self.scheduler.set_message_sender(self._send_scheduled_message)

        # Store checkpointer reference
        self.checkpointer = checkpointer

        # Build graph (shared for both Square and Talk)
        self.app = build_graph(self.checkpointer)

    async def _process_message(self, event: ChatMessage, chat_type: str) -> None:
        """
        Process a single message through the graph.

        Args:
            event: The message event (SquareMessage or TalkMessage).
            chat_type: Type of chat ("square" or "talk").
        """
        if not self.app or not self.chat_context:
            logger.warning("No app or chat_context, skipping message")
            return

        try:
            # Determine thread_id based on chat type
            if chat_type == "square" and isinstance(event, SquareMessage):
                thread_id = event.square_chat_mid
            else:
                # For Talk messages, use to_mid for groups/rooms, from_mid for DMs
                # to_type: 0=USER, 1=ROOM, 2=GROUP
                to_type = event.to_type
                if to_type in (1, 2):  # ROOM or GROUP
                    thread_id = event.to_mid
                else:
                    # DM: use from_mid if it's not our own message
                    thread_id = event.to_mid if event.is_my_message else event.from_mid

            # Check if thread_id is empty
            if not thread_id:
                logger.warning(f"Empty thread_id! to_type={getattr(event, 'to_type', 'N/A')}")
                return

            # Create context with the specific event and chat type
            chat_context = ChatContext(
                bot_name=self.chat_context.bot_name,
                client=self.chat_context.client,
                chats=self.chat_context.chats,
                search=self.chat_context.search,
                scheduler=self.chat_context.scheduler,
                preferences_store=self.chat_context.preferences_store,
                chat_type=chat_type,  # type: ignore[arg-type]
                event=event,
            )

            # Create VanillaContext for runtime
            vanilla_context = VanillaContext(
                chat_context=chat_context,
                chat_id=thread_id,
            )

            # Check if this message will trigger a bot response
            # Only enable Langfuse tracing for messages that trigger responses
            will_trigger = await should_trigger_response(chat_context)
            callbacks = [self.langfuse_handler] if will_trigger else []

            # Set a timeout for the entire graph invocation to prevent blocking
            # the message worker indefinitely
            try:
                await asyncio.wait_for(
                    self.app.ainvoke(
                        {"messages": [HumanMessage(content=event.text)]},
                        config={
                            "callbacks": callbacks,
                            "configurable": {"thread_id": thread_id},
                        },
                        context=vanilla_context,
                    ),
                    timeout=300.0,  # 5 minutes max for entire graph invocation
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Graph invocation timed out after 300s for {chat_type} message "
                    f"in thread {thread_id[:20]}..."
                )
        except Exception as e:
            logger.exception(f"Error processing {chat_type} message: {e}")

    async def _message_worker(self) -> None:
        """Worker that dispatches messages to concurrent processing tasks.

        Messages are processed in parallel - each message spawns a new task
        without blocking the worker, so new messages can be received immediately.
        """
        # Track active processing tasks for cleanup
        active_tasks: set[asyncio.Task] = set()
        max_concurrent_tasks = 50  # Limit concurrent processing to prevent overload

        def _on_task_done(task: asyncio.Task) -> None:
            """Callback to remove completed tasks from tracking set."""
            active_tasks.discard(task)
            self.queue.task_done()
            # Log any exceptions from the task
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.exception(f"Message processing task failed: {exc}")

        while self._running:
            try:
                # Wait for next message
                event, chat_type = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # If too many concurrent tasks, wait for some to complete
                while len(active_tasks) >= max_concurrent_tasks:
                    logger.warning(
                        f"Max concurrent tasks reached ({max_concurrent_tasks}), "
                        f"waiting for tasks to complete..."
                    )
                    # Wait for at least one task to complete
                    done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                    # Tasks are removed by their callbacks

                # Spawn a new task for this message (non-blocking)
                task = asyncio.create_task(
                    self._process_message(event, chat_type),
                    name=f"process_{chat_type}_{time.time():.0f}",
                )
                active_tasks.add(task)
                task.add_done_callback(_on_task_done)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception(f"Worker error: {e}")

        # Cleanup: wait for all active tasks to complete on shutdown
        if active_tasks:
            logger.info(f"Waiting for {len(active_tasks)} active message tasks to complete...")
            await asyncio.gather(*active_tasks, return_exceptions=True)

    def _on_square_message(self, event: SquareMessage) -> None:
        """Handle incoming Square message."""
        self.queue.put_nowait((event, "square"))

    def _on_talk_message(self, event: TalkMessage) -> None:
        """Handle incoming Talk message."""
        self.queue.put_nowait((event, "talk"))

    async def _send_scheduled_message(self, chat_id: str, message: str) -> None:
        """
        Send a scheduled message to a chat.

        Args:
            chat_id: Target chat ID.
            message: Message to send.
        """
        logger.info(f"Sending scheduled message to {chat_id}: {message[:50]}...")

        if not self.client:
            logger.error("Cannot send scheduled message: client not initialized")
            return

        try:
            # Determine chat type based on MID prefix
            # Square Chat MIDs start with 'm' (e.g., m98467015043cea030d6836398056b994)
            # Square MIDs start with 's'
            # Talk MIDs start with 'u' (user), 'r' (room), 'c' (group/chat)
            is_square_chat = chat_id.startswith("m") or chat_id.startswith("s")
            logger.debug(f"Chat ID {chat_id[:8]} is_square_chat={is_square_chat}")

            if is_square_chat:
                logger.debug(f"Sending to Square chat: {chat_id[:8]}")
                await self.client.base.square.send_message(
                    square_chat_mid=chat_id,
                    text=message,
                )
            else:
                logger.debug(f"Sending to Talk chat: {chat_id[:8]}")
                await self.client.base.talk.send_message(
                    to=chat_id,
                    text=message,
                )
            logger.info(f"Successfully sent scheduled message to {chat_id[:8]}")
        except Exception as e:
            logger.error(f"Error sending scheduled message to {chat_id}: {e}", exc_info=True)

    async def serve(self) -> None:
        """Start the bot and listen for messages."""
        # Use async context manager for PostgreSQL checkpointer
        postgres_url = os.environ["POSTGRES_URL"]
        async with AsyncPostgresSaver.from_conn_string(postgres_url) as checkpointer:
            await checkpointer.setup()

            # Get retention days from environment
            retention_days = int(
                os.environ.get("CHECKPOINT_RETENTION_DAYS", CHECKPOINT_RETENTION_DAYS)
            )

            # Run checkpoint cleanup on startup
            try:
                results = await cleanup_old_checkpoints(postgres_url, retention_days)
                if results["threads_cleaned"] > 0:
                    logger.info(
                        f"Cleaned up {results['checkpoints_deleted']} old checkpoints "
                        f"from {results['threads_cleaned']} threads"
                    )
            except Exception as e:
                logger.warning(f"Checkpoint cleanup failed: {e}")

            # Initialize scheduler with PostgreSQL persistence
            self.scheduler = Scheduler(postgres_url=postgres_url)

            # Initialize user preferences store with PostgreSQL persistence
            self.preferences_store = UserPreferencesStore(postgres_url=postgres_url)
            await self.preferences_store.setup()

            await self._init(checkpointer)

            # Schedule daily cleanup task (runs at 3 AM every day)
            async def daily_cleanup() -> None:
                try:
                    results = await cleanup_old_checkpoints(postgres_url, retention_days)
                    if results["threads_cleaned"] > 0:
                        logger.info(
                            f"[Scheduled] Cleaned up {results['checkpoints_deleted']} checkpoints "
                            f"from {results['threads_cleaned']} threads"
                        )
                except Exception as e:
                    logger.warning(f"[Scheduled] Checkpoint cleanup failed: {e}")

            # Schedule daily cleanup at 3 AM using cron expression
            self.scheduler.create_system_task(
                task_id=CLEANUP_TASK_ID,
                callback=daily_cleanup,
                cron_expression="0 3 * * *",  # Every day at 3:00 AM
                max_triggers=-1,  # Unlimited
                description="Daily checkpoint cleanup",
            )

            if not self.client:
                raise RuntimeError("Client not initialized")

            self._running = True

            # Register event handlers
            if self.enable_square:
                self.client.on("square:message", self._on_square_message)
            if self.enable_talk:
                self.client.on("message", self._on_talk_message)

            # Start listening
            self.client.listen(talk=self.enable_talk, square=self.enable_square)

            # Start message worker
            worker_task = asyncio.create_task(self._message_worker())

            # Start scheduler
            await self.scheduler.start()

            enabled_types = []
            if self.enable_square:
                enabled_types.append("Square")
            if self.enable_talk:
                enabled_types.append("Talk")
            logger.info(f"Bot '{self.bot_name}' is now running... ({', '.join(enabled_types)})")
            logger.info("Scheduler is active for timed tasks.")

            try:
                # Keep running
                while self._running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
            finally:
                self._running = False
                await self.scheduler.stop()
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
                if self.client:
                    await self.client.close()
