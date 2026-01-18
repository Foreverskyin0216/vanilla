"""Auth service for token refresh and authentication."""

from typing import TYPE_CHECKING

from ..client.exceptions import InternalError

if TYPE_CHECKING:
    from ..client.base_client import BaseClient


class AuthService:
    """
    Auth service for token refresh and authentication operations.

    Handles token refresh to avoid repeated logins.
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.protocol_type = 4
        self.request_path = "/AS4"

    async def try_refresh_token(self) -> bool:
        """
        Try to refresh the auth token using a stored refresh token.

        Returns:
            True if refresh was successful, False otherwise

        Raises:
            InternalError: If refresh token is not found
        """
        refresh_token = await self.client.storage.get("refreshToken")

        if not refresh_token or not isinstance(refresh_token, str):
            raise InternalError("refreshError", "refreshToken not found")

        try:
            result = await self._refresh(refresh_token)

            # Extract access token from result
            access_token = result.get("accessToken") or result.get(1)
            if not access_token:
                raise InternalError("refreshError", "No access token in response")

            self.client.auth_token = access_token
            self.client.emit("update:authtoken", access_token)

            # Update expiration info if available
            token_issue_time = result.get("tokenIssueTimeEpochSec") or result.get(4)
            duration_until_refresh = result.get("durationUntilRefreshInSec") or result.get(5)

            if token_issue_time and duration_until_refresh:
                await self.client.storage.set(
                    "expire",
                    int(token_issue_time) + int(duration_until_refresh),
                )

            return True

        except Exception as e:
            self.client.log("auth", {"error": "refresh_failed", "message": str(e)})
            raise

    async def _refresh(self, refresh_token: str) -> dict:
        """
        Make the refresh token request.

        Args:
            refresh_token: The refresh token to use

        Returns:
            The response containing the new access token
        """
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, refresh_token],
                    ],
                ],
            ],
            "refresh",
            self.protocol_type,
            True,
            "/EXT/auth/tokenrefresh/v1",
        )

    async def has_valid_token(self) -> bool:
        """
        Check if we have a valid auth token or refresh token.

        Returns:
            True if we have a potentially valid token setup
        """
        if self.client.auth_token:
            return True

        refresh_token = await self.client.storage.get("refreshToken")
        return refresh_token is not None
