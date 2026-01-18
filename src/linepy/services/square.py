"""Square service for OpenChat/community chat."""

from typing import TYPE_CHECKING

from ..thrift.types import ThriftType

if TYPE_CHECKING:
    from ..client.base_client import BaseClient


class SquareService:
    """
    Square service for OpenChat/community chat operations.

    Handles Square (OpenChat) messaging, management, and events.
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.protocol_type = 4
        self.request_path = "/SQ1"

    async def get_joined_squares(
        self,
        limit: int = 100,
        continuation_token: str | None = None,
    ) -> dict:
        """Get list of joined Squares.

        GetJoinedSquaresRequest thrift struct:
            2: string continuationToken
            3: i32 limit
        """
        request_data: list[list] = [[8, 3, limit]]  # limit is field 3 (i32)
        if continuation_token:
            request_data.append(
                [11, 2, continuation_token]
            )  # continuationToken is field 2 (string)

        return await self.client.request.request(
            [[12, 1, request_data]],
            "getJoinedSquares",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_square(self, square_mid: str) -> dict:
        """Get Square information."""
        return await self.client.request.request(
            [[12, 1, [[11, 2, square_mid]]]],
            "getSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_square_chat(self, square_chat_mid: str) -> dict:
        """Get Square chat information."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, square_chat_mid]]]],
            "getSquareChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def fetch_my_events(
        self,
        sync_token: str | None = None,
        continuation_token: str | None = None,
        limit: int = 100,
        subscription_id: int | None = None,
        timeout: int | None = None,
    ) -> dict:
        """Fetch personalized Square events.

        FetchMyEventsRequest thrift struct:
            1: i64 subscriptionId
            2: string syncToken
            3: i32 limit
            4: string continuationToken

        Args:
            timeout: Request timeout in milliseconds (defaults to long_timeout for long polling)
        """
        request_data: list[list] = [[8, 3, limit]]  # limit is field 3 (i32)
        if subscription_id is not None:
            request_data.append([10, 1, subscription_id])  # subscriptionId is field 1 (i64)
        if sync_token:
            request_data.append([11, 2, sync_token])  # syncToken is field 2 (string)
        if continuation_token:
            request_data.append(
                [11, 4, continuation_token]
            )  # continuationToken is field 4 (string)

        return await self.client.request.request(
            [[12, 1, request_data]],
            "fetchMyEvents",
            self.protocol_type,
            True,
            self.request_path,
            {},
            timeout or self.client.config.long_timeout,
        )

    async def fetch_square_chat_events(
        self,
        square_chat_mid: str,
        sync_token: str | None = None,
        limit: int = 100,
        direction: int = 1,  # 1=FORWARD, 2=BACKWARD
        thread_mid: str | None = None,
    ) -> dict:
        """Fetch Square chat events/messages."""
        request_data = [
            [11, 1, square_chat_mid],
            [8, 4, limit],
            [8, 5, direction],
        ]
        if sync_token:
            request_data.append([11, 2, sync_token])
        if thread_mid:
            request_data.append([11, 6, thread_mid])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "fetchSquareChatEvents",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def send_message(
        self,
        square_chat_mid: str,
        text: str | None = None,
        content_type: int = 0,
        content_metadata: dict[str, str] | None = None,
        related_message_id: str | None = None,
        location: dict | None = None,
    ) -> dict:
        """Send a message to a Square chat.

        Message struct fields:
            2: string to
            10: string text
            11: Location location
            15: ContentType contentType (enum/i32)
            18: map<string, string> contentMetadata
            21: string relatedMessageId
            22: Pb1_EnumC13015h6 messageRelationType (enum)
            24: Pb1_E7 relatedMessageServiceCode (enum)
        """
        content_metadata = content_metadata or {}
        seq = await self.client.get_reqseq("sq")

        message_data: list = [
            [11, 2, square_chat_mid],  # to (field 2)
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

        if related_message_id:
            message_data.extend(
                [
                    [11, 21, related_message_id],  # relatedMessageId (field 21)
                    [8, 22, 3],  # messageRelationType = REPLY (field 22)
                    [8, 24, 2],  # relatedMessageServiceCode = SQUARE (field 24)
                ]
            )

        # SendMessageRequest struct:
        #   1: i32 reqSeq
        #   2: string squareChatMid
        #   3: SquareMessage squareMessage
        #
        # SquareMessage struct:
        #   1: Message message
        #   4: i64 squareMessageRevision
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [8, 1, seq],  # reqSeq
                        [11, 2, square_chat_mid],  # squareChatMid
                        [
                            12,
                            3,  # squareMessage
                            [
                                [12, 1, message_data],  # message (Message struct)
                                [10, 4, 4],  # squareMessageRevision (field 4, i64)
                            ],
                        ],
                    ],
                ],
            ],
            "sendMessage",
            self.protocol_type,
            True,
            self.request_path,
        )

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

    async def join_square(
        self,
        square_mid: str,
        display_name: str,
        able_to_receive_message: bool = True,
        pass_code: str | None = None,
        join_message: str | None = None,
    ) -> dict:
        """Join a Square."""
        join_value = []
        if join_message:
            join_value.append([12, 1, [[11, 1, join_message]]])
        if pass_code:
            join_value.append([12, 2, [[11, 1, pass_code]]])

        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 2, square_mid],
                        [
                            12,
                            3,
                            [
                                [11, 2, square_mid],
                                [11, 3, display_name],
                                [2, 7, able_to_receive_message],
                                [10, 9, 0],  # revision
                            ],
                        ],
                        [12, 4, join_value] if join_value else None,
                    ],
                ],
            ],
            "joinSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def leave_square(self, square_mid: str) -> dict:
        """Leave a Square."""
        return await self.client.request.request(
            [[12, 1, [[11, 2, square_mid]]]],
            "leaveSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def join_square_chat(self, square_chat_mid: str) -> dict:
        """Join a Square chat."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, square_chat_mid]]]],
            "joinSquareChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def leave_square_chat(self, square_chat_mid: str) -> dict:
        """Leave a Square chat."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, square_chat_mid],
                        [2, 2, True],  # sayGoodbye
                    ],
                ],
            ],
            "leaveSquareChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_square_chat_members(
        self,
        square_chat_mid: str,
        limit: int = 100,
        continuation_token: str | None = None,
    ) -> dict:
        """Get members of a Square chat."""
        request_data = [
            [11, 1, square_chat_mid],
            [8, 3, limit],
        ]
        if continuation_token:
            request_data.append([11, 2, continuation_token])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "getSquareChatMembers",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_square_member(self, square_member_mid: str) -> dict:
        """Get Square member information."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, square_member_mid]]]],
            "getSquareMember",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def mark_as_read(
        self,
        square_chat_mid: str,
        message_id: str,
        thread_mid: str | None = None,
    ) -> dict:
        """Mark messages as read."""
        request_data = [
            [11, 2, square_chat_mid],
            [11, 4, message_id],
        ]
        if thread_mid:
            request_data.append([11, 3, thread_mid])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "markAsRead",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def react_to_message(
        self,
        square_chat_mid: str,
        message_id: str,
        reaction_type: int,
        thread_mid: str | None = None,
    ) -> dict:
        """React to a message."""
        request_data = [
            [8, 1, 0],  # reqSeq
            [11, 2, square_chat_mid],
            [11, 3, message_id],
            [8, 4, reaction_type],
        ]
        if thread_mid:
            request_data.append([11, 5, thread_mid])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "reactToMessage",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def unsend_message(
        self,
        square_chat_mid: str,
        message_id: str,
        thread_mid: str | None = None,
    ) -> dict:
        """Unsend a message."""
        request_data = [
            [11, 2, square_chat_mid],
            [11, 3, message_id],
        ]
        if thread_mid:
            request_data.append([11, 4, thread_mid])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "unsendMessage",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def destroy_message(
        self,
        square_chat_mid: str,
        message_id: str,
        thread_mid: str | None = None,
    ) -> dict:
        """Destroy (admin delete) a message."""
        request_data = [
            [11, 2, square_chat_mid],
            [11, 3, message_id],
        ]
        if thread_mid:
            request_data.append([11, 4, thread_mid])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "destroyMessage",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def update_square(
        self,
        square_mid: str,
        name: str | None = None,
        description: str | None = None,
        searchable: bool | None = None,
    ) -> dict:
        """Update Square settings."""
        updated_attrs = []
        square_data = [[11, 1, square_mid]]

        if name is not None:
            updated_attrs.append(2)  # NAME
            square_data.append([11, 2, name])

        if description is not None:
            updated_attrs.append(4)  # DESC
            square_data.append([11, 5, description])

        if searchable is not None:
            updated_attrs.append(8)  # SEARCHABLE
            square_data.append([2, 6, searchable])

        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [15, 2, [ThriftType.I32, updated_attrs]],
                        [12, 3, square_data],
                    ],
                ],
            ],
            "updateSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def update_square_chat(
        self,
        square_chat_mid: str,
        name: str | None = None,
    ) -> dict:
        """Update Square chat settings."""
        updated_attrs = []
        chat_data = [[11, 1, square_chat_mid]]

        if name is not None:
            updated_attrs.append(2)  # NAME
            chat_data.append([11, 2, name])

        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [15, 2, [ThriftType.I32, updated_attrs]],
                        [12, 3, chat_data],
                    ],
                ],
            ],
            "updateSquareChat",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def create_square(
        self,
        square_name: str,
        display_name: str,
        profile_image_obs_hash: str | None = None,
        description: str | None = None,
        searchable: bool = True,
        join_method_type: int = 0,  # NONE
    ) -> dict:
        """Create a new Square."""
        seq = await self.client.get_reqseq("sq")
        # Default profile image hash
        default_hash = (
            "0h6tJfahRYaVt3H0eLAsAWDFheczgHd3wTCTx2eApNKSoefHNVGRdwfgxbdgUMLi8"
            "MSngnPFMeNmpbLi8MSngnPFMeNmpbLi8MSngnPQ"
        )

        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [8, 1, seq],
                        [
                            12,
                            2,
                            [
                                [11, 2, square_name],
                                [11, 4, profile_image_obs_hash or default_hash],
                                [11, 5, description],
                                [2, 6, searchable],
                                [8, 7, 1],  # OPEN
                                [8, 8, 1],  # categoryId
                                [10, 10, 0],  # revision
                                [2, 11, True],  # ableToUseInvitationTicket
                                [12, 14, [[8, 1, join_method_type]]],  # joinMethod
                                [8, 17, 0],  # adultOnly: NONE
                                [15, 18, [ThriftType.STRING, []]],  # svcTags
                            ],
                        ],
                        [
                            12,
                            3,
                            [
                                [11, 3, display_name],
                                [2, 7, True],  # ableToReceiveMessage
                                [10, 9, 0],  # revision
                            ],
                        ],
                    ],
                ],
            ],
            "createSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def search_squares(
        self,
        query: str,
        limit: int = 20,
        continuation_token: str | None = None,
    ) -> dict:
        """Search for Squares."""
        request_data = [
            [11, 2, query],
            [8, 4, limit],
        ]
        if continuation_token:
            request_data.append([11, 3, continuation_token])

        return await self.client.request.request(
            [[12, 1, request_data]],
            "searchSquares",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def find_square_by_invitation_ticket(self, ticket: str) -> dict:
        """Find a Square by invitation ticket."""
        return await self.client.request.request(
            [[12, 1, [[11, 2, ticket]]]],
            "findSquareByInvitationTicket",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def get_invitation_ticket_url(self, square_mid: str) -> dict:
        """Get invitation ticket URL for a Square."""
        return await self.client.request.request(
            [[12, 1, [[11, 2, square_mid]]]],
            "getInvitationTicketUrl",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def create_square_chat_announcement(
        self,
        square_chat_mid: str,
        sender_mid: str,
        message_id: str,
        text: str,
        created_at: int,
    ) -> dict:
        """Create a Square chat announcement (pin)."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [8, 1, 0],  # reqSeq
                        [11, 2, square_chat_mid],
                        [
                            12,
                            3,
                            [
                                [10, 1, 0],  # announcementSeq
                                [8, 2, 0],  # type
                                [
                                    12,
                                    3,
                                    [
                                        [
                                            12,
                                            1,
                                            [
                                                [11, 1, sender_mid],
                                                [11, 2, message_id],
                                                [11, 3, text],
                                            ],
                                        ],
                                    ],
                                ],
                                [10, 4, created_at],
                            ],
                        ],
                    ],
                ],
            ],
            "createSquareChatAnnouncement",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def invite_to_square(
        self,
        square_mid: str,
        invitee_mids: list[str],
    ) -> dict:
        """Invite users to a Square."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 2, square_mid],
                        [15, 3, [ThriftType.STRING, invitee_mids]],
                    ],
                ],
            ],
            "inviteToSquare",
            self.protocol_type,
            True,
            self.request_path,
        )

    async def invite_into_square_chat(
        self,
        square_chat_mid: str,
        invitee_member_mids: list[str],
    ) -> dict:
        """Invite members into a Square chat."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, square_chat_mid],
                        [15, 2, [ThriftType.STRING, invitee_member_mids]],
                    ],
                ],
            ],
            "inviteIntoSquareChat",
            self.protocol_type,
            True,
            self.request_path,
        )
