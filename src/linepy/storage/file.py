"""File-based storage implementation."""

import json
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any

from .base import BaseStorage, StorageValue

# Prefix to mark bytes values
BYTES_PREFIX = "__bytes__:"


class FileStorage(BaseStorage):
    """
    File-based storage implementation.

    Data is persisted to a JSON file.
    Bytes values are encoded as base64 with a special prefix.
    """

    def __init__(
        self,
        path: str | Path,
        initial_data: dict[str, Any] | None = None,
    ):
        """
        Initialize file storage.

        Args:
            path: Path to the storage file
            initial_data: Optional initial data dictionary
        """
        self._path = Path(path)
        self._data: dict[str, StorageValue] = {}

        # Load existing data if file exists
        if self._path.exists():
            self._load()
        elif initial_data:
            self._data = initial_data.copy()
            self._save()

    def _load(self) -> None:
        """Load data from file."""
        try:
            with open(self._path, encoding="utf-8") as f:
                raw_data = json.load(f)
                # Decode bytes values
                self._data = {}
                for k, v in raw_data.items():
                    if isinstance(v, str) and v.startswith(BYTES_PREFIX):
                        self._data[k] = b64decode(v[len(BYTES_PREFIX) :])
                    else:
                        self._data[k] = v
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def _save(self) -> None:
        """Save data to file."""
        # Ensure directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Encode bytes values as base64
        save_data = {}
        for k, v in self._data.items():
            if isinstance(v, bytes):
                save_data[k] = BYTES_PREFIX + b64encode(v).decode("ascii")
            else:
                save_data[k] = v

        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

    async def set(self, key: str, value: StorageValue) -> None:
        """Set a value for a key."""
        self._data[key] = value
        self._save()

    async def get(self, key: str) -> StorageValue | None:
        """Get a value by key."""
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        if key in self._data:
            del self._data[key]
            self._save()

    async def clear(self) -> None:
        """Clear all stored data."""
        self._data.clear()
        self._save()

    def get_all(self) -> dict[str, StorageValue]:
        """
        Get all stored data.

        Returns:
            A copy of all stored data
        """
        return self._data.copy()

    async def migrate(self, storage: BaseStorage) -> None:
        """Migrate data from another storage."""
        if isinstance(storage, FileStorage):
            self._data.update(storage._data)
            self._save()
