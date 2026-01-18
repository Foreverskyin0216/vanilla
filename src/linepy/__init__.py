"""
LINEPY - A Python library for creating LINE SelfBot clients.

This is a Python port of the LINEJS TypeScript library.
"""

from .client import (
    BaseClient,
    Chat,
    Client,
    Square,
    SquareChat,
    SquareMessage,
    TalkMessage,
    login_with_password,
    login_with_qr,
    login_with_token,
)
from .server import LineServer, create_app, serve
from .storage import BaseStorage, FileStorage, MemoryStorage

__version__ = "0.1.0"
__all__ = [
    # Client
    "BaseClient",
    "Client",
    "TalkMessage",
    "SquareMessage",
    "Chat",
    "Square",
    "SquareChat",
    # Login
    "login_with_qr",
    "login_with_password",
    "login_with_token",
    # Storage
    "BaseStorage",
    "MemoryStorage",
    "FileStorage",
    # Server
    "LineServer",
    "create_app",
    "serve",
]
