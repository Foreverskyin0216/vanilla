"""HTTP request handling for LINE API."""

from typing import TYPE_CHECKING, Any

import httpx

from ..thrift import read_thrift, write_thrift
from ..thrift.types import NestedArray
from .exceptions import InternalError, LineError, SquareException, TalkException

if TYPE_CHECKING:
    from .base_client import BaseClient


class RequestClient:
    """Handles HTTP requests to LINE API."""

    def __init__(self, client: "BaseClient"):
        self.client = client
        self._http_client: httpx.AsyncClient | None = None

    @property
    def endpoint(self) -> str:
        """Get the API endpoint."""
        return self.client.endpoint

    @property
    def system_type(self) -> str:
        """Get the x-line-application header value."""
        d = self.client.device_details
        return f"{self.client.device}\t{d.app_version}\t{d.system_name}\t{d.system_version}"

    @property
    def user_agent(self) -> str:
        """Get the user-agent header value."""
        return f"Line/{self.client.device_details.app_version}"

    def get_header(self, method: str = "POST") -> dict[str, str]:
        """
        Get common request headers.

        Args:
            method: HTTP method for x-lhm header

        Returns:
            Headers dictionary
        """
        headers = {
            "Host": self.endpoint,
            "accept": "application/x-thrift",
            "user-agent": self.user_agent,
            "x-line-application": self.system_type,
            "content-type": "application/x-thrift",
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": method,
            "accept-encoding": "gzip",
        }
        if self.client.auth_token:
            headers["x-line-access"] = self.client.auth_token
        return headers

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.client.config.timeout / 1000),
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def request(
        self,
        value: NestedArray,
        method_name: str,
        protocol_type: int = 4,
        _parse_response: bool = True,  # Reserved for future use
        path: str = "/S4",
        additional_headers: dict[str, str] | None = None,
        timeout: int | None = None,
        _is_retry: bool = False,
    ) -> Any:
        """
        Make a thrift request to LINE API.

        Args:
            value: The thrift data to send
            method_name: The RPC method name
            protocol_type: 3 for Binary, 4 for Compact protocol
            _parse_response: Reserved for future use
            path: The API path
            additional_headers: Additional headers to include
            timeout: Request timeout in milliseconds
            _is_retry: Internal flag to prevent infinite retry loops

        Returns:
            The parsed response data

        Raises:
            InternalError: If the request fails
        """
        # Serialize request
        body = write_thrift(value, method_name, protocol_type)

        # Build headers
        headers = self.get_header("POST")
        if additional_headers:
            headers.update(additional_headers)

        # Build URL
        url = f"https://{self.endpoint}{path}"

        # Make request
        client = await self.get_http_client()
        timeout_seconds = (timeout or self.client.config.timeout) / 1000

        try:
            response = await client.post(
                url,
                content=body,
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as e:
            raise InternalError("TimeoutError", str(e)) from e
        except httpx.HTTPError as e:
            raise InternalError("HTTPError", str(e)) from e

        # Check for token rotation
        new_token = response.headers.get("x-line-next-access")
        if new_token:
            self.client.auth_token = new_token
            self.client.emit("update:authtoken", new_token)

        # Parse response
        response_data = response.content
        if not response_data:
            return None

        parsed = read_thrift(response_data, protocol_type)

        # Check for errors (field 1 is typically the exception)
        if 1 in parsed.data:
            error_data = parsed.data[1]
            error_code = error_data.get(1, "UNKNOWN")
            error_msg = error_data.get(2, "Unknown error")
            error_code_str = error_data.get("code", "")

            # Check if we need to refresh token
            if not _is_retry and error_code_str == "MUST_REFRESH_V3_TOKEN":
                refresh_token = await self.client.storage.get("refreshToken")
                if refresh_token:
                    try:
                        await self.client.auth.try_refresh_token()
                        # Retry the request with new token
                        return await self.request(
                            value=value,
                            method_name=method_name,
                            protocol_type=protocol_type,
                            _parse_response=_parse_response,
                            path=path,
                            additional_headers=additional_headers,
                            timeout=timeout,
                            _is_retry=True,
                        )
                    except Exception:
                        pass  # Fall through to raise original error

            raise self._create_exception(path, error_code, error_msg, error_data)

        # Return success result (field 0)
        if 0 in parsed.data:
            return parsed.data[0]

        return parsed.data

    def _create_exception(
        self,
        path: str,
        code: str,
        message: str,
        data: dict[str, Any],
    ) -> LineError:
        """Create an appropriate exception based on the path."""
        if "/SQ" in path:
            return SquareException(f"{code}: {message}", data)
        elif "/S" in path or "TalkService" in path:
            return TalkException(f"{code}: {message}", data)
        return InternalError(code, message, data)
