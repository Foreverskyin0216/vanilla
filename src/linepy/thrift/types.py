"""Thrift type definitions."""

from enum import IntEnum
from typing import Any


class ThriftType(IntEnum):
    """Thrift data types."""

    STOP = 0
    VOID = 1
    BOOL = 2
    BYTE = 3
    I08 = 3
    DOUBLE = 4
    I16 = 6
    I32 = 8
    I64 = 10
    STRING = 11
    UTF7 = 11
    STRUCT = 12
    MAP = 13
    SET = 14
    LIST = 15
    UTF8 = 16
    UTF16 = 17


# Type alias for nested array format used in thrift serialization
# Format: [type, field_id, value]
NestedArray = list[None | tuple[int, int, Any] | list[Any]]


class ParsedThrift:
    """Container for parsed thrift data."""

    def __init__(self, data: dict[int, Any], info: dict[str, Any] | None = None):
        self.data = data
        self._info = info or {}

    def __getitem__(self, key: int) -> Any:
        return self.data.get(key)

    def get(self, key: int, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def method(self) -> str:
        """Get the method name from the message info."""
        return self._info.get("fname", "")

    @property
    def message_type(self) -> int:
        """Get the message type from the message info."""
        return self._info.get("mtype", 0)

    @property
    def sequence_id(self) -> int:
        """Get the sequence ID from the message info."""
        return self._info.get("rseqid", 0)
