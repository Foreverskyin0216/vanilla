"""In-memory storage implementation."""

from typing import Any

from .base import BaseStorage, StorageValue


class MemoryStorage(BaseStorage):
    """
    In-memory storage implementation.

    Data is stored in a dictionary and is not persisted.
    """

    def __init__(self, initial_data: dict[str, Any] | None = None):
        """
        Initialize memory storage.

        Args:
            initial_data: Optional initial data dictionary
        """
        self._data: dict[str, StorageValue] = initial_data.copy() if initial_data else {}

    async def set(self, key: str, value: StorageValue) -> None:
        """Set a value for a key."""
        self._data[key] = value

    async def get(self, key: str) -> StorageValue | None:
        """Get a value by key."""
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        self._data.pop(key, None)

    async def clear(self) -> None:
        """Clear all stored data."""
        self._data.clear()

    def get_all(self) -> dict[str, StorageValue]:
        """
        Get all stored data.

        Returns:
            A copy of all stored data
        """
        return self._data.copy()

    async def migrate(self, storage: BaseStorage) -> None:
        """Migrate data from another storage."""
        if isinstance(storage, MemoryStorage):
            self._data.update(storage._data)
