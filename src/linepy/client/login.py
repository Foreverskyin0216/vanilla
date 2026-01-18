"""Login handling for LINE API (v3 only)."""

import base64
import re
from typing import TYPE_CHECKING

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from src.logging import get_logger

from .exceptions import InternalError

if TYPE_CHECKING:
    from .base_client import BaseClient

logger = get_logger(__name__)


EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_REGEX = re.compile(r"^.{4,}$")


class Login:
    """Handles LINE authentication flows (v3 only)."""

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.cert: str | None = None
        self.qr_cert: str | None = None

    async def register_cert(self, cert: str, email: str) -> None:
        """Register a certificate for email login."""
        await self.client.storage.set(f"cert:{email}", cert)

    async def get_cert(self, email: str) -> str | None:
        """Get stored certificate for email."""
        return await self.client.storage.get(f"cert:{email}")

    async def register_qr_cert(self, qr_cert: str) -> None:
        """Register a certificate for QR login."""
        await self.client.storage.set("qrCert", qr_cert)

    async def get_qr_cert(self) -> str | None:
        """Get stored QR certificate."""
        return await self.client.storage.get("qrCert")

    async def ready(self) -> None:
        """Complete login by fetching profile."""
        if not self.client.auth_token:
            raise InternalError("NotAuthorized", "try login first")
        profile_data = await self.client.talk.get_profile()
        from .base_client import Profile

        # Thrift field IDs for Profile struct:
        # 1 = mid, 20 = displayName, 22 = pictureStatus, 24 = statusMessage
        FIELD_MID = 1
        FIELD_DISPLAY_NAME = 20
        FIELD_PICTURE_STATUS = 22
        FIELD_STATUS_MESSAGE = 24

        self.client.profile = Profile(
            mid=profile_data.get(FIELD_MID) or profile_data.get("mid", ""),
            display_name=profile_data.get(FIELD_DISPLAY_NAME)
            or profile_data.get("displayName", ""),
            picture_status=profile_data.get(FIELD_PICTURE_STATUS)
            or profile_data.get("pictureStatus"),
            status_message=profile_data.get(FIELD_STATUS_MESSAGE)
            or profile_data.get("statusMessage"),
            raw=profile_data,
        )

        # Verify and sync E2EE key with server
        try:
            await self.client.e2ee.verify_and_sync_e2ee_key()
        except Exception as e:
            logger.warning(f"E2EE key verification failed: {e}")

        self.client.emit("ready", self.client.profile)

    async def login(
        self,
        auth_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        qr: bool = False,
        pincode: str | None = None,
    ) -> None:
        """
        Login to LINE.

        Args:
            auth_token: Existing auth token to reuse
            email: Email for password login
            password: Password for password login
            qr: Whether to use QR code login
            pincode: Custom pincode for email login

        Raises:
            InternalError: If login fails
        """
        if auth_token:
            self.client.emit("update:authtoken", auth_token)
            self.client.auth_token = auth_token
        elif email and password:
            await self.with_password(email, password, pincode)
        elif qr:
            await self.with_qr_code()
        else:
            raise InternalError(
                "InvalidLoginMethod", "Provide auth_token, email/password, or qr=True"
            )

        await self.ready()

    async def with_qr_code(self) -> None:
        """Login with QR code (v3)."""
        auth_token = await self.request_sqr2()
        self.client.emit("update:authtoken", auth_token)
        self.client.auth_token = auth_token

    async def request_sqr2(self) -> str:
        """
        Request QR code login (v3).

        Returns:
            The auth token

        Raises:
            InternalError: If login fails
        """
        # Create session
        session_response = await self.create_session()
        sqr = session_response.get(1)
        if sqr is None:
            from .exceptions import InternalError

            raise InternalError("LOGIN_ERROR", "Failed to create session")

        # Create QR code
        qr_response = await self.create_qr_code(sqr)
        url = qr_response.get(1)
        if url is None:
            raise InternalError("LOGIN_ERROR", "Failed to create QR code URL")

        # Add E2EE secret to URL
        secret, secret_url = self.client.e2ee.create_sqr_secret()
        url = url + secret_url

        self.client.emit("qrcall", url)

        # Wait for QR code to be verified
        if await self.check_qr_code_verified(sqr):
            # Try to verify with existing certificate
            try:
                qr_cert = await self.get_qr_cert()
                await self.verify_certificate(sqr, qr_cert)
            except Exception:
                # Need pincode verification
                pin_response = await self.create_pin_code(sqr)
                pincode = pin_response.get(1)
                self.client.emit("pincall", pincode)
                await self.check_pin_code_verified(sqr)

            # Complete login
            response = await self.qr_code_login_v2(sqr)
            pem = response.get(1)
            token_info = response.get(3)
            e2ee_info = response.get(10)

            if pem:
                self.client.emit("update:qrcert", pem)
                await self.register_qr_cert(pem)

            if e2ee_info:
                await self.client.e2ee.decode_e2ee_key_v1(e2ee_info, secret)

            if token_info is None:
                raise InternalError("LOGIN_ERROR", "No token info in QR login response")

            refresh_token = token_info.get(2)
            expire_time = token_info.get(3)
            expire_offset = token_info.get(6)
            if refresh_token is not None:
                await self.client.storage.set("refreshToken", refresh_token)
            if expire_time is not None and expire_offset is not None:
                await self.client.storage.set("expire", expire_time + expire_offset)

            auth_token = token_info.get(1)
            if auth_token is None:
                raise InternalError("LOGIN_ERROR", "No auth token returned")
            return auth_token

        raise InternalError("TimeoutError", "checkQrCodeVerified timed out")

    async def with_password(
        self,
        email: str,
        password: str,
        pincode: str | None = None,
    ) -> None:
        """Login with email and password (v3)."""
        auth_token = await self.request_email_login_v2(email, password, pincode or "114514")
        self.client.emit("update:authtoken", auth_token)
        self.client.auth_token = auth_token

    async def request_email_login_v2(
        self,
        email: str,
        password: str,
        constant_pincode: str = "114514",
    ) -> str:
        """
        Request email login (v3).

        Args:
            email: Account email
            password: Account password
            constant_pincode: Custom pincode (6 digits)

        Returns:
            The auth token

        Raises:
            InternalError: If login fails
        """
        if not EMAIL_REGEX.match(email):
            raise InternalError("RegExpUnmatch", "invalid email")
        if not PASSWORD_REGEX.match(password):
            raise InternalError("RegExpUnmatch", "invalid password")
        if len(constant_pincode) != 6:
            raise InternalError("Invalid constant pincode", "must be 6 digits")

        self.client.log(
            "login",
            {
                "method": "email",
                "email": email,
                "password_length": len(password),
                "constant_pincode": constant_pincode,
            },
        )

        # Get RSA key
        # Response fields: 1=keynm, 2=nvalue, 3=evalue, 4=sessionKey
        rsa_key = await self.get_rsa_key_info()
        keynm = rsa_key.get("keynm") or rsa_key.get(1)
        nvalue = rsa_key.get("nvalue") or rsa_key.get(2)
        evalue = rsa_key.get("evalue") or rsa_key.get(3)
        session_key = rsa_key.get("sessionKey") or rsa_key.get(4)

        if not keynm or not session_key or not nvalue or not evalue:
            from .exceptions import InternalError

            raise InternalError("RSA_KEY_ERROR", "Failed to get RSA key info")

        # Encrypt credentials
        message = (
            chr(len(session_key))
            + session_key
            + chr(len(email))
            + email
            + chr(len(password))
            + password
        )
        encrypted_message = self._encrypt_rsa(message, nvalue, evalue)

        # Create E2EE data
        secret, secret_pk = self.client.e2ee.create_sqr_secret(base64_only=True)
        e2ee_data = self.client.e2ee.encrypt_aes_ecb(
            self.client.e2ee.get_sha256_sum(constant_pincode.encode()),
            base64.b64decode(secret_pk),
        )

        cert = await self.get_cert(email)

        # First login attempt - try loginZ first (LINE v1 API), then loginV2 as fallback
        try:
            response = await self._login_v2(
                str(keynm),
                encrypted_message,
                self.client.device,
                None,
                e2ee_data,
                cert,
                "loginZ",
            )
        except Exception as e:
            self.client.log("login", {"loginZ_failed": str(e), "fallback": "loginV2"})
            response = await self._login_v2(
                str(keynm),
                encrypted_message,
                self.client.device,
                None,
                e2ee_data,
                cert,
                "loginV2",
            )

        # Check if pincode verification needed
        if not response.get(9):
            self.client.emit("pincall", constant_pincode)

            # Fetch E2EE info
            access_token = response.get(3)
            if access_token is None:
                from .exceptions import InternalError

                raise InternalError("LOGIN_ERROR", "No access token in response")

            headers: dict[str, str] = {
                "accept": "application/x-thrift",
                "user-agent": self.client.request.user_agent,
                "x-line-application": self.client.request.system_type,
                "x-line-access": access_token,
                "x-lal": "ja_JP",
                "x-lpv": "1",
                "x-lhm": "GET",
                "accept-encoding": "gzip",
            }

            import httpx

            # LF1 is a long-polling endpoint that waits for PIN verification
            async with httpx.AsyncClient(timeout=180.0) as http:
                e2ee_response = await http.get(
                    f"https://{self.client.endpoint}/LF1",
                    headers=headers,
                )
                e2ee_info = e2ee_response.json().get("result", {})

            self.client.log("response", e2ee_info)

            metadata = e2ee_info.get("metadata", {})
            await self.client.e2ee.decode_e2ee_key_v1(metadata, secret)

            # Encrypt device secret
            device_secret = self.client.e2ee.encrypt_device_secret(
                base64.b64decode(metadata.get("publicKey")),
                secret,
                base64.b64decode(metadata.get("encryptedKeyChain")),
            )

            # Confirm E2EE login
            e2ee_verifier = await self.confirm_e2ee_login(access_token, device_secret)

            # Retry login with verifier
            response = await self._login_v2(
                str(keynm),
                encrypted_message,
                self.client.device,
                e2ee_verifier,
                e2ee_data,
                cert,
                "loginV2",
            )

        # Save certificate
        cert_value = response.get(2)
        if cert_value:
            self.client.emit("update:cert", cert_value)
            await self.register_cert(cert_value, email)

        # Save refresh token
        token_info = response.get(9)
        if token_info is None:
            from .exceptions import InternalError

            raise InternalError("LOGIN_ERROR", "No token info in response")

        refresh_token = token_info.get(2)
        expire_time = token_info.get(3)
        expire_offset = token_info.get(6)

        if refresh_token is not None:
            await self.client.storage.set("refreshToken", refresh_token)
        if expire_time is not None and expire_offset is not None:
            await self.client.storage.set("expire", expire_time + expire_offset)

        auth_token = token_info.get(1)
        if auth_token is None:
            from .exceptions import InternalError

            raise InternalError("LOGIN_ERROR", "No auth token in response")

        return auth_token

    def _encrypt_rsa(self, message: str, nvalue: str, evalue: str) -> str:
        """Encrypt message with RSA public key using PKCS#1 v1.5 padding."""
        n = int(nvalue, 16)
        e = int(evalue, 16)
        key = RSA.construct((n, e))
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(message.encode("utf-8"))
        return encrypted.hex()

    async def get_rsa_key_info(self, provider: int = 0) -> dict:
        """Get RSA key info for login."""
        return await self.client.request.request(
            [[12, 1, [[8, 2, provider]]]],
            "getRSAKeyInfo",
            3,
            True,
            "/api/v3/TalkService.do",
        )

    async def _login_v2(
        self,
        keynm: str,
        encrypted_message: str,
        device_name: str,
        verifier: str | None,
        secret: bytes | None,
        cert: str | None,
        method_name: str,
    ) -> dict:
        """Internal login request."""
        login_type = 2
        if not secret:
            login_type = 0
        if verifier:
            login_type = 1

        return await self.client.request.request(
            [
                [
                    12,
                    2,
                    [
                        [8, 1, login_type],
                        [8, 2, 1],
                        [11, 3, keynm],
                        [11, 4, encrypted_message],
                        [2, 5, 0],
                        [11, 6, ""],
                        [11, 7, device_name],
                        [11, 8, cert],
                        [11, 9, verifier],
                        [11, 10, secret],
                        [8, 11, 1],
                        [11, 12, "System Product Name"],
                    ],
                ],
            ],
            method_name,
            3,
            False,
            "/api/v3p/rs",
        )

    async def create_session(self) -> dict:
        """Create login session."""
        return await self.client.request.request(
            [],
            "createSession",
            4,
            False,
            "/acct/lgn/sq/v1",
        )

    async def create_qr_code(self, qrcode: str) -> dict:
        """Create QR code for login."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, qrcode]]]],
            "createQrCode",
            4,
            False,
            "/acct/lgn/sq/v1",
        )

    async def check_qr_code_verified(self, qrcode: str) -> bool:
        """Check if QR code has been verified."""
        try:
            await self.client.request.request(
                [[12, 1, [[11, 1, qrcode]]]],
                "checkQrCodeVerified",
                4,
                False,
                "/acct/lp/lgn/sq/v1",
                {"x-lst": "180000", "x-line-access": qrcode},
                self.client.config.long_timeout,
            )
            return True
        except Exception:
            raise

    async def verify_certificate(
        self,
        qrcode: str,
        cert: str | None,
    ) -> dict:
        """Verify certificate for login."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, qrcode], [11, 2, cert]]]],
            "verifyCertificate",
            4,
            False,
            "/acct/lgn/sq/v1",
        )

    async def create_pin_code(self, qrcode: str) -> dict:
        """Create pin code for login."""
        return await self.client.request.request(
            [[12, 1, [[11, 1, qrcode]]]],
            "createPinCode",
            4,
            False,
            "/acct/lgn/sq/v1",
        )

    async def check_pin_code_verified(self, qrcode: str) -> bool:
        """Check if pin code has been verified."""
        try:
            await self.client.request.request(
                [[12, 1, [[11, 1, qrcode]]]],
                "checkPinCodeVerified",
                4,
                False,
                "/acct/lp/lgn/sq/v1",
                {"x-lst": "180000", "x-line-access": qrcode},
                self.client.config.long_timeout,
            )
            return True
        except Exception:
            raise

    async def qr_code_login_v2(
        self,
        auth_session_id: str,
        model_name: str = "evex-device",
        system_name: str = "linejs-py-v2",
        auto_login_required: bool = True,
    ) -> dict:
        """Complete QR code login (v2)."""
        return await self.client.request.request(
            [
                [
                    12,
                    1,
                    [
                        [11, 1, auth_session_id],
                        [11, 2, system_name],
                        [11, 3, model_name],
                        [2, 4, auto_login_required],
                    ],
                ]
            ],
            "qrCodeLoginV2",
            4,
            False,
            "/acct/lgn/sq/v1",
        )

    async def confirm_e2ee_login(
        self,
        verifier: str,
        device_secret: bytes,
    ) -> dict:
        """Confirm E2EE login."""
        return await self.client.request.request(
            [
                [11, 1, verifier],
                [11, 2, device_secret],
            ],
            "confirmE2EELogin",
            3,
            False,
            "/api/v3p/rs",
        )
