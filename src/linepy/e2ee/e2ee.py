"""End-to-end encryption implementation."""

import hashlib
import json
import os
import struct
from base64 import b64decode, b64encode
from typing import TYPE_CHECKING
from urllib.parse import quote

import nacl.public
from Crypto.Cipher import AES
from nacl.bindings import crypto_scalarmult, crypto_scalarmult_base

from src.logging import get_logger

from ..thrift import read_thrift_struct

if TYPE_CHECKING:
    from ..client.base_client import BaseClient

logger = get_logger(__name__)


class E2EE:
    """Handles end-to-end encryption for LINE messages."""

    def __init__(self, client: "BaseClient"):
        self.client = client
        # Track recently registered group keys to avoid re-registration loops
        # Maps chat_mid -> timestamp when last registered
        self._recent_group_key_registrations: dict[str, float] = {}
        # Minimum time between group key registrations (30 seconds)
        self._min_registration_interval = 30.0

    async def get_e2ee_self_key_data(self, mid: str) -> dict:
        """Get E2EE key data for self."""
        try:
            key_data_str = await self.client.storage.get(f"e2eeKeys:{mid}")
            if key_data_str:
                key_data = json.loads(key_data_str)
                if key_data and key_data.get("privKey") and key_data.get("pubKey"):
                    return key_data
        except Exception:
            pass

        keys = await self.client.talk.get_e2ee_public_keys()
        for key in keys:
            key_id = key.get("keyId") or key.get(2)
            if key_id is None:
                continue
            _key_data = await self.get_e2ee_self_key_data_by_key_id(key_id)
            if _key_data:
                await self.save_e2ee_self_key_data(_key_data)
                return _key_data

        from ..client.exceptions import InternalError

        raise InternalError("NoE2EEKey", "E2EE Key has not been saved")

    async def get_e2ee_self_key_data_by_key_id(self, key_id: int | str) -> dict | None:
        """Get E2EE key data by key ID."""
        try:
            data = await self.client.storage.get(f"e2eeKeys:{key_id}")
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None

    async def save_e2ee_self_key_data_by_key_id(self, key_id: int | str, value: dict) -> None:
        """Save E2EE key data by key ID."""
        await self.client.storage.set(f"e2eeKeys:{key_id}", json.dumps(value))

    async def save_e2ee_self_key_data(self, value: dict) -> None:
        """Save E2EE key data for self."""
        if self.client.profile:
            await self.client.storage.set(f"e2eeKeys:{self.client.profile.mid}", json.dumps(value))

    async def verify_and_sync_e2ee_key(self) -> bool:
        """Verify that the local E2EE key matches the server and sync if needed.

        This method:
        1. Gets the bot's current E2EE public key from the server
        2. Compares it with the local private/public key pair
        3. If they don't match, generates a new key pair and registers it

        Returns:
            True if the key was synced/registered, False if already in sync.
        """
        if not self.client.profile:
            await logger.awarning("[E2EE] Cannot verify key - profile not available")
            return False

        # Get server's public keys for this account
        server_keys = await self.client.talk.get_e2ee_public_keys()
        if not server_keys:
            await logger.adebug("[E2EE] No E2EE keys registered on server, will generate new key")
            return await self._generate_and_register_e2ee_key()

        # Get the most recent key from the server
        # Keys are returned with fields: 1=version, 2=keyId, 4=keyData, 5=createdTime
        server_key = server_keys[0] if server_keys else None
        if not server_key:
            await logger.adebug("[E2EE] No E2EE key found on server, will generate new key")
            return await self._generate_and_register_e2ee_key()

        server_key_id = server_key.get(2) or server_key.get("keyId")
        server_pub_key_data = server_key.get(4) or server_key.get("keyData", b"")
        if isinstance(server_pub_key_data, str):
            server_pub_key_data = server_pub_key_data.encode("utf-8")

        # Check if we have the corresponding local key
        local_key_data = await self.get_e2ee_self_key_data_by_key_id(server_key_id)
        if not local_key_data:
            await logger.awarning(
                f"[E2EE] No local key found for server key_id={server_key_id}. "
                "This account may have been logged in on another device. "
                "Generating new key..."
            )
            return await self._generate_and_register_e2ee_key()

        # Verify the local key pair matches the server's public key
        local_priv_key = b64decode(local_key_data.get("privKey", ""))
        local_pub_key = b64decode(local_key_data.get("pubKey", ""))

        # Derive public key from private key to verify
        derived_pub_key = crypto_scalarmult_base(local_priv_key)

        if derived_pub_key != local_pub_key:
            await logger.aerror(
                "[E2EE] Local key pair is corrupted - derived pubkey doesn't match stored pubkey"
            )
            return await self._generate_and_register_e2ee_key()

        if derived_pub_key != server_pub_key_data:
            await logger.awarning(
                "[E2EE] Local public key doesn't match server, registering local key"
            )
            # Register our local key to the server
            return await self._register_local_e2ee_key(local_key_data)

        await logger.adebug(f"[E2EE] Key verification successful - key_id={server_key_id}")
        return False

    async def _generate_and_register_e2ee_key(self) -> bool:
        """Generate a new E2EE key pair and register it with the server.

        Returns:
            True if successful.
        """
        import time

        # Generate new curve25519 key pair
        private_key = nacl.public.PrivateKey.generate()
        priv_key_bytes = bytes(private_key)
        pub_key_bytes = bytes(private_key.public_key)

        # Use next key ID (reqSeq can be reused from client)
        req_seq = await self.client.get_reqseq()
        key_id = req_seq  # Use reqSeq as key ID
        version = 1
        created_time = int(time.time() * 1000)

        await logger.adebug(f"[E2EE] Registering new E2EE key with key_id={key_id}")

        try:
            result = await self.client.talk.register_e2ee_public_key(
                req_seq=req_seq,
                version=version,
                key_id=key_id,
                key_data=pub_key_bytes,
                created_time=created_time,
            )

            # Extract the registered key ID from the response
            registered_key_id = result.get(2) or result.get("keyId") or key_id

            # Save the key pair locally
            key_data = {
                "keyId": registered_key_id,
                "privKey": b64encode(priv_key_bytes).decode(),
                "pubKey": b64encode(pub_key_bytes).decode(),
                "e2eeVersion": "1",
            }
            await self.save_e2ee_self_key_data_by_key_id(registered_key_id, key_data)
            await self.save_e2ee_self_key_data(key_data)

            await logger.ainfo(f"[E2EE] Registered new E2EE key_id={registered_key_id}")
            return True
        except Exception as e:
            await logger.aerror(f"[E2EE] Failed to register E2EE key: {e}")
            return False

    async def _register_local_e2ee_key(self, local_key_data: dict) -> bool:
        """Register the existing local E2EE key with the server.

        Args:
            local_key_data: The local key data to register.

        Returns:
            True if successful.
        """
        import time

        pub_key_bytes = b64decode(local_key_data.get("pubKey", ""))
        key_id = int(local_key_data.get("keyId", 0))
        version = 1
        created_time = int(time.time() * 1000)

        req_seq = await self.client.get_reqseq()

        await logger.adebug(f"[E2EE] Registering local E2EE key with key_id={key_id}")

        try:
            result = await self.client.talk.register_e2ee_public_key(
                req_seq=req_seq,
                version=version,
                key_id=key_id,
                key_data=pub_key_bytes,
                created_time=created_time,
            )

            registered_key_id = result.get(2) or result.get("keyId") or key_id
            await logger.ainfo(f"[E2EE] Registered local E2EE key_id={registered_key_id}")

            # Update local storage if key_id changed
            if registered_key_id != key_id:
                local_key_data["keyId"] = registered_key_id
                await self.save_e2ee_self_key_data_by_key_id(registered_key_id, local_key_data)
                await self.save_e2ee_self_key_data(local_key_data)

            return True
        except Exception as e:
            await logger.aerror(f"[E2EE] Failed to register local E2EE key: {e}")
            return False

    async def get_e2ee_local_public_key(
        self,
        mid: str,
        key_id: int | None = None,
        skip_cache: bool = False,
    ) -> bytes | dict:
        """Get E2EE public key for a user or group.

        E2EENegotiationResult struct:
            1: set<i32> allowedTypes
            2: E2EEPublicKey publicKey
            3: i32 specVersion

        E2EEPublicKey (Pb1_C13097n4) struct:
            1: i32 version
            2: i32 keyId
            4: binary keyData
            5: i64 createdTime
        """
        # E2EENegotiationResult field IDs
        FIELD_PUBLIC_KEY = 2
        FIELD_SPEC_VERSION = 3

        # E2EEPublicKey field IDs
        PK_FIELD_KEY_ID = 2
        PK_FIELD_KEY_DATA = 4

        to_type = self.client.get_to_type(mid)

        if to_type == 0:  # User
            key = None
            if key_id is not None and not skip_cache:
                key = await self.client.storage.get(f"e2eePublicKeys:{key_id}")
            elif skip_cache and key_id is not None:
                # Clear the potentially corrupted cache
                await self.client.storage.delete(f"e2eePublicKeys:{key_id}")

            if not key:
                # Following linejs behavior: use negotiateE2EEPublicKey and verify key_id matches
                # If key_id doesn't match, throw an error (don't use wrong key)
                receiver_key_data = await self.client.talk.negotiate_e2ee_public_key(mid)
                # Use numeric field IDs (thrift returns raw field IDs)
                spec_version = receiver_key_data.get(FIELD_SPEC_VERSION)
                if spec_version is None or spec_version == -1:
                    from ..client.exceptions import InternalError

                    raise InternalError("Not support E2EE", mid)

                public_key = receiver_key_data.get(FIELD_PUBLIC_KEY, {})
                receiver_key_id = public_key.get(PK_FIELD_KEY_ID)
                key_data_raw = public_key.get(PK_FIELD_KEY_DATA, b"")

                # If a specific key_id was requested, verify it matches (following linejs behavior)
                if key_id is not None and receiver_key_id != key_id:
                    from ..client.exceptions import InternalError

                    raise InternalError(
                        "E2EE_KEY_NOT_FOUND",
                        f"E2EE key_id {key_id} not found for {mid}, current key_id is {receiver_key_id}. "
                        f"The sender's key may have been rotated and the old key is no longer available.",
                    )

                # keyData is raw binary from the server, but thrift reader might decode
                # it as UTF-8 string if it happens to be valid UTF-8.
                # We always convert to bytes first, then base64 encode for storage.
                if isinstance(key_data_raw, str):
                    # Convert back to bytes using UTF-8 (safe because is_binary check
                    # ensures round-trip compatibility)
                    key_data_bytes = key_data_raw.encode("utf-8")
                else:
                    key_data_bytes = key_data_raw
                key = b64encode(key_data_bytes).decode()

                # Cache the key with the returned key ID
                if receiver_key_id is not None:
                    await self.client.storage.set(f"e2eePublicKeys:{receiver_key_id}", key)

            return b64decode(key)
        else:
            # Group key
            key = await self.client.storage.get(f"e2eeGroupKeys:{mid}")
            if key_id and key:
                key_data = json.loads(key)
                if key_id != key_data.get("keyId"):
                    key = None
                else:
                    return key_data

            if not key:
                e2ee_group_shared_key = None

                # If a specific key_id is requested, try to get that specific key first
                if key_id:
                    try:
                        e2ee_group_shared_key = await self.client.talk.get_e2ee_group_shared_key(
                            key_version=2,
                            chat_mid=mid,
                            group_key_id=key_id,
                        )
                    except Exception as e:
                        await logger.adebug(
                            f"[E2EE] Failed to get group key {key_id}: {e}, falling back"
                        )
                        e2ee_group_shared_key = None

                # Fall back to getting the last key
                if e2ee_group_shared_key is None:
                    try:
                        e2ee_group_shared_key = (
                            await self.client.talk.get_last_e2ee_group_shared_key(
                                key_version=2,
                                chat_mid=mid,
                            )
                        )
                    except Exception as e:
                        from ..client.exceptions import LineError

                        # Check if this is NOT_FOUND error - register new key
                        should_register = False
                        if isinstance(e, LineError):
                            error_code = e.data.get(1) or e.data.get("code")
                            if error_code == 5:  # NOT_FOUND
                                should_register = True

                        # Also check error message as fallback
                        if not should_register:
                            error_str = str(e).lower()
                            should_register = "not_found" in error_str or "not found" in error_str

                        if should_register:
                            await logger.adebug(
                                f"[E2EE] Group key not found for {mid[:20]}..., registering"
                            )
                            return await self.try_register_e2ee_group_key(mid)
                        else:
                            await logger.aerror(f"[E2EE] Failed to get group shared key: {e}")
                            raise

                # Pb1_U3 struct fields:
                # 1: keyVersion, 2: groupKeyId, 3: creator, 4: creatorKeyId
                # 5: receiver, 6: receiverKeyId, 7: encryptedSharedKey
                group_key_id = e2ee_group_shared_key.get(2) or e2ee_group_shared_key.get(
                    "groupKeyId"
                )
                creator = e2ee_group_shared_key.get(3) or e2ee_group_shared_key.get("creator")
                creator_key_id = e2ee_group_shared_key.get(4) or e2ee_group_shared_key.get(
                    "creatorKeyId"
                )
                # receiver = e2ee_group_shared_key.get(5) (unused)
                receiver_key_id = e2ee_group_shared_key.get(6) or e2ee_group_shared_key.get(
                    "receiverKeyId"
                )
                encrypted_shared_key = e2ee_group_shared_key.get(7) or e2ee_group_shared_key.get(
                    "encryptedSharedKey"
                )

                # Ensure encrypted_shared_key is bytes
                if isinstance(encrypted_shared_key, str):
                    encrypted_shared_key = encrypted_shared_key.encode("utf-8")

                if receiver_key_id is None or creator is None or encrypted_shared_key is None:
                    from ..client.exceptions import InternalError

                    raise InternalError("E2EE_ERROR", "Missing group shared key data")

                self_key_data = await self.get_e2ee_self_key_data_by_key_id(receiver_key_id)
                if self_key_data is None:
                    # The group key was encrypted for a key ID we no longer have
                    await logger.adebug(
                        f"[E2EE] Self key not found for key_id={receiver_key_id}, registering"
                    )
                    return await self.try_register_e2ee_group_key(mid)
                self_key = b64decode(self_key_data["privKey"])

                # Try to get creator's public key and decrypt the group shared key
                # First try with cache, then retry with fresh key if decryption fails
                for attempt, skip_cache in enumerate([False, True]):
                    try:
                        try:
                            creator_key_data = await self.get_e2ee_local_public_key(
                                creator, creator_key_id, skip_cache=skip_cache
                            )
                        except Exception as key_error:
                            await logger.awarning(
                                f"[E2EE] Failed to get creator's key: {key_error}"
                            )
                            raise

                        if not isinstance(creator_key_data, bytes):
                            creator_key_data = b64decode(creator_key_data.get("pubKey", ""))

                        aes_key = self.generate_shared_secret(self_key, creator_key_data)
                        aes_key_hash = self.get_sha256_sum(aes_key, b"Key")
                        aes_iv = self.xor(self.get_sha256_sum(aes_key, b"IV"))

                        cipher = AES.new(aes_key_hash, AES.MODE_CBC, aes_iv)
                        decrypted_raw = cipher.decrypt(encrypted_shared_key)

                        # Try to unpad - if it fails, the data is garbage
                        decrypted = self._unpad(decrypted_raw)

                        # Verify the decryption was successful by checking padding
                        if len(decrypted) == len(decrypted_raw):
                            last_byte = decrypted_raw[-1]
                            raise ValueError(f"Invalid padding: last_byte={last_byte}")

                        # Handle edge case: force unpad if still 48 bytes
                        if len(decrypted) == 48:
                            last_16 = decrypted[-16:]
                            if len(set(last_16)) == 1 and last_16[0] <= 16:
                                decrypted = decrypted[: -last_16[0]]

                        data = {
                            "privKey": b64encode(decrypted).decode(),
                            "keyId": group_key_id,
                        }
                        await self.client.storage.set(f"e2eeGroupKeys:{mid}", json.dumps(data))
                        return data
                    except Exception as decrypt_error:
                        if attempt == 0:
                            await logger.adebug(f"[E2EE] Decrypt failed, retrying: {decrypt_error}")
                            continue
                        else:
                            await logger.adebug(
                                f"[E2EE] Decrypt failed after retry: {decrypt_error}"
                            )
                            break

                # Both attempts failed, register new group key
                return await self.try_register_e2ee_group_key(mid)

            return json.loads(key)

    def generate_shared_secret(self, private_key: bytes, public_key: bytes) -> bytes:
        """Generate shared secret using curve25519."""
        return crypto_scalarmult(private_key, public_key)

    def xor(self, buf: bytes) -> bytes:
        """XOR first half with second half of buffer."""
        buf_length = len(buf) // 2
        result = bytearray(buf_length)
        for i in range(buf_length):
            result[i] = buf[i] ^ buf[buf_length + i]
        return bytes(result)

    def get_sha256_sum(self, *args: bytes | str) -> bytes:
        """Calculate SHA256 hash of concatenated arguments."""
        h = hashlib.sha256()
        for arg in args:
            if isinstance(arg, str):
                arg = arg.encode()
            h.update(arg)
        return h.digest()

    async def try_register_e2ee_group_key(self, chat_mid: str) -> dict:
        """
        Register E2EE group key for a chat.

        This is called when getLastE2EEGroupSharedKey fails with NOT_FOUND,
        indicating no group key exists yet. This function:
        1. Gets all members' public keys
        2. Generates a random shared key
        3. Encrypts it for each member using their public key
        4. Registers the encrypted keys with the server

        Returns:
            The registered group key data from the server.
        """
        # Get all members' E2EE public keys
        e2ee_public_keys = await self.client.talk.get_last_e2ee_public_keys(chat_mid)

        if not e2ee_public_keys:
            from ..client.exceptions import InternalError

            raise InternalError("E2EE_ERROR", "No E2EE public keys found for chat members")

        # Get self key
        if not self.client.profile:
            from ..client.exceptions import InternalError

            raise InternalError("E2EE_ERROR", "Profile not available")

        self_mid = self.client.profile.mid

        # Find self's key ID in the response
        self_key_info = e2ee_public_keys.get(self_mid)
        if not self_key_info:
            from ..client.exceptions import InternalError

            raise InternalError("E2EE_ERROR", f"Self key not found in response for {self_mid}")

        # Get key ID - try numeric field first, then string key
        self_key_id = self_key_info.get(2) or self_key_info.get("keyId")

        self_key_data = await self.get_e2ee_self_key_data_by_key_id(self_key_id)
        if not self_key_data:
            from ..client.exceptions import InternalError

            raise InternalError(
                "NoE2EEKey",
                "E2EE Key has not been saved, try register or use E2EE Login",
            )

        self_key = b64decode(self_key_data["privKey"])

        # Generate a random 32-byte private key for the group
        private_key = os.urandom(32)

        # Prepare lists for the API call
        members: list[str] = []
        key_ids: list[int] = []
        encrypted_shared_keys: list[bytes] = []

        # Detect the key version from members' keys
        # E2EEPublicKey struct: 1=version, 2=keyId, 4=keyData
        # Use the minimum version found among all members to ensure compatibility
        detected_key_version = 2  # Default to version 2
        for key_info in e2ee_public_keys.values():
            member_key_version = key_info.get(1) or key_info.get("version")
            if member_key_version is not None and member_key_version < detected_key_version:
                detected_key_version = member_key_version

        await logger.adebug(f"[E2EE] Using key_version={detected_key_version} for group key")

        for mid, key_info in e2ee_public_keys.items():
            # Get keyId and keyData - try numeric fields first
            key_id = key_info.get(2) or key_info.get("keyId")
            key_data = key_info.get(4) or key_info.get("keyData")

            if key_id is None or key_data is None:
                continue

            members.append(mid)
            key_ids.append(key_id)

            # key_data is raw binary from the server, but thrift reader might decode
            # it as UTF-8 string if it happens to be valid UTF-8.
            if isinstance(key_data, str):
                key_data = key_data.encode("utf-8")

            # Generate shared secret with each member's public key
            aes_key = self.generate_shared_secret(self_key, key_data)
            aes_key_hash = self.get_sha256_sum(aes_key, b"Key")
            aes_iv = self.xor(self.get_sha256_sum(aes_key, b"IV"))

            # Encrypt the shared private key for this member
            cipher = AES.new(aes_key_hash, AES.MODE_CBC, aes_iv)
            # Pad the private key to AES block size
            padded_key = self._pad(private_key)
            encrypted_shared_key = cipher.encrypt(padded_key)
            encrypted_shared_keys.append(encrypted_shared_key)

        # Register the group key using the detected key version
        result = await self.client.talk.register_e2ee_group_key(
            key_version=detected_key_version,
            chat_mid=chat_mid,
            members=members,
            key_ids=key_ids,
            encrypted_shared_keys=encrypted_shared_keys,
        )

        # Extract the group key ID from the result
        # The response contains field 2 = groupKeyId
        group_key_id = result.get(2) or result.get("groupKeyId")
        if group_key_id is None:
            # If not in response, we need to fetch it
            # This shouldn't happen normally but handle it gracefully
            await logger.awarning(
                "[E2EE] registerE2EEGroupKey response missing groupKeyId, "
                "will fetch from server on next use"
            )
            group_key_id = 0

        # Save the generated private key to storage
        data = {
            "privKey": b64encode(private_key).decode(),
            "keyId": group_key_id,
        }
        await self.client.storage.set(f"e2eeGroupKeys:{chat_mid}", json.dumps(data))
        await logger.ainfo(f"[E2EE] Registered new group key, keyId={group_key_id}")

        return data

    def encrypt_aes_ecb(self, aes_key: bytes, plain_data: bytes) -> bytes:
        """Encrypt data with AES-256-ECB."""
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.encrypt(plain_data)

    def decrypt_aes_ecb(self, aes_key: bytes, cipher_data: bytes) -> bytes:
        """Decrypt data with AES-256-ECB."""
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.decrypt(cipher_data)

    async def decode_e2ee_key_v1(
        self,
        data: dict,
        secret: bytes,
    ) -> dict | None:
        """Decode E2EE key from login response."""
        if data.get("encryptedKeyChain"):
            encrypted_key_chain = b64decode(data["encryptedKeyChain"])
            key_id = data.get("keyId")
            public_key = b64decode(data["publicKey"])
            e2ee_version = data.get("e2eeVersion")

            priv_key, pub_key = self.decrypt_key_chain(
                public_key,
                secret,
                encrypted_key_chain,
            )

            result = {
                "keyId": key_id,
                "privKey": b64encode(priv_key).decode(),
                "pubKey": b64encode(pub_key).decode(),
                "e2eeVersion": e2ee_version,
            }

            await self.client.storage.set(f"e2eeKeys:{key_id}", json.dumps(result))

            return result
        return None

    def decrypt_key_chain(
        self,
        public_key: bytes,
        private_key: bytes,
        encrypted_key_chain: bytes,
    ) -> tuple[bytes, bytes]:
        """Decrypt key chain from E2EE login."""
        shared_secret = self.generate_shared_secret(private_key, public_key)
        aes_key = self.get_sha256_sum(shared_secret, b"Key")
        aes_iv = self.xor(self.get_sha256_sum(shared_secret, b"IV"))

        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        keychain_data = cipher.decrypt(encrypted_key_chain)

        # Parse thrift struct
        parsed = read_thrift_struct(keychain_data, 4)
        key_data = parsed.get(1, {})
        if isinstance(key_data, list):
            key_data = key_data[0] if key_data else {}

        public_key_bytes = key_data.get(4, b"")
        private_key_bytes = key_data.get(5, b"")

        return private_key_bytes, public_key_bytes

    def encrypt_device_secret(
        self,
        public_key: bytes,
        private_key: bytes,
        encrypted_key_chain: bytes,
    ) -> bytes:
        """Encrypt device secret for E2EE login confirmation."""
        shared_secret = self.generate_shared_secret(private_key, public_key)
        aes_key = self.get_sha256_sum(shared_secret, b"Key")
        xored = self.xor(self.get_sha256_sum(encrypted_key_chain))

        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.encrypt(xored)

    def generate_aad(
        self,
        to: str,
        from_: str,
        sender_key_id: int,
        receiver_key_id: int,
        spec_version: int = 2,
        content_type: int = 0,
    ) -> bytes:
        """Generate additional authenticated data for E2EE."""
        aad = to.encode()
        aad += from_.encode()
        aad += struct.pack(">I", sender_key_id)
        aad += struct.pack(">I", receiver_key_id)
        aad += struct.pack(">I", spec_version)
        aad += struct.pack(">I", content_type)
        return aad

    async def encrypt_e2ee_message(
        self,
        to: str,
        data: str | dict,
        content_type: int = 0,
        spec_version: int = 2,
    ) -> list[bytes]:
        """Encrypt a message with E2EE.

        E2EENegotiationResult struct:
            1: set<i32> allowedTypes
            2: E2EEPublicKey publicKey
            3: i32 specVersion

        E2EEPublicKey (Pb1_C13097n4) struct:
            1: i32 version
            2: i32 keyId
            4: binary keyData
            5: i64 createdTime
        """
        # E2EENegotiationResult field IDs
        FIELD_PUBLIC_KEY = 2
        FIELD_SPEC_VERSION = 3

        # E2EEPublicKey field IDs
        PK_FIELD_KEY_ID = 2
        PK_FIELD_KEY_DATA = 4

        if self.client.profile is None:
            from ..client.exceptions import InternalError

            raise InternalError("NOT_LOGGED_IN", "Profile not available")
        from_ = self.client.profile.mid
        self_key_data = await self.get_e2ee_self_key_data(from_)

        # Ensure sender_key_id is an integer (may be str from JSON storage)
        sender_key_id = int(self_key_data["keyId"])
        to_type = self.client.get_to_type(to)

        await logger.adebug(f"[E2EE.encrypt] to_type={to_type}")

        if to_type == 0:  # User
            private_key = b64decode(self_key_data["privKey"])
            receiver_key_data = await self.client.talk.negotiate_e2ee_public_key(to)
            # Use numeric field IDs (thrift returns raw field IDs)
            spec_version = int(receiver_key_data.get(FIELD_SPEC_VERSION, 2))

            if spec_version == -1:
                from ..client.exceptions import InternalError

                raise InternalError("Not support E2EE", to)

            public_key = receiver_key_data.get(FIELD_PUBLIC_KEY, {})
            receiver_key_id = int(public_key.get(PK_FIELD_KEY_ID, 0))
            receiver_key_buffer = public_key.get(PK_FIELD_KEY_DATA, b"")
            # keyData is raw binary from the server, but thrift reader might decode
            # it as UTF-8 string if it happens to be valid UTF-8.
            if isinstance(receiver_key_buffer, str):
                receiver_key_buffer = receiver_key_buffer.encode("utf-8")
            key_data = self.generate_shared_secret(private_key, receiver_key_buffer)
        else:  # Group
            group_key_data = await self.get_e2ee_local_public_key(to)
            if not isinstance(group_key_data, dict):
                from ..client.exceptions import InternalError

                raise InternalError("E2EE_ERROR", "Expected group key dict")
            priv_key = b64decode(group_key_data["privKey"])
            pub_key = b64decode(self_key_data["pubKey"])
            # Ensure receiver_key_id is an integer (may be str from JSON storage)
            receiver_key_id = int(group_key_data["keyId"])
            key_data = self.generate_shared_secret(priv_key, pub_key)

        if isinstance(data, str):
            return self._encrypt_e2ee_text_message(
                sender_key_id, receiver_key_id, key_data, spec_version, data, to, from_
            )
        else:
            return self._encrypt_e2ee_data_message(
                sender_key_id,
                receiver_key_id,
                key_data,
                spec_version,
                data,
                to,
                from_,
                content_type,
            )

    def _encrypt_e2ee_text_message(
        self,
        sender_key_id: int,
        receiver_key_id: int,
        key_data: bytes,
        spec_version: int,
        text: str,
        to: str,
        from_: str,
    ) -> list[bytes]:
        """Encrypt a text message."""
        salt = os.urandom(16)
        gcm_key = self.get_sha256_sum(key_data, salt, b"Key")
        aad = self.generate_aad(to, from_, sender_key_id, receiver_key_id, spec_version, 0)
        nonce = os.urandom(12)
        data = json.dumps({"text": text}).encode()

        cipher = AES.new(gcm_key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        enc_data = ciphertext + tag

        return [
            salt,
            enc_data,
            nonce,
            struct.pack(">I", sender_key_id),
            struct.pack(">I", receiver_key_id),
        ]

    def _encrypt_e2ee_data_message(
        self,
        sender_key_id: int,
        receiver_key_id: int,
        key_data: bytes,
        spec_version: int,
        data: dict,
        to: str,
        from_: str,
        content_type: int,
    ) -> list[bytes]:
        """Encrypt a data message."""
        salt = os.urandom(16)
        gcm_key = self.get_sha256_sum(key_data, salt, b"Key")
        aad = self.generate_aad(
            to, from_, sender_key_id, receiver_key_id, spec_version, content_type
        )
        nonce = os.urandom(12)
        data_bytes = json.dumps(data).encode()

        cipher = AES.new(gcm_key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        ciphertext, tag = cipher.encrypt_and_digest(data_bytes)
        enc_data = ciphertext + tag

        return [
            salt,
            enc_data,
            nonce,
            struct.pack(">I", sender_key_id),
            struct.pack(">I", receiver_key_id),
        ]

    async def decrypt_e2ee_message(self, message: dict) -> dict:
        """Decrypt an E2EE message."""
        # Support both numeric field IDs and string keys
        # Field 15 = contentType, Field 20 = chunks
        content_type = message.get(15) or message.get("contentType")
        chunks = message.get(20) or message.get("chunks", [])

        if not chunks:
            return message

        if content_type in ("NONE", 0, None):
            text, meta = await self._decrypt_e2ee_text_message(message)
            # Update both numeric and string keys for compatibility
            message[10] = text  # Field 10 = text
            message["text"] = text
            existing_meta = message.get(18) or message.get("contentMetadata", {})
            message[18] = {**existing_meta, **meta}
            message["contentMetadata"] = message[18]
        elif content_type in ("LOCATION", 15):
            location = await self._decrypt_e2ee_location_message(message)
            message[11] = location  # Field 11 = location
            message["location"] = location

        return message

    async def _decrypt_e2ee_text_message(
        self,
        message: dict,
    ) -> tuple[str, dict]:
        """Decrypt a text message."""
        if self.client.profile is None:
            from ..client.exceptions import InternalError

            raise InternalError("NOT_LOGGED_IN", "Profile not available")
        my_mid = self.client.profile.mid
        # Support both numeric field IDs and string keys
        # Field 1 = from, Field 2 = to, Field 3 = toType
        from_ = message.get(1) or message.get("from")
        to = message.get(2) or message.get("to")
        is_self = from_ == my_mid
        to_type = message.get(3) or message.get("toType")
        # Field 18 = contentMetadata, Field 15 = contentType, Field 20 = chunks
        metadata = message.get(18) or message.get("contentMetadata", {})
        spec_version = metadata.get("e2eeVersion", "2")
        content_type = message.get(15) or message.get("contentType")
        chunks_raw = message.get(20) or message.get("chunks", [])

        # Convert chunks to bytes if needed
        chunks = []
        for c in chunks_raw:
            if isinstance(c, bytes):
                chunks.append(c)
            else:
                chunks.append(c.encode("utf-8"))

        sender_key_id = self._byte2int(chunks[3])
        receiver_key_id = self._byte2int(chunks[4])

        self_key = await self.get_e2ee_self_key_data(my_mid)
        priv_key = b64decode(self_key["privKey"])

        if to_type in ("USER", 0):
            pub_key_data = await self.get_e2ee_local_public_key(
                to if is_self else from_,
                receiver_key_id if is_self else sender_key_id,
            )
            if isinstance(pub_key_data, bytes):
                pub_key = pub_key_data
            else:
                pub_key = b64decode(pub_key_data.get("pubKey", ""))
        else:
            group_key_data = await self.get_e2ee_local_public_key(to, receiver_key_id)
            if not isinstance(group_key_data, dict):
                from ..client.exceptions import InternalError

                raise InternalError("E2EE_ERROR", "Expected group key dict")
            priv_key = b64decode(group_key_data["privKey"])
            pub_key = b64decode(self_key["pubKey"])
            if from_ != my_mid:
                sender_pub = await self.get_e2ee_local_public_key(from_, sender_key_id)
                if isinstance(sender_pub, bytes):
                    pub_key = sender_pub
                else:
                    pub_key = b64decode(sender_pub.get("pubKey", ""))

        # Try decryption, with retry if cache might be stale
        try:
            decrypted = self._decrypt_e2ee_message_v2(
                to,
                from_,
                chunks,
                priv_key,
                pub_key,
                int(spec_version),
                0 if content_type in ("NONE", 0) else int(content_type) if content_type else 0,
            )
        except ValueError as e:
            # MAC check failed - possibly stale cached key
            if "MAC check failed" in str(e) and from_ != my_mid and to_type not in ("USER", 0):
                await logger.adebug("[E2EE.decrypt] MAC check failed, retrying with fresh key")
                # Clear cache and retry
                sender_pub = await self.get_e2ee_local_public_key(
                    from_, sender_key_id, skip_cache=True
                )
                if isinstance(sender_pub, bytes):
                    pub_key = sender_pub
                else:
                    pub_key = b64decode(sender_pub.get("pubKey", ""))

                try:
                    decrypted = self._decrypt_e2ee_message_v2(
                        to,
                        from_,
                        chunks,
                        priv_key,
                        pub_key,
                        int(spec_version),
                        0
                        if content_type in ("NONE", 0)
                        else int(content_type)
                        if content_type
                        else 0,
                    )
                except ValueError as retry_error:
                    if "MAC check failed" in str(retry_error):
                        # The message cannot be decrypted - register new group key for future
                        import time

                        last_registration = self._recent_group_key_registrations.get(to, 0)
                        now = time.time()
                        if now - last_registration >= self._min_registration_interval:
                            await self.client.storage.delete(f"e2eeGroupKeys:{to}")
                            try:
                                await self.try_register_e2ee_group_key(to)
                                self._recent_group_key_registrations[to] = now
                                await logger.adebug("[E2EE.decrypt] New group key registered")
                            except Exception as reg_error:
                                await logger.adebug(
                                    f"[E2EE.decrypt] Failed to register: {reg_error}"
                                )

                        # Re-raise the original error - this message cannot be decrypted
                        raise retry_error
                    else:
                        raise
            else:
                raise

        text = decrypted.get("text", "")
        meta = {
            k: v if isinstance(v, str) else json.dumps(v)
            for k, v in decrypted.items()
            if k != "text"
        }
        return text, meta

    async def _decrypt_e2ee_location_message(self, message: dict) -> dict | None:
        """Decrypt a location message."""
        if self.client.profile is None:
            from ..client.exceptions import InternalError

            raise InternalError("NOT_LOGGED_IN", "Profile not available")
        my_mid = self.client.profile.mid
        from_ = message["from"]
        to = message["to"]
        to_type = message.get("toType")
        metadata = message.get("contentMetadata", {})
        spec_version = metadata.get("e2eeVersion", "2")
        chunks = message.get("chunks", [])

        chunks = [c if isinstance(c, bytes) else c.encode() for c in chunks]

        sender_key_id = self._byte2int(chunks[3])
        receiver_key_id = self._byte2int(chunks[4])

        self_key = await self.get_e2ee_self_key_data(my_mid)
        priv_key = b64decode(self_key["privKey"])

        if to_type in ("USER", 0):
            pub_key_data = await self.get_e2ee_local_public_key(to, receiver_key_id)
            if isinstance(pub_key_data, bytes):
                pub_key = pub_key_data
            else:
                pub_key = b64decode(pub_key_data.get("pubKey", ""))
        else:
            group_key_data = await self.get_e2ee_local_public_key(to, receiver_key_id)
            if not isinstance(group_key_data, dict):
                from ..client.exceptions import InternalError

                raise InternalError("E2EE_ERROR", "Expected group key dict")
            priv_key = b64decode(group_key_data["privKey"])
            pub_key = b64decode(self_key["pubKey"])
            if from_ != my_mid:
                sender_pub = await self.get_e2ee_local_public_key(from_, sender_key_id)
                if isinstance(sender_pub, bytes):
                    pub_key = sender_pub
                else:
                    pub_key = b64decode(sender_pub.get("pubKey", ""))

        decrypted = self._decrypt_e2ee_message_v2(
            to, from_, chunks, priv_key, pub_key, int(spec_version), 15
        )

        return decrypted.get("location")

    def _decrypt_e2ee_message_v2(
        self,
        to: str,
        from_: str,
        chunks: list[bytes],
        priv_key: bytes,
        pub_key: bytes,
        spec_version: int = 2,
        content_type: int = 0,
    ) -> dict:
        """Decrypt an E2EE message (v2)."""
        salt = chunks[0]
        message = chunks[1]
        ciphertext = message[:-16]
        tag = message[-16:]
        nonce = chunks[2]
        sender_key_id = self._byte2int(chunks[3])
        receiver_key_id = self._byte2int(chunks[4])

        key_data = self.generate_shared_secret(priv_key, pub_key)
        gcm_key = self.get_sha256_sum(key_data, salt, b"Key")
        aad = self.generate_aad(
            to, from_, sender_key_id, receiver_key_id, spec_version, content_type
        )

        cipher = AES.new(gcm_key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)

        return json.loads(decrypted.decode())

    def create_sqr_secret(self, base64_only: bool = False) -> tuple[bytes, str]:
        """Create secret for QR code login."""
        private_key = nacl.public.PrivateKey.generate()
        public_key = private_key.public_key

        if base64_only:
            return bytes(private_key), b64encode(bytes(public_key)).decode()

        secret = quote(b64encode(bytes(public_key)).decode())
        version = 1
        return bytes(private_key), f"?secret={secret}&e2eeVersion={version}"

    def _byte2int(self, data: bytes) -> int:
        """Convert bytes to integer."""
        result = 0
        for b in data:
            result = 256 * result + b
        return result

    def _is_base64(self, data: str) -> bool:
        """Check if string is valid base64."""
        try:
            b64decode(data, validate=True)
            return True
        except Exception:
            return False

    def _unpad(self, data: bytes) -> bytes:
        """Remove PKCS7 padding.

        Returns the unpadded data if padding is valid, otherwise returns the original data.
        PKCS7 padding uses the padding length as the padding byte value (1-16).
        """
        if not data:
            return data
        pad_len = data[-1]
        if pad_len < 1 or pad_len > 16:
            return data
        # Validate that all padding bytes have the same value
        padding = data[-pad_len:]
        if all(b == pad_len for b in padding):
            return data[:-pad_len]
        return data

    def _pad(self, data: bytes, block_size: int = 16) -> bytes:
        """Add PKCS7 padding."""
        pad_len = block_size - (len(data) % block_size)
        return data + bytes([pad_len] * pad_len)
