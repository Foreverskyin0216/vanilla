"""Tests for linepy/services modules."""

import pytest

from src.linepy.client.base_client import BaseClient
from src.linepy.client.exceptions import InternalError
from src.linepy.services.auth import AuthService
from src.linepy.services.square import SquareService
from src.linepy.services.talk import TalkService
from src.linepy.storage import MemoryStorage


@pytest.fixture
def client():
    return BaseClient("DESKTOPWIN")


@pytest.fixture
def client_with_storage():
    storage = MemoryStorage()
    return BaseClient("DESKTOPWIN", storage=storage)


class TestTalkService:
    """Tests for TalkService."""

    def test_init(self, client):
        service = TalkService(client)
        assert service.client is client
        assert service.protocol_type == 4
        assert service.request_path == "/S4"

    def test_accessible_via_client(self, client):
        service = client.talk
        assert isinstance(service, TalkService)
        assert service.client is client


class TestSquareService:
    """Tests for SquareService."""

    def test_init(self, client):
        service = SquareService(client)
        assert service.client is client
        assert service.protocol_type == 4
        assert service.request_path == "/SQ1"

    def test_accessible_via_client(self, client):
        service = client.square
        assert isinstance(service, SquareService)
        assert service.client is client


class TestAuthService:
    """Tests for AuthService."""

    def test_init(self, client):
        """Test AuthService initialization."""
        service = AuthService(client)
        assert service.client is client
        assert service.protocol_type == 4
        assert service.request_path == "/AS4"

    def test_accessible_via_client(self, client):
        """Test AuthService is accessible via client.auth."""
        service = client.auth
        assert isinstance(service, AuthService)
        assert service.client is client

    @pytest.mark.asyncio
    async def test_try_refresh_token_no_token(self, client_with_storage):
        """Test try_refresh_token raises error when no refresh token."""
        service = AuthService(client_with_storage)
        with pytest.raises(InternalError) as exc_info:
            await service.try_refresh_token()
        assert "refreshToken not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_has_valid_token_with_auth_token(self, client_with_storage):
        """Test has_valid_token returns True when auth token exists."""
        client_with_storage.auth_token = "test_token"
        service = AuthService(client_with_storage)
        assert await service.has_valid_token() is True

    @pytest.mark.asyncio
    async def test_has_valid_token_with_refresh_token(self, client_with_storage):
        """Test has_valid_token returns True when refresh token exists."""
        await client_with_storage.storage.set("refreshToken", "test_refresh")
        service = AuthService(client_with_storage)
        assert await service.has_valid_token() is True

    @pytest.mark.asyncio
    async def test_has_valid_token_no_tokens(self, client_with_storage):
        """Test has_valid_token returns False when no tokens exist."""
        service = AuthService(client_with_storage)
        assert await service.has_valid_token() is False
