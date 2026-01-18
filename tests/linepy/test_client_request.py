"""Tests for linepy/client/request.py."""

import pytest

from src.linepy.client.base_client import BaseClient
from src.linepy.client.request import RequestClient


@pytest.fixture
def client():
    return BaseClient("DESKTOPWIN")


@pytest.fixture
def request_client(client):
    return RequestClient(client)


class TestRequestClient:
    """Tests for RequestClient."""

    def test_init(self, client):
        rc = RequestClient(client)
        assert rc.client is client
        assert rc._http_client is None

    def test_endpoint_property(self, request_client, client):
        assert request_client.endpoint == client.endpoint

    def test_system_type_property(self, request_client):
        system_type = request_client.system_type
        assert "DESKTOPWIN" in system_type
        assert "WINDOWS" in system_type

    def test_user_agent_property(self, request_client, client):
        user_agent = request_client.user_agent
        assert user_agent.startswith("Line/")
        assert client.device_details.app_version in user_agent

    def test_get_header_without_auth(self, request_client):
        headers = request_client.get_header()
        assert "x-line-application" in headers
        assert "user-agent" in headers
        assert "x-lal" in headers
        assert "x-lpv" in headers
        assert "accept-encoding" in headers
        assert "x-line-access" not in headers

    def test_get_header_with_auth(self, request_client, client):
        client.auth_token = "test-token-123"
        headers = request_client.get_header()
        assert headers["x-line-access"] == "test-token-123"

    async def test_get_http_client(self, request_client):
        http_client = await request_client.get_http_client()
        assert http_client is not None
        assert not http_client.is_closed

        # Should return same client on second call
        http_client2 = await request_client.get_http_client()
        assert http_client is http_client2

        await request_client.close()

    async def test_close(self, request_client):
        await request_client.get_http_client()
        await request_client.close()
        assert request_client._http_client.is_closed

    async def test_close_without_client(self, request_client):
        # Should not raise
        await request_client.close()


class TestRequestClientExceptionCreation:
    """Tests for exception creation in RequestClient."""

    def test_create_exception_square_path(self, request_client):
        exc = request_client._create_exception("/SQ1", "ERROR", "message", {})
        from src.linepy.client.exceptions import SquareException

        assert isinstance(exc, SquareException)

    def test_create_exception_talk_path(self, request_client):
        exc = request_client._create_exception("/S4", "ERROR", "message", {})
        from src.linepy.client.exceptions import TalkException

        assert isinstance(exc, TalkException)

    def test_create_exception_talk_service_path(self, request_client):
        exc = request_client._create_exception("/TalkService", "ERROR", "message", {})
        from src.linepy.client.exceptions import TalkException

        assert isinstance(exc, TalkException)

    def test_create_exception_other_path(self, request_client):
        exc = request_client._create_exception("/other", "ERROR", "message", {})
        from src.linepy.client.exceptions import InternalError

        assert isinstance(exc, InternalError)
