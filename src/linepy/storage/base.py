"""Base storage interface."""

from abc import ABC, abstractmethod
from typing import Any

StorageValue = Any


class BaseStorage(ABC):
    """Abstract base class for storage implementations."""

    @abstractmethod
    async def set(self, key: str, value: StorageValue) -> None:
        """
        Set a value for a key.

        Args:
            key: The key to set
            value: The value to store
        """
        pass

    @abstractmethod
    async def get(self, key: str) -> StorageValue | None:
        """
        Get a value by key.

        Args:
            key: The key to retrieve

        Returns:
            The stored value or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Delete a key.

        Args:
            key: The key to delete
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all stored data."""
        pass

    async def migrate(self, storage: "BaseStorage") -> None:  # noqa: B027
        """
        Migrate data from another storage.

        Args:
            storage: The source storage to migrate from
        """
        # Subclasses can override this for optimized migration
