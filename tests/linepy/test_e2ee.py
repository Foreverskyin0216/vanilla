"""Tests for linepy/e2ee/e2ee.py."""

import json
import struct

import pytest

from src.linepy.client.base_client import BaseClient
from src.linepy.e2ee.e2ee import E2EE


@pytest.fixture
def client():
    return BaseClient("DESKTOPWIN")


@pytest.fixture
def e2ee(client):
    return E2EE(client)


class TestE2EEHelpers:
    """Tests for E2EE helper methods."""

    def test_xor(self, e2ee):
        buf = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        result = e2ee.xor(buf)
        # XOR first 4 bytes with last 4 bytes
        expected = bytes([0x01 ^ 0x05, 0x02 ^ 0x06, 0x03 ^ 0x07, 0x04 ^ 0x08])
        assert result == expected

    def test_xor_16_bytes(self, e2ee):
        buf = bytes(range(16))
        result = e2ee.xor(buf)
        assert len(result) == 8
        for i in range(8):
            assert result[i] == i ^ (i + 8)

    def test_get_sha256_sum_bytes(self, e2ee):
        result = e2ee.get_sha256_sum(b"hello")
        assert len(result) == 32
        assert isinstance(result, bytes)

    def test_get_sha256_sum_string(self, e2ee):
        result = e2ee.get_sha256_sum("hello")
        assert len(result) == 32
        assert isinstance(result, bytes)

    def test_get_sha256_sum_multiple_args(self, e2ee):
        result1 = e2ee.get_sha256_sum(b"hello", b"world")
        result2 = e2ee.get_sha256_sum(b"helloworld")
        assert result1 == result2

    def test_get_sha256_sum_mixed_types(self, e2ee):
        result = e2ee.get_sha256_sum(b"hello", "world")
        assert len(result) == 32

    def test_encrypt_decrypt_aes_ecb(self, e2ee):
        key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        plaintext = b"0123456789abcdef"  # 16 bytes (one block)
        ciphertext = e2ee.encrypt_aes_ecb(key, plaintext)
        decrypted = e2ee.decrypt_aes_ecb(key, ciphertext)
        assert decrypted == plaintext

    def test_byte2int(self, e2ee):
        assert e2ee._byte2int(b"\x00") == 0
        assert e2ee._byte2int(b"\x01") == 1
        assert e2ee._byte2int(b"\xff") == 255
        assert e2ee._byte2int(b"\x00\x01") == 1
        assert e2ee._byte2int(b"\x01\x00") == 256
        assert e2ee._byte2int(b"\xff\xff") == 65535

    def test_byte2int_4_bytes(self, e2ee):
        assert e2ee._byte2int(b"\x00\x00\x00\x01") == 1
        assert e2ee._byte2int(b"\x00\x00\x01\x00") == 256
        assert e2ee._byte2int(b"\x7f\xff\xff\xff") == 2147483647

    def test_unpad(self, e2ee):
        # PKCS7 padding with pad_len = 4
        data = b"hello" + bytes([4, 4, 4, 4])
        assert e2ee._unpad(data) == b"hello"  # Removes last 4 bytes

    def test_unpad_empty(self, e2ee):
        assert e2ee._unpad(b"") == b""

    def test_unpad_invalid_pad_len(self, e2ee):
        # pad_len > 16 should not be stripped
        data = b"hello" + bytes([20])
        assert e2ee._unpad(data) == data

    def test_pad(self, e2ee):
        data = b"hello"  # 5 bytes
        padded = e2ee._pad(data)
        # Should pad to 16 bytes (11 bytes of padding)
        assert len(padded) == 16
        assert padded[-1] == 11
        assert padded[-11:] == bytes([11] * 11)

    def test_pad_already_aligned(self, e2ee):
        data = b"0123456789abcdef"  # 16 bytes
        padded = e2ee._pad(data)
        # Should add full block of padding
        assert len(padded) == 32
        assert padded[-1] == 16

    def test_generate_shared_secret(self, e2ee):
        # Using known test keys
        import nacl.public

        priv_key = nacl.public.PrivateKey.generate()
        pub_key = priv_key.public_key

        # Generate shared secret with same private and public key
        shared = e2ee.generate_shared_secret(bytes(priv_key), bytes(pub_key))
        assert len(shared) == 32
        assert isinstance(shared, bytes)

    def test_generate_aad(self, e2ee):
        aad = e2ee.generate_aad(
            to="uabc123",
            from_="udef456",
            sender_key_id=1,
            receiver_key_id=2,
            spec_version=2,
            content_type=0,
        )
        # AAD format: to + from + sender_key_id(4) + receiver_key_id(4) + spec_version(4) + content_type(4)
        assert aad.startswith(b"uabc123")
        assert b"udef456" in aad
        assert struct.pack(">I", 1) in aad
        assert struct.pack(">I", 2) in aad


class TestE2EECreateSqrSecret:
    """Tests for create_sqr_secret method."""

    def test_create_sqr_secret(self, e2ee):
        priv_key, secret = e2ee.create_sqr_secret()
        assert len(priv_key) == 32
        assert "?secret=" in secret
        assert "&e2eeVersion=1" in secret

    def test_create_sqr_secret_base64_only(self, e2ee):
        priv_key, pub_key_b64 = e2ee.create_sqr_secret(base64_only=True)
        assert len(priv_key) == 32
        assert isinstance(pub_key_b64, str)
        # Should be valid base64
        from base64 import b64decode

        decoded = b64decode(pub_key_b64)
        assert len(decoded) == 32


class TestE2EEKeyStorage:
    """Tests for E2EE key storage methods."""

    async def test_save_and_get_e2ee_self_key_data_by_key_id(self, e2ee):
        key_data = {"privKey": "abc123", "pubKey": "def456", "keyId": 1}
        await e2ee.save_e2ee_self_key_data_by_key_id(1, key_data)

        result = await e2ee.get_e2ee_self_key_data_by_key_id(1)
        assert result == key_data

    async def test_get_e2ee_self_key_data_by_key_id_not_found(self, e2ee):
        result = await e2ee.get_e2ee_self_key_data_by_key_id(999)
        assert result is None

    async def test_save_e2ee_self_key_data_with_profile(self, client):
        from src.linepy.client.base_client import Profile

        client.profile = Profile(mid="u12345", display_name="Test")
        e2ee = E2EE(client)

        key_data = {"privKey": "abc", "pubKey": "def", "keyId": 1}
        await e2ee.save_e2ee_self_key_data(key_data)

        stored = await client.storage.get("e2eeKeys:u12345")
        assert stored is not None
        assert json.loads(stored) == key_data

    async def test_save_e2ee_self_key_data_without_profile(self, e2ee):
        key_data = {"privKey": "abc", "pubKey": "def", "keyId": 1}
        # Should not raise, just no-op
        await e2ee.save_e2ee_self_key_data(key_data)
