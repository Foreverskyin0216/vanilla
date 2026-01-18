"""Exception classes for LINE client."""

from typing import Any


class LineError(Exception):
    """Base exception for LINE client errors."""

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.data = data or {}

    def __str__(self) -> str:
        if self.data:
            return f"{self.message}: {self.data}"
        return self.message


class InternalError(LineError):
    """Internal error from LINE API."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None):
        super().__init__(message, data)
        self.code = code
        if data:
            self.data["code"] = code
        else:
            self.data = {"code": code}


class TalkException(LineError):
    """Exception from Talk service."""

    pass


class SquareException(LineError):
    """Exception from Square service."""

    pass


class ChannelException(LineError):
    """Exception from Channel service."""

    pass


class AuthException(LineError):
    """Authentication error."""

    pass


class LoginError(LineError):
    """Login error."""

    pass


class TimeoutError(LineError):
    """Request timeout error."""

    pass
