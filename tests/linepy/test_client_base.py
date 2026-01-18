"""Tests for linepy/client/base_client.py."""

import json

import pytest

from src.linepy.client.base_client import BaseClient, Config, Profile
from src.linepy.storage.memory import MemoryStorage


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        config = Config()
        assert config.timeout == 30_000
        assert config.long_timeout == 180_000

    def test_custom_values(self):
        config = Config(timeout=60_000, long_timeout=300_000)
        assert config.timeout == 60_000
        assert config.long_timeout == 300_000


class TestProfile:
    """Tests for Profile dataclass."""

    def test_required_fields(self):
        profile = Profile(mid="u123", display_name="Test User")
        assert profile.mid == "u123"
        assert profile.display_name == "Test User"

    def test_optional_fields(self):
        profile = Profile(
            mid="u123",
            display_name="Test",
            picture_status="pic123",
            status_message="Hello!",
            raw={"extra": "data"},
        )
        assert profile.picture_status == "pic123"
        assert profile.status_message == "Hello!"
        assert profile.raw == {"extra": "data"}

    def test_default_optional_fields(self):
        profile = Profile(mid="u123", display_name="Test")
        assert profile.picture_status is None
        assert profile.status_message is None
        assert profile.raw == {}


class TestBaseClient:
    """Tests for BaseClient."""

    def test_init_with_valid_device(self):
        client = BaseClient("DESKTOPWIN")
        assert client.device == "DESKTOPWIN"
        assert client.device_details is not None
        assert client.endpoint == "legy.line-apps.com"

    def test_init_with_invalid_device_raises(self):
        with pytest.raises(ValueError, match="Unsupported device"):
            BaseClient("INVALID_DEVICE")

    def test_init_with_custom_version(self):
        client = BaseClient("DESKTOPWIN", version="1.0.0")
        assert client.device_details.app_version == "1.0.0"

    def test_init_with_custom_endpoint(self):
        client = BaseClient("DESKTOPWIN", endpoint="custom.endpoint.com")
        assert client.endpoint == "custom.endpoint.com"

    def test_init_with_custom_storage(self):
        storage = MemoryStorage({"key": "value"})
        client = BaseClient("DESKTOPWIN", storage=storage)
        assert client.storage is storage

    def test_init_default_storage_is_memory(self):
        client = BaseClient("DESKTOPWIN")
        assert isinstance(client.storage, MemoryStorage)

    def test_auth_token_initially_none(self):
        client = BaseClient("DESKTOPWIN")
        assert client.auth_token is None

    def test_profile_initially_none(self):
        client = BaseClient("DESKTOPWIN")
        assert client.profile is None

    def test_system_type_property(self):
        client = BaseClient("DESKTOPWIN")
        system_type = client.system_type
        assert "DESKTOPWIN" in system_type
        assert "WINDOWS" in system_type

    def test_get_to_type_user(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("u12345") == 0

    def test_get_to_type_room(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("r12345") == 1

    def test_get_to_type_chat(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("c12345") == 2

    def test_get_to_type_square(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("s12345") == 3

    def test_get_to_type_bot(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("m12345") == 4

    def test_get_to_type_page(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("p12345") == 5

    def test_get_to_type_voom(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("v12345") == 6

    def test_get_to_type_timeline(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("t12345") == 7

    def test_get_to_type_unknown(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("x12345") is None

    def test_get_to_type_empty_string(self):
        client = BaseClient("DESKTOPWIN")
        assert client.get_to_type("") is None

    async def test_get_reqseq_increments(self):
        client = BaseClient("DESKTOPWIN")
        seq1 = await client.get_reqseq("talk")
        seq2 = await client.get_reqseq("talk")
        seq3 = await client.get_reqseq("talk")
        assert seq1 == 0
        assert seq2 == 1
        assert seq3 == 2

    async def test_get_reqseq_different_services(self):
        client = BaseClient("DESKTOPWIN")
        talk_seq = await client.get_reqseq("talk")
        square_seq = await client.get_reqseq("square")
        assert talk_seq == 0
        assert square_seq == 0

    async def test_get_reqseq_persisted_to_storage(self):
        storage = MemoryStorage()
        client = BaseClient("DESKTOPWIN", storage=storage)
        await client.get_reqseq("talk")
        await client.get_reqseq("talk")

        stored = await storage.get("reqseq")
        parsed = json.loads(stored)
        assert parsed["talk"] == 2

    async def test_get_reqseq_loads_from_storage(self):
        storage = MemoryStorage({"reqseq": json.dumps({"talk": 100})})
        client = BaseClient("DESKTOPWIN", storage=storage)
        seq = await client.get_reqseq("talk")
        assert seq == 100

    def test_log_emits_event(self):
        client = BaseClient("DESKTOPWIN")
        logged = []

        def handler(data):
            logged.append(data)

        client.on("log", handler)
        client.log("info", {"message": "test"})

        assert len(logged) == 1
        assert logged[0]["type"] == "info"
        assert logged[0]["data"]["message"] == "test"

    def test_talk_property_returns_talk_service(self):
        client = BaseClient("DESKTOPWIN")
        talk = client.talk
        assert talk is not None
        # Should be cached
        assert client.talk is talk

    def test_square_property_returns_square_service(self):
        client = BaseClient("DESKTOPWIN")
        square = client.square
        assert square is not None
        # Should be cached
        assert client.square is square

    def test_e2ee_property_returns_e2ee(self):
        client = BaseClient("DESKTOPWIN")
        e2ee = client.e2ee
        assert e2ee is not None
        # Should be cached
        assert client.e2ee is e2ee

    def test_obs_property_returns_obs(self):
        client = BaseClient("DESKTOPWIN")
        obs = client.obs
        assert obs is not None
        # Should be cached
        assert client.obs is obs

    def test_login_process_property_returns_login(self):
        client = BaseClient("DESKTOPWIN")
        login = client.login_process
        assert login is not None
        # Should be cached
        assert client.login_process is login

    async def test_close(self):
        client = BaseClient("DESKTOPWIN")
        # Should not raise
        await client.close()


class TestBaseClientCaseSensitivity:
    """Tests for device case handling."""

    def test_lowercase_device_fails(self):
        # Device lookup is case-insensitive in get_device_details
        client = BaseClient("desktopwin")
        assert client.device == "desktopwin"

    def test_mixed_case_device(self):
        client = BaseClient("DesktopWin")
        assert client.device == "DesktopWin"
