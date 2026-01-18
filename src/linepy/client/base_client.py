"""Base client implementation for LINE API."""

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..storage import BaseStorage, MemoryStorage
from .devices import get_device_details
from .events import TypedEventEmitter
from .request import RequestClient

if TYPE_CHECKING:
    from ..e2ee import E2EE
    from ..obs import OBS
    from ..services.auth import AuthService
    from ..services.square import SquareService
    from ..services.talk import TalkService
    from .login import Login


@dataclass
class Config:
    """Client configuration."""

    timeout: int = 30_000  # 30 seconds in milliseconds
    long_timeout: int = 180_000  # 180 seconds in milliseconds


@dataclass
class Profile:
    """User profile data."""

    mid: str
    display_name: str
    picture_status: str | None = None
    status_message: str | None = None
    raw: dict = field(default_factory=dict)


class BaseClient(TypedEventEmitter):
    """
    Base LINE client with core functionality.

    This provides low-level access to LINE API services.
    """

    def __init__(
        self,
        device: str,
        version: str | None = None,
        endpoint: str = "legy.line-apps.com",
        storage: BaseStorage | None = None,
    ):
        """
        Initialize the base client.

        Args:
            device: The device type (e.g., "DESKTOPWIN", "IOS")
            version: Optional custom app version
            endpoint: API endpoint (default: legy.line-apps.com)
            storage: Storage implementation (default: MemoryStorage)

        Raises:
            ValueError: If device is not supported
        """
        super().__init__()

        device_details = get_device_details(device, version)
        if not device_details:
            raise ValueError(f"Unsupported device: {device}")

        self.device = device
        self.device_details = device_details
        self.endpoint = endpoint
        self.storage = storage or MemoryStorage()
        self.config = Config()

        self.auth_token: str | None = None
        self.profile: Profile | None = None

        # Initialize request client
        self.request = RequestClient(self)

        # Request sequence counters
        self._reqseqs: dict[str, int] | None = None

    async def close(self) -> None:
        """Close the client and release resources."""
        await self.request.close()

    @property
    def system_type(self) -> str:
        """Get the system type header value."""
        return self.device_details.system_type

    def get_to_type(self, mid: str) -> int | None:
        """
        Get the type of a MID based on its first character.

        Args:
            mid: The messenger ID

        Returns:
            The type code or None if unknown
        """
        type_mapping = {
            "u": 0,  # User
            "r": 1,  # Room
            "c": 2,  # Chat (Group)
            "s": 3,  # Square
            "m": 4,  # Bot
            "p": 5,  # Page
            "v": 6,  # Voom
            "t": 7,  # Timeline
        }
        if mid:
            return type_mapping.get(mid[0])
        return None

    async def get_reqseq(self, name: str = "talk") -> int:
        """
        Get and increment a request sequence number.

        Args:
            name: The service name

        Returns:
            The current sequence number
        """
        if self._reqseqs is None:
            stored = await self.storage.get("reqseq")
            if stored:
                self._reqseqs = json.loads(str(stored))
            else:
                self._reqseqs = {}

        if name not in self._reqseqs:
            self._reqseqs[name] = 0

        seq = self._reqseqs[name]
        self._reqseqs[name] += 1
        await self.storage.set("reqseq", json.dumps(self._reqseqs))
        return seq

    def log(self, log_type: str, data: dict[str, Any]) -> None:
        """
        Emit a log event.

        Args:
            log_type: The type of log
            data: Log data
        """
        self.emit("log", {"type": log_type, "data": data})

    # Lazy-loaded service references
    _talk_service: Any = None
    _square_service: Any = None
    _auth_service: Any = None
    _e2ee: Any = None
    _obs: Any = None
    _login: Any = None

    @property
    def talk(self) -> "TalkService":
        """Get the Talk service."""
        if self._talk_service is None:
            from ..services.talk import TalkService

            self._talk_service = TalkService(self)
        return self._talk_service

    @property
    def square(self) -> "SquareService":
        """Get the Square service."""
        if self._square_service is None:
            from ..services.square import SquareService

            self._square_service = SquareService(self)
        return self._square_service

    @property
    def auth(self) -> "AuthService":
        """Get the Auth service."""
        if self._auth_service is None:
            from ..services.auth import AuthService

            self._auth_service = AuthService(self)
        return self._auth_service

    @property
    def e2ee(self) -> "E2EE":
        """Get the E2EE handler."""
        if self._e2ee is None:
            from ..e2ee import E2EE

            self._e2ee = E2EE(self)
        return self._e2ee

    @property
    def obs(self) -> "OBS":
        """Get the OBS (file handling) service."""
        if self._obs is None:
            from ..obs import OBS

            self._obs = OBS(self)
        return self._obs

    @property
    def login_process(self) -> "Login":
        """Get the login handler."""
        if self._login is None:
            from .login import Login

            self._login = Login(self)
        return self._login
