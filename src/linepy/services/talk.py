"""Talk service for personal and group chat."""

from typing import TYPE_CHECKING

from src.logging import get_logger

from ..thrift.types import ThriftType

if TYPE_CHECKING:
    from ..client.base_client import BaseClient

logger = get_logger(__name__)


class TalkService:
    """
    Talk service for personal and group chat operations.

    Handles message sending, chat management, contacts, and more.
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.protocol_type = 4
        self.request_path = "/S4"

    async def sync(
        self,
        limit: int = 100,
        revision: int = 0,
        global_rev: int = 0,
        individual_rev: int = 0,
        timeout: int | None = None,
    ) -> dict:
        """
        Retrieve LINE events from the server.

        Args:
            limit: Maximum number of events to retrieve
            revision: Last known revision number
            global_rev: Last known global revision number
            individual_rev: Last known individual revision number
            timeout: Request timeout in milliseconds

        Returns:
            Event sync result
        """
        # SyncRequest struct:
        # Field 1 = lastRevision (i64)
        # Field 2 = count (i32)
        # Field 3 = lastGlobalRevision (i64)
        # Field 4 = lastIndividualRevision (i64)
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [10, 1, revision],  # lastRevision
                        [8, 2, limit],  # count
                        [10, 3, global_rev],  # lastGlobalRevision
                        [10, 4, individual_rev],  # lastIndividualRevision
                    ],
                ],
            ],
            "sync",
            4,
            True,
            "/SYNC4",
            {},
            timeout or self.client.config.long_timeout,
        )

    async def send_message(
        self,
        to: str,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict[str, str] | None = None,
        related_message_id: str | None = None,
        location: dict | None = None,
        chunks: list[bytes] | list[str] | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Send a message to a recipient.

        Args:
            to: Recipient's MID
            text: Message text
            content_type: Type of content (0=NONE, 1=IMAGE, etc.)
            content_metadata: Additional metadata
            related_message_id: ID of message to reply to
            location: Location data
            chunks: Encrypted message chunks (for E2EE)
            e2ee: Whether to use E2EE encryption

        Returns:
            Sent message object
        """
        content_metadata = content_metadata or {}
        logger.debug(f"send_message called with e2ee={e2ee} to={to}")

        # Handle E2EE encryption if requested
        if e2ee and not chunks and (text or location):
            logger.debug(f"E2EE encryption requested for to={to}")
            e2ee_data = text if text else location if location else ""
            try:
                chunks = await self.client.e2ee.encrypt_e2ee_message(
                    to,
                    e2ee_data,
                    content_type,
                )
                logger.debug(f"E2EE encryption successful, chunks={len(chunks)}")
            except Exception as e:
                logger.error(f"E2EE encryption failed: {e}")
                raise
            content_metadata.update(
                {
                    "e2eeVersion": "2",
                    "contentType": str(content_type),
                    "e2eeMark": "2",
                }
            )
            # For E2EE messages, don't include plaintext
            text = None

        # Build message struct
        # Message struct fields:
        #   2: string to
        #   3: MIDType toType (enum/i32)
        #   10: string text
        #   11: Location location
        #   15: ContentType contentType (enum/i32)
        #   18: map<string, string> contentMetadata
        #   20: list<string> chunks (for E2EE)
        #   21: string relatedMessageId
        #   22: messageRelationType (enum)
        #   24: relatedMessageServiceCode (enum)
        to_type = self.client.get_to_type(to) or 0
        message_data: list = [
            [11, 2, to],  # to (field 2)
            [8, 3, to_type],  # toType (field 3)
            [8, 15, content_type],  # contentType (field 15)
        ]

        if text:
            message_data.append([11, 10, text])  # text (field 10)

        if location:
            message_data.append([12, 11, self._build_location(location)])  # location (field 11)

        if content_metadata:
            message_data.append(
                [13, 18, [ThriftType.STRING, ThriftType.STRING, content_metadata]]
            )  # contentMetadata (field 18)

        if chunks:
            message_data.append([15, 20, [ThriftType.STRING, chunks]])  # chunks (field 20)

        if related_message_id:
            message_data.extend(
                [
                    [11, 21, related_message_id],
                    [8, 22, 3],  # REPLY
                    [8, 24, 1],  # TALK
                ]
            )

        seq = await self.client.get_reqseq()

        try:
            return await self.client.request.request(
                [
                    [8, 1, seq],
                    [12, 2, message_data],
                ],
                "sendMessage",
                self.protocol_type,
                True,
                self.request_path,
            )
        except Exception as error:
            from ..client.exceptions import LineError

            # E2EE error codes that indicate we should retry with encryption:
            # 81 = E2EE_INVALID_PROTOCOL
            # 82 = E2EE_RETRY_ENCRYPT
            # 83 = E2EE_UPDATE_SENDER_KEY
            # 84 = E2EE_UPDATE_RECEIVER_KEY
            # 99 = E2EE_RECREATE_GROUP_KEY (old group key)
            e2ee_retry_codes = {81, 82, 83, 84, 99}

            if isinstance(error, LineError):
                # Get error code from data - can be at key 1 (numeric) or "code" (string key)
                error_code = error.data.get(1) or error.data.get("code")
                if isinstance(error_code, int) and error_code in e2ee_retry_codes:
                    # For error 99 (old group key), clear the cached group key and register new one
                    if error_code == 99:
                        to_type = self.client.get_to_type(to) or 0
                        if to_type != 0:  # Group chat (not USER)
                            logger.debug(
                                f"[E2EE] Error 99 (old group key), refreshing group key for {to[:20]}..."
                            )
                            # Clear cached group key
                            await self.client.storage.delete(f"e2eeGroupKeys:{to}")
                            # Register new group key
                            try:
                                await self.client.e2ee.try_register_e2ee_group_key(to)
                                logger.info(f"[E2EE] New group key registered for {to[:20]}...")
                            except Exception as reg_error:
                                logger.error(
                                    f"[E2EE] Failed to register new group key: {reg_error}"
                                )
                                raise error
                            # Retry with E2EE using the new group key
                            return await self.send_message(
                                to=to,
                                text=text,
                                content_type=content_type,
                                content_metadata=content_metadata,
                                related_message_id=related_message_id,
                                location=location,
                                e2ee=True,
                            )
                    # For other E2EE errors, just retry with E2EE if not already using it
                    elif not e2ee:
                        return await self.send_message(
                            to=to,
                            text=text,
                            content_type=content_type,
                            content_metadata=content_metadata,
                            related_message_id=related_message_id,
                            location=location,
                            e2ee=True,
                        )
            raise

    def _build_location(self, location: dict) -> list:
        """Build location thrift struct."""
        result = []
        if "title" in location:
            result.append([11, 1, location["title"]])
        if "address" in location:
            result.append([11, 2, location["address"]])
        if "latitude" in location:
            result.append([4, 3, location["latitude"]])
        if "longitude" in location:
            result.append([4, 4, location["longitude"]])
        if "phone" in location:
            result.append([11, 5, location["phone"]])
        return result

    async def get_profile(self) -> dict:
        """Get current user's profile."""
        return await self.client.request.request(
            [],
            "getProfile",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_contact(self, mid: str) -> dict:
        """Get contact information for a user."""
        return await self.client.request.request(
            [[11, 2, mid]],
            "getContact",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_contacts(self, mids: list[str]) -> list[dict]:
        """Get contact information for multiple users."""
        return await self.client.request.request(
            [[15, 2, [ThriftType.STRING, mids]]],
            "getContacts",
            self.protocol_type,
            False,
            self.request_path,
        )

    async def get_chat(
        self,
        chat_mid: str,
        with_invitees: bool = True,
        with_members: bool = True,
    ) -> dict:
        """Get chat information."""
        result = await self.get_chats([chat_mid], with_invitees, with_members)
        chats = result.get("chats", [])
        return chats[0] if chats else {}

    async def get_chats(
        self,
        chat_mids: list[str],
        with_invitees: bool = True,
        with_members: bool = True,
    ) -> dict:
        """Get information for multiple chats."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [15, 1, [ThriftType.STRING, chat_mids]],
                        [2, 2, with_members],
                        [2, 3, with_invitees],
                    ],
                ],
                [8, 2, 0],  # syncReason: INTERNAL
            ],
            "getChats",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_all_chat_mids(
        self,
        with_member_chats: bool = True,
        with_inviting_chats: bool = True,
    ) -> dict:
        """Get all chat MIDs the user is part of."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [2, 1, with_member_chats],
                        [2, 2, with_inviting_chats],
                    ],
                ],
                [8, 2, 0],  # syncReason
            ],
            "getAllChatMids",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def send_chat_checked(
        self,
        chat_mid: str,
        last_message_id: str,
    ) -> None:
        """Mark a chat as read."""
        seq = await self.client.get_reqseq()
        await self.client.request.request(
            [
                [8, 1, seq],
                [11, 2, chat_mid],
                [11, 3, last_message_id],
            ],
            "sendChatChecked",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def unsend_message(self, message_id: str) -> None:
        """Unsend (delete) a sent message."""
        seq = await self.client.get_reqseq()
        await self.client.request.request(
            [
                [8, 1, seq],
                [11, 2, message_id],
            ],
            "unsendMessage",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def react(
        self,
        message_id: int,
        reaction_type: int,
    ) -> None:
        """Add a reaction to a message."""
        await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [8, 1, 0],  # reqSeq
                        [10, 2, message_id],
                        [
                            12,
                            3,
                            [
                                [8, 1, reaction_type],
                            ],
                        ],
                    ],
                ],
            ],
            "react",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def update_chat(
        self,
        chat_mid: str,
        name: str | None = None,
        notification_disabled: bool | None = None,
    ) -> dict:
        """Update chat settings."""
        updated_attrs = []
        chat_data = [[11, 1, chat_mid]]

        if name is not None:
            updated_attrs.append(1)  # NAME
            chat_data.append([11, 6, name])

        if notification_disabled is not None:
            updated_attrs.append(4)  # NOTIFICATION_DISABLED
            chat_data.append([2, 9, notification_disabled])

        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [15, 1, [ThriftType.I32, updated_attrs]],
                        [12, 2, chat_data],
                    ],
                ],
            ],
            "updateChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def invite_into_chat(
        self,
        chat_mid: str,
        target_user_mids: list[str],
    ) -> dict:
        """Invite users into a chat."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, chat_mid],
                        [15, 2, [ThriftType.STRING, target_user_mids]],
                    ],
                ],
            ],
            "inviteIntoChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def delete_self_from_chat(self, chat_mid: str) -> dict:
        """Leave a chat."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, chat_mid],
                    ],
                ],
            ],
            "deleteSelfFromChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def create_chat(
        self,
        name: str,
        target_user_mids: list[str],
        notification_disabled: bool = False,
    ) -> dict:
        """Create a new chat."""
        seq = await self.client.get_reqseq()
        return await self.client.request.request(
            [
                [8, 1, seq],
                [
                    12,
                    2,
                    [
                        [8, 1, 2],  # GROUP
                        [11, 6, name],
                        [15, 7, [ThriftType.STRING, target_user_mids]],
                        [2, 9, notification_disabled],
                    ],
                ],
            ],
            "createChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def create_chat_room_announcement(
        self,
        chat_room_mid: str,
        ann_type: int,
        contents: dict,
    ) -> dict:
        """Create a chat room announcement (pin)."""
        seq = await self.client.get_reqseq()
        return await self.client.request.request(
            [
                [8, 1, seq],
                [11, 2, chat_room_mid],
                [8, 3, ann_type],
                [12, 4, self._build_announcement_contents(contents)],
            ],
            "createChatRoomAnnouncement",
            self.protocol_type,
            True,
            self.request_path,
        )

    def _build_announcement_contents(self, contents: dict) -> list:
        """Build announcement contents struct."""
        result = []
        if "displayFields" in contents:
            result.append([8, 1, contents["displayFields"]])
        if "text" in contents:
            result.append([11, 2, contents["text"]])
        if "link" in contents:
            result.append([11, 3, contents["link"]])
        if "thumbnail" in contents:
            result.append([11, 4, contents["thumbnail"]])
        return result

    async def get_all_contact_ids(self) -> list[str]:
        """Get all contact IDs."""
        return await self.client.request.request(
            [],
            "getAllContactIds",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_blocked_contact_ids(self) -> list[str]:
        """Get blocked contact IDs."""
        return await self.client.request.request(
            [],
            "getBlockedContactIds",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def block_contact(self, mid: str) -> None:
        """Block a contact."""
        seq = await self.client.get_reqseq()
        await self.client.request.request(
            [
                [8, 1, seq],
                [11, 2, mid],
            ],
            "blockContact",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def unblock_contact(self, mid: str) -> None:
        """Unblock a contact."""
        seq = await self.client.get_reqseq()
        await self.client.request.request(
            [
                [8, 1, seq],
                [11, 2, mid],
            ],
            "unblockContact",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_e2ee_public_keys(self) -> list[dict]:
        """Get E2EE public keys."""
        return await self.client.request.request(
            [],
            "getE2EEPublicKeys",
            self.protocol_type,
            False,
            self.request_path,
        )

    async def register_e2ee_public_key(
        self,
        req_seq: int,
        version: int,
        key_id: int,
        key_data: bytes,
        created_time: int,
    ) -> dict:
        """Register E2EE public key.

        registerE2EEPublicKey_args thrift struct:
            1: i32 reqSeq
            2: E2EEPublicKey publicKey
                1: i32 version
                2: i32 keyId
                4: binary keyData
                5: i64 createdTime

        Returns:
            The registered E2EEPublicKey from the server.
        """
        # Build E2EEPublicKey struct (Pb1_C13097n4)
        public_key_struct = [
            [8, 1, version],  # version
            [8, 2, key_id],  # keyId
            [11, 4, key_data],  # keyData (binary as STRING type)
            [10, 5, created_time],  # createdTime (i64)
        ]
        return await self.client.request.request(
            [
                [8, 1, req_seq],  # reqSeq
                [12, 2, public_key_struct],  # publicKey
            ],
            "registerE2EEPublicKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def negotiate_e2ee_public_key(self, mid: str) -> dict:
        """Negotiate E2EE public key with a user.

        negotiateE2EEPublicKey_args thrift struct:
            2: string mid
        """
        return await self.client.request.request(
            [[11, 2, mid]],  # mid is field 2 (string)
            "negotiateE2EEPublicKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_e2ee_public_key(self, mid: str, version: int, key_id: int) -> dict:
        """Get E2EE public key by key ID.

        getE2EEPublicKey_args thrift struct:
            2: string mid
            3: i32 keyVersion
            4: i32 keyId
        """
        return await self.client.request.request(
            [
                [11, 2, mid],  # mid is field 2 (string)
                [8, 3, version],  # keyVersion is field 3 (i32)
                [8, 4, key_id],  # keyId is field 4 (i32)
            ],
            "getE2EEPublicKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_last_e2ee_group_shared_key(
        self,
        key_version: int,
        chat_mid: str,
    ) -> dict:
        """Get last E2EE group shared key.

        getLastE2EEGroupSharedKey_args thrift struct:
            2: i32 keyVersion
            3: string chatMid
        """
        return await self.client.request.request(
            [
                [8, 2, key_version],  # keyVersion is field 2 (i32)
                [11, 3, chat_mid],  # chatMid is field 3 (string)
            ],
            "getLastE2EEGroupSharedKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_e2ee_group_shared_key(
        self,
        key_version: int,
        chat_mid: str,
        group_key_id: int,
    ) -> dict:
        """Get a specific E2EE group shared key by ID.

        getE2EEGroupSharedKey_args thrift struct:
            2: i32 keyVersion
            3: string chatMid
            4: i32 groupKeyId
        """
        return await self.client.request.request(
            [
                [8, 2, key_version],  # keyVersion is field 2 (i32)
                [11, 3, chat_mid],  # chatMid is field 3 (string)
                [8, 4, group_key_id],  # groupKeyId is field 4 (i32)
            ],
            "getE2EEGroupSharedKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_last_e2ee_public_keys(self, chat_mid: str) -> dict:
        """Get last E2EE public keys for all members in a chat.

        getLastE2EEPublicKeys_args thrift struct:
            2: string chatMid
        """
        return await self.client.request.request(
            [[11, 2, chat_mid]],
            "getLastE2EEPublicKeys",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def register_e2ee_group_key(
        self,
        key_version: int,
        chat_mid: str,
        members: list[str],
        key_ids: list[int],
        encrypted_shared_keys: list[bytes],
    ) -> dict:
        """Register E2EE group key for a chat.

        registerE2EEGroupKey_args thrift struct:
            2: i32 keyVersion
            3: string chatMid
            4: list<string> members
            5: list<i32> keyIds
            6: list<binary> encryptedSharedKeys (sent as STRING type but with binary data)

        Note: encryptedSharedKeys should be raw bytes, not base64 encoded.
        The thrift writer handles bytes correctly by using write_binary.
        """
        from ..thrift.types import ThriftType

        # Pass encrypted keys as raw bytes - the thrift writer handles bytes correctly
        # by using write_binary for bytes values in lists
        return await self.client.request.request(
            [
                [8, 2, key_version],
                [11, 3, chat_mid],
                [15, 4, [ThriftType.STRING, members]],
                [15, 5, [ThriftType.I32, key_ids]],
                [15, 6, [ThriftType.STRING, encrypted_shared_keys]],
            ],
            "registerE2EEGroupKey",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_server_time(self) -> int:
        """Get server time."""
        return await self.client.request.request(
            [],
            "getServerTime",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def noop(self) -> None:
        """No operation (keep-alive)."""
        await self.client.request.request(
            [],
            "noop",
            self.protocol_type,
            True,
            self.request_path,
        )
