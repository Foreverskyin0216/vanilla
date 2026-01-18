"""Tests for linepy/storage modules."""

import json

import pytest

from src.linepy.storage.base import BaseStorage
from src.linepy.storage.file import BYTES_PREFIX, FileStorage
from src.linepy.storage.memory import MemoryStorage


class TestMemoryStorage:
    """Tests for MemoryStorage."""

    @pytest.fixture
    def storage(self):
        return MemoryStorage()

    async def test_set_and_get(self, storage):
        await storage.set("key1", "value1")
        result = await storage.get("key1")
        assert result == "value1"

    async def test_get_nonexistent_returns_none(self, storage):
        result = await storage.get("nonexistent")
        assert result is None

    async def test_delete_existing_key(self, storage):
        await storage.set("key1", "value1")
        await storage.delete("key1")
        result = await storage.get("key1")
        assert result is None

    async def test_delete_nonexistent_key_no_error(self, storage):
        await storage.delete("nonexistent")

    async def test_clear(self, storage):
        await storage.set("key1", "value1")
        await storage.set("key2", "value2")
        await storage.clear()
        assert await storage.get("key1") is None
        assert await storage.get("key2") is None

    async def test_get_all(self, storage):
        await storage.set("key1", "value1")
        await storage.set("key2", "value2")
        all_data = storage.get_all()
        assert all_data == {"key1": "value1", "key2": "value2"}

    async def test_get_all_returns_copy(self, storage):
        await storage.set("key1", "value1")
        all_data = storage.get_all()
        all_data["key1"] = "modified"
        assert await storage.get("key1") == "value1"

    def test_init_with_initial_data(self):
        initial = {"key1": "value1", "key2": 123}
        storage = MemoryStorage(initial_data=initial)
        assert storage._data == initial

    def test_init_with_initial_data_copies(self):
        initial = {"key1": "value1"}
        storage = MemoryStorage(initial_data=initial)
        initial["key1"] = "modified"
        assert storage._data["key1"] == "value1"

    async def test_migrate_from_memory_storage(self):
        source = MemoryStorage({"key1": "value1", "key2": "value2"})
        target = MemoryStorage()
        await target.migrate(source)
        assert target._data == {"key1": "value1", "key2": "value2"}

    async def test_set_various_types(self, storage):
        await storage.set("str", "hello")
        await storage.set("int", 123)
        await storage.set("float", 3.14)
        await storage.set("list", [1, 2, 3])
        await storage.set("dict", {"a": 1})
        await storage.set("bytes", b"\x00\x01")

        assert await storage.get("str") == "hello"
        assert await storage.get("int") == 123
        assert await storage.get("float") == 3.14
        assert await storage.get("list") == [1, 2, 3]
        assert await storage.get("dict") == {"a": 1}
        assert await storage.get("bytes") == b"\x00\x01"


class TestFileStorage:
    """Tests for FileStorage."""

    @pytest.fixture
    def temp_path(self, tmp_path):
        return tmp_path / "test_storage.json"

    @pytest.fixture
    def storage(self, temp_path):
        return FileStorage(temp_path)

    async def test_set_and_get(self, storage):
        await storage.set("key1", "value1")
        result = await storage.get("key1")
        assert result == "value1"

    async def test_data_persisted_to_file(self, temp_path):
        storage = FileStorage(temp_path)
        await storage.set("key1", "value1")

        # Create new storage instance and verify data persisted
        storage2 = FileStorage(temp_path)
        assert await storage2.get("key1") == "value1"

    async def test_get_nonexistent_returns_none(self, storage):
        result = await storage.get("nonexistent")
        assert result is None

    async def test_delete_existing_key(self, storage):
        await storage.set("key1", "value1")
        await storage.delete("key1")
        result = await storage.get("key1")
        assert result is None

    async def test_delete_nonexistent_key_no_error(self, storage):
        await storage.delete("nonexistent")

    async def test_clear(self, storage):
        await storage.set("key1", "value1")
        await storage.set("key2", "value2")
        await storage.clear()
        assert await storage.get("key1") is None
        assert await storage.get("key2") is None

    async def test_get_all(self, storage):
        await storage.set("key1", "value1")
        await storage.set("key2", "value2")
        all_data = storage.get_all()
        assert all_data == {"key1": "value1", "key2": "value2"}

    async def test_get_all_returns_copy(self, storage):
        await storage.set("key1", "value1")
        all_data = storage.get_all()
        all_data["key1"] = "modified"
        assert await storage.get("key1") == "value1"

    def test_init_with_initial_data(self, tmp_path):
        path = tmp_path / "new_storage.json"
        initial = {"key1": "value1", "key2": 123}
        storage = FileStorage(path, initial_data=initial)
        assert storage._data == initial
        assert path.exists()

    async def test_bytes_encoding(self, temp_path):
        storage = FileStorage(temp_path)
        await storage.set("binary", b"\x00\x01\x02\xff")

        # Verify bytes stored with prefix
        with open(temp_path) as f:
            raw = json.load(f)
        assert raw["binary"].startswith(BYTES_PREFIX)

        # Verify bytes decoded correctly
        storage2 = FileStorage(temp_path)
        assert await storage2.get("binary") == b"\x00\x01\x02\xff"

    async def test_unicode_values(self, storage):
        await storage.set("chinese", "你好世界")
        await storage.set("emoji", "🎉🎊")
        assert await storage.get("chinese") == "你好世界"
        assert await storage.get("emoji") == "🎉🎊"

    def test_load_invalid_json_clears_data(self, temp_path):
        # Write invalid JSON
        with open(temp_path, "w") as f:
            f.write("not valid json")

        storage = FileStorage(temp_path)
        assert storage._data == {}

    def test_load_existing_file(self, temp_path):
        # Create file with data
        with open(temp_path, "w") as f:
            json.dump({"key1": "value1"}, f)

        storage = FileStorage(temp_path)
        assert storage._data == {"key1": "value1"}

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "storage.json"
        FileStorage(path, initial_data={"key": "value"})
        assert path.exists()

    async def test_migrate_from_file_storage(self, tmp_path):
        source_path = tmp_path / "source.json"
        target_path = tmp_path / "target.json"

        source = FileStorage(source_path, {"key1": "value1", "key2": "value2"})
        target = FileStorage(target_path)

        await target.migrate(source)
        assert target._data == {"key1": "value1", "key2": "value2"}

        # Verify persisted
        target2 = FileStorage(target_path)
        assert await target2.get("key1") == "value1"


class TestBaseStorage:
    """Tests for BaseStorage abstract class."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseStorage()

    def test_subclass_must_implement_methods(self):
        class IncompleteStorage(BaseStorage):
            pass

        with pytest.raises(TypeError):
            IncompleteStorage()

    async def test_migrate_default_does_nothing(self):
        storage = MemoryStorage()
        source = MemoryStorage({"key": "value"})

        # Call base migrate (which does nothing)
        await BaseStorage.migrate(storage, source)

        # Data should not be migrated since base implementation is a no-op
        assert storage._data == {}
