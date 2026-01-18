"""Tests for linepy/obs/obs.py."""

import pytest

from src.linepy.client.base_client import BaseClient
from src.linepy.obs.obs import OBS


@pytest.fixture
def client():
    return BaseClient("DESKTOPWIN")


@pytest.fixture
def obs(client):
    return OBS(client)


class TestOBS:
    """Tests for OBS class."""

    def test_init(self, client):
        obs = OBS(client)
        assert obs.client is client

    def test_obs_host(self):
        assert OBS.OBS_HOST == "obs.line-apps.com"

    def test_type_map_image(self):
        assert OBS.TYPE_MAP["image"] == ("emi", 1)

    def test_type_map_gif(self):
        assert OBS.TYPE_MAP["gif"] == ("emi", 1)

    def test_type_map_video(self):
        assert OBS.TYPE_MAP["video"] == ("emv", 2)

    def test_type_map_audio(self):
        assert OBS.TYPE_MAP["audio"] == ("ema", 3)

    def test_type_map_file(self):
        assert OBS.TYPE_MAP["file"] == ("emf", 14)

    def test_accessible_via_client(self, client):
        obs = client.obs
        assert isinstance(obs, OBS)
        assert obs.client is client


class TestOBSBuildMessageThrift:
    """Tests for _build_message_thrift method."""

    def test_build_message_thrift_with_id(self, obs):
        message = {"id": "msg123"}
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_build_message_thrift_with_from(self, obs):
        message = {"from": "u12345"}
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)

    def test_build_message_thrift_with_to(self, obs):
        message = {"to": "u67890"}
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)

    def test_build_message_thrift_with_content_type_int(self, obs):
        message = {"contentType": 1}
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)

    def test_build_message_thrift_with_content_type_str(self, obs):
        message = {"contentType": "IMAGE"}
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)

    def test_build_message_thrift_full_message(self, obs):
        message = {
            "id": "msg123",
            "from": "u12345",
            "to": "u67890",
            "contentType": 1,
        }
        result = obs._build_message_thrift(message)
        assert isinstance(result, bytes)
        assert len(result) > 0
