"""FastAPI application for LINE client server."""

import asyncio
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ..client import Client, SquareMessage, TalkMessage


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients."""
        data = json.dumps(message, default=str)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


class LineServer:
    """
    FastAPI server wrapper for LINE client.

    Provides WebSocket events and REST API endpoints.
    """

    def __init__(
        self,
        client: Client,
        listen_talk: bool = True,
        listen_square: bool = True,
    ):
        """
        Initialize the LINE server.

        Args:
            client: LINE client instance
            listen_talk: Listen to Talk events (DM/Group)
            listen_square: Listen to Square events (OpenChat)
        """
        self.client = client
        self.listen_talk = listen_talk
        self.listen_square = listen_square
        self.manager = ConnectionManager()
        self._tasks: list[asyncio.Task] = []
        self._event_handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> "LineServer":
        """
        Register an event handler.

        Args:
            event: Event name
            handler: Handler function

        Returns:
            Self for chaining
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
        return self

    async def _emit(self, event: str, data: Any) -> None:
        """Emit an event to handlers and WebSocket clients."""
        # Call registered handlers
        for handler in self._event_handlers.get(event, []):
            if asyncio.iscoroutinefunction(handler):
                await handler(data)
            else:
                handler(data)

        # Broadcast to WebSocket clients
        await self.manager.broadcast({"event": event, "data": data})

    async def _start_polling(self) -> None:
        """Start event polling tasks."""
        if self.listen_talk:
            self._tasks.append(asyncio.create_task(self._poll_talk()))
        if self.listen_square:
            self._tasks.append(asyncio.create_task(self._poll_square()))

    async def _stop_polling(self) -> None:
        """Stop all polling tasks."""
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def _poll_talk(self) -> None:
        """Poll for Talk events."""
        revision = 0
        global_rev = 0
        individual_rev = 0

        # Thrift field IDs for SyncResponse
        FIELD_OPERATION_RESPONSE = 1
        FIELD_FULL_SYNC_RESPONSE = 2

        # Thrift field IDs for OperationResponse
        OP_RESPONSE_FIELD_OPERATIONS = 1

        # Thrift field IDs for FullSyncResponse
        FULL_SYNC_FIELD_NEXT_REVISION = 2

        # Thrift field IDs for Operation
        OP_FIELD_REVISION = 1
        OP_FIELD_TYPE = 3
        OP_FIELD_MESSAGE = 20

        # OpType enum values
        SEND_MESSAGE = 25
        RECEIVE_MESSAGE = 26

        while self.client.base.auth_token:
            try:
                result = await self.client.base.talk.sync(
                    limit=100,
                    revision=revision,
                    global_rev=global_rev,
                    individual_rev=individual_rev,
                )

                # Check for full sync response (field 2)
                full_sync = result.get(FIELD_FULL_SYNC_RESPONSE, {})
                if full_sync:
                    next_rev = full_sync.get(FULL_SYNC_FIELD_NEXT_REVISION)
                    if next_rev:
                        revision = next_rev

                # Get operation response (field 1)
                op_response = result.get(FIELD_OPERATION_RESPONSE, {})

                # Process operations (field 1 of OperationResponse)
                for op in op_response.get(OP_RESPONSE_FIELD_OPERATIONS, []):
                    await self._emit("talk:event", op)

                    # Update revision from operation (field 1)
                    op_revision = op.get(OP_FIELD_REVISION)
                    if op_revision and op_revision > revision:
                        revision = op_revision

                    # Get operation type (field 3) - enum value (int)
                    op_type = op.get(OP_FIELD_TYPE)
                    if op_type in (SEND_MESSAGE, RECEIVE_MESSAGE):
                        # Get message (field 20)
                        message = op.get(OP_FIELD_MESSAGE, {})
                        chunks = message.get(21)  # chunks field
                        if chunks:
                            message = await self.client.base.e2ee.decrypt_e2ee_message(message)
                        msg = TalkMessage(message, self.client)
                        await self._emit("talk:message", self._serialize_message(msg))

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._emit("error", {"type": "talk", "error": str(e)})
                await asyncio.sleep(1)

    async def _poll_square(self) -> None:
        """Poll for Square events."""
        sync_token: str | None = None
        subscription_id: int | None = None

        # Thrift field IDs for FetchMyEventsResponse
        FIELD_SUBSCRIPTION = 1
        FIELD_EVENTS = 2
        FIELD_SYNC_TOKEN = 3

        # Thrift field IDs for SquareEvent
        EVENT_FIELD_TYPE = 3
        EVENT_FIELD_PAYLOAD = 4

        # SquareEventType enum value
        NOTIFICATION_MESSAGE = 29

        # Thrift field ID for SquareEventPayload.notificationMessage
        PAYLOAD_NOTIFICATION_MESSAGE = 30

        # Thrift field ID for SquareEventNotificationMessage.squareMessage
        NOTIFICATION_FIELD_SQUARE_MESSAGE = 2

        while self.client.base.auth_token:
            try:
                result = await self.client.base.square.fetch_my_events(
                    sync_token=sync_token,
                    subscription_id=subscription_id,
                )

                # Extract syncToken (field 3)
                sync_token = result.get(FIELD_SYNC_TOKEN)

                # Extract subscription.subscriptionId (field 1)
                subscription = result.get(FIELD_SUBSCRIPTION, {})
                if isinstance(subscription, dict):
                    subscription_id = subscription.get(1)

                # Process events (field 2)
                for event in result.get(FIELD_EVENTS, []):
                    await self._emit("square:event", event)

                    # Get event type (field 3) - enum value (int)
                    event_type = event.get(EVENT_FIELD_TYPE)
                    # Get payload (field 4)
                    payload = event.get(EVENT_FIELD_PAYLOAD, {})

                    if event_type == NOTIFICATION_MESSAGE:
                        # Get notificationMessage (field 30)
                        notification_msg = payload.get(PAYLOAD_NOTIFICATION_MESSAGE, {})
                        # Get squareMessage (field 2)
                        sq_msg = notification_msg.get(NOTIFICATION_FIELD_SQUARE_MESSAGE)
                        if sq_msg:
                            msg = SquareMessage(sq_msg, self.client)
                            await self._emit("square:message", self._serialize_square_message(msg))

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._emit("error", {"type": "square", "error": str(e)})
                await asyncio.sleep(1)

    def _serialize_message(self, msg: TalkMessage) -> dict:
        """Serialize a TalkMessage for JSON."""
        return {
            "id": msg.id,
            "text": msg.text,
            "from_mid": msg.from_mid,
            "to_mid": msg.to_mid,
            "content_type": msg.content_type,
            "content_metadata": msg.content_metadata,
            "is_my_message": msg.is_my_message,
            "raw": msg.raw,
        }

    def _serialize_square_message(self, msg: SquareMessage) -> dict:
        """Serialize a SquareMessage for JSON."""
        return {
            "id": msg.id,
            "text": msg.text,
            "from_mid": msg.from_mid,
            "square_chat_mid": msg.square_chat_mid,
            "content_type": msg.content_type,
            "content_metadata": msg.content_metadata,
            "raw": msg.raw,
        }

    def create_app(self) -> FastAPI:
        """
        Create the FastAPI application.

        Returns:
            FastAPI application instance
        """

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self._start_polling()
            yield
            await self._stop_polling()
            await self.client.close()

        app = FastAPI(
            title="LINEPY Server",
            description="LINE client server with WebSocket events",
            version="0.1.0",
            lifespan=lifespan,
        )

        @app.get("/")
        async def root():
            """Health check endpoint."""
            return {"status": "ok", "version": "0.1.0"}

        @app.get("/profile")
        async def get_profile():
            """Get current user profile."""
            profile = self.client.profile
            if profile:
                return {
                    "mid": profile.mid,
                    "display_name": profile.display_name,
                    "picture_status": profile.picture_status,
                    "status_message": profile.status_message,
                }
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        @app.get("/contacts/{mid}")
        async def get_contact(mid: str):
            """Get contact information."""
            try:
                contact = await self.client.get_contact(mid)
                return contact
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @app.post("/messages/send")
        async def send_message(
            to: str,
            text: str | None = None,
            content_type: int = 0,
            e2ee: bool = False,
        ):
            """Send a message."""
            try:
                result = await self.client.base.talk.send_message(
                    to=to,
                    text=text,
                    content_type=content_type,
                    e2ee=e2ee,
                )
                return result
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @app.get("/chats")
        async def get_chats():
            """Get all chats."""
            try:
                chats = await self.client.get_all_chats()
                return [{"mid": c.mid, "name": c.name, "type": c.chat_type} for c in chats]
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @app.get("/squares")
        async def get_squares():
            """Get joined Squares."""
            try:
                squares = await self.client.get_joined_squares()
                return [{"mid": s.mid, "name": s.name} for s in squares]
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time events."""
            await self.manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    try:
                        message = json.loads(data)
                        action = message.get("action")

                        if action == "send_message":
                            result = await self.client.base.talk.send_message(
                                to=message.get("to"),
                                text=message.get("text"),
                                content_type=message.get("content_type", 0),
                                e2ee=message.get("e2ee", False),
                            )
                            await websocket.send_text(
                                json.dumps({"action": "message_sent", "data": result}, default=str)
                            )

                        elif action == "ping":
                            await websocket.send_text(json.dumps({"action": "pong"}))

                    except json.JSONDecodeError:
                        await websocket.send_text(json.dumps({"error": "Invalid JSON"}))

            except WebSocketDisconnect:
                self.manager.disconnect(websocket)

        return app

    async def serve(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        **kwargs: Any,
    ) -> None:
        """
        Start the server using uvicorn.

        Args:
            host: Host to bind to
            port: Port to bind to
            **kwargs: Additional uvicorn config options
        """
        import uvicorn

        app = self.create_app()
        config = uvicorn.Config(app, host=host, port=port, **kwargs)
        server = uvicorn.Server(config)
        await server.serve()


async def serve(
    client: Client,
    host: str = "0.0.0.0",
    port: int = 8000,
    listen_talk: bool = True,
    listen_square: bool = True,
    **kwargs: Any,
) -> None:
    """
    Start a LINE client server.

    Args:
        client: LINE client instance
        host: Host to bind to
        port: Port to bind to
        listen_talk: Listen to Talk events
        listen_square: Listen to Square events
        **kwargs: Additional uvicorn config options
    """
    server = LineServer(client, listen_talk, listen_square)
    await server.serve(host, port, **kwargs)


def create_app(
    client: Client,
    listen_talk: bool = True,
    listen_square: bool = True,
) -> FastAPI:
    """
    Create a FastAPI application for the LINE client.

    Args:
        client: LINE client instance
        listen_talk: Listen to Talk events
        listen_square: Listen to Square events

    Returns:
        FastAPI application
    """
    server = LineServer(client, listen_talk, listen_square)
    return server.create_app()
