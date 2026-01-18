"""Object storage service for media upload/download."""

import json
from base64 import b64decode, b64encode
from typing import TYPE_CHECKING, Literal

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from ..thrift import write_thrift

if TYPE_CHECKING:
    from ..client.base_client import BaseClient

ObjType = Literal["image", "gif", "video", "audio", "file"]


class OBS:
    """
    Object storage service for media upload/download.

    Handles file uploads and downloads for LINE messaging.
    """

    OBS_HOST = "obs.line-apps.com"

    # Content type mappings: (obs_namespace, content_type_id)
    TYPE_MAP: dict[ObjType, tuple[str, int]] = {
        "image": ("emi", 1),
        "gif": ("emi", 1),
        "video": ("emv", 2),
        "audio": ("ema", 3),
        "file": ("emf", 14),
    }

    def __init__(self, client: "BaseClient"):
        self.client = client

    async def upload_object(
        self,
        data: bytes,
        obj_type: ObjType = "image",
        obs_path: str = "talk/m",
        oid: str | None = None,
        filename: str | None = None,
        params: dict[str, str] | None = None,
        add_headers: dict[str, str] | None = None,
    ) -> dict:
        """
        Upload a file to LINE's object storage.

        Args:
            data: File data as bytes
            obj_type: Type of object (image, gif, video, audio, file)
            obs_path: OBS path prefix (e.g., "talk/m", "myhome/h")
            oid: Object ID (if not provided, uses temp upload)
            filename: File name
            params: Additional parameters
            add_headers: Additional headers

        Returns:
            Dict with objId and objHash
        """
        # Default extension based on type
        ext_map = {
            "image": "jpg",
            "gif": "gif",
            "video": "mp4",
            "audio": "m4a",
            "file": "bin",
        }

        default_ext = ext_map.get(obj_type, "bin")
        if not filename:
            filename = f"linejs.{default_ext}"

        # Build X-Obs-Params
        obs_params: dict[str, str] = {
            "type": "image" if obj_type == "gif" else obj_type,
            "ver": "2.0",
            "name": filename,
        }

        # Add type-specific params
        if obj_type in ("image", "gif"):
            obs_params["cat"] = "original"
        elif obj_type in ("audio", "video"):
            obs_params["duration"] = "1919"

        if params:
            obs_params.update(params)

        # Build URL
        if oid:
            url = f"https://{self.OBS_HOST}/r/{obs_path}/{oid}"
        else:
            url = f"https://{self.OBS_HOST}/r/{obs_path}"

        # Build headers
        headers: dict[str, str] = {
            "content-type": "application/octet-stream",
            "x-obs-params": b64encode(json.dumps(obs_params).encode()).decode(),
            "x-line-application": self.client.system_type,
            "x-line-access": self.client.auth_token or "",
        }

        if add_headers:
            headers.update(add_headers)

        # Make request
        http_client = await self.client.request.get_http_client()
        response = await http_client.post(
            url,
            content=data,
            headers=headers,
        )

        if response.status_code != 200 and response.status_code != 201:
            from ..client.exceptions import InternalError

            raise InternalError(
                "OBS_UPLOAD_FAILED",
                f"Status {response.status_code}: {response.text}",
                {
                    "status": response.status_code,
                    "body": response.text,
                },
            )

        return {
            "objId": response.headers.get("x-obs-oid", ""),
            "objHash": response.headers.get("x-obs-hash", ""),
        }

    async def upload_obj_talk(
        self,
        to: str,
        obj_type: ObjType,
        data: bytes,
        oid: str | None = None,
        filename: str | None = None,
    ) -> dict:
        """
        Upload media to talk service.

        Args:
            to: Recipient MID
            obj_type: Type of object
            data: File data
            oid: Optional object ID
            filename: Optional filename

        Returns:
            Dict with objId and objHash
        """
        params: dict[str, str] = {}

        if oid:
            params["oid"] = oid
        else:
            # Use reqseq mode
            seq = await self.client.get_reqseq()
            params["reqseq"] = str(seq)

        params["tomid"] = to
        params["type"] = "image" if obj_type == "gif" else obj_type

        return await self.upload_object(
            data=data,
            obj_type=obj_type,
            obs_path="talk/m",
            oid=oid,
            filename=filename,
            params=params,
        )

    async def upload_media_e2ee(
        self,
        to: str,
        data: bytes,
        obj_type: ObjType,
        filename: str | None = None,
    ) -> dict:
        """
        Upload media with E2EE encryption.

        Args:
            to: Recipient MID
            data: File data
            obj_type: Type of object
            filename: Optional filename

        Returns:
            Sent message object
        """
        obs_namespace, content_type = self.TYPE_MAP.get(obj_type, ("emf", 14))

        # Generate encryption key material
        key_material = get_random_bytes(32)
        nonce = get_random_bytes(16)

        # Encrypt file data
        aes_key = key_material[:16]
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce[:12])
        encrypted_data, tag = cipher.encrypt_and_digest(data)
        encrypted_blob = nonce + encrypted_data + tag

        # Upload encrypted data
        seq = await self.client.get_reqseq()
        temp_id = f"temp_{seq}"

        upload_result = await self.upload_object(
            data=encrypted_blob,
            obj_type=obj_type,
            obs_path=f"talk/{obs_namespace}",
            oid=temp_id,
            filename=filename,
            params={"tomid": to, "cat": "original"},
        )

        obj_id = upload_result["objId"]

        # Upload preview for images/videos
        if obj_type in ("image", "gif", "video"):
            await self._upload_preview(
                encrypted_blob[: min(len(encrypted_blob), 10240)],
                obs_namespace,
                obj_id,
                to,
            )

        # Build encrypted message metadata
        media_info = {
            "keyMaterial": b64encode(key_material).decode(),
            "fileName": filename or f"linejs.{obj_type}",
            "contentType": str(content_type),
            "fileSize": str(len(data)),
        }

        # Encrypt metadata using E2EE
        chunks = await self.client.e2ee.encrypt_e2ee_message(
            to=to,
            data=media_info,
            content_type=content_type,
        )

        # Send message with media
        content_metadata = {
            "SID": "",
            "OID": obj_id,
            "FILE_SIZE": str(len(data)),
            "e2eeVersion": "2",
        }

        if filename:
            content_metadata["FILE_NAME"] = filename

        return await self.client.talk.send_message(
            to=to,
            content_type=content_type,
            content_metadata=content_metadata,
            chunks=[b64encode(c).decode() for c in chunks],
        )

    async def _upload_preview(
        self,
        data: bytes,
        obs_namespace: str,
        obj_id: str,
        to: str,
    ) -> None:
        """Upload preview image for media."""
        try:
            await self.upload_object(
                data=data,
                obj_type="image",
                obs_path=f"talk/{obs_namespace}",
                oid=f"{obj_id}__ud-preview",
                params={"tomid": to, "cat": "preview"},
            )
        except Exception:
            # Preview upload failure is not critical
            pass

    async def download_object(
        self,
        obs_path: str,
        oid: str,
        add_headers: dict[str, str] | None = None,
    ) -> bytes:
        """
        Download a file from LINE's object storage.

        Args:
            obs_path: OBS path
            oid: Object ID
            add_headers: Additional headers

        Returns:
            File data as bytes
        """
        url = f"https://{self.OBS_HOST}/r/{obs_path}/{oid}"

        headers: dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "x-line-application": self.client.system_type,
            "x-line-access": self.client.auth_token or "",
        }

        if add_headers:
            headers.update(add_headers)

        http_client = await self.client.request.get_http_client()
        response = await http_client.get(url, headers=headers)

        if response.status_code != 200:
            from ..client.exceptions import InternalError

            raise InternalError(
                "OBS_DOWNLOAD_FAILED",
                f"Status {response.status_code}: {response.text}",
                {
                    "status": response.status_code,
                    "body": response.text,
                },
            )

        return response.content

    async def download_message_data(
        self,
        message_id: str,
        is_preview: bool = False,
        is_square: bool = False,
    ) -> tuple[bytes, dict]:
        """
        Download media from a message.

        Args:
            message_id: Message ID
            is_preview: Whether to download preview
            is_square: Whether this is a Square message

        Returns:
            Tuple of (file_data, metadata)
        """
        obs_path = "g2" if is_square else "talk"
        preview_suffix = "/preview" if is_preview else ""

        # Download file
        data = await self.download_object(
            obs_path=obs_path,
            oid=f"m/{message_id}{preview_suffix}",
        )

        # Get metadata
        metadata = await self.get_message_obs_metadata(message_id, is_square)

        return data, metadata

    async def get_message_obs_metadata(
        self,
        message_id: str,
        is_square: bool = False,
    ) -> dict:
        """
        Get OBS metadata for a message.

        Args:
            message_id: Message ID
            is_square: Whether this is a Square message

        Returns:
            Metadata dict
        """
        obs_path = "g2" if is_square else "talk"
        url = f"https://{self.OBS_HOST}/r/{obs_path}/m/{message_id}/object_info.obs"

        headers: dict[str, str] = {
            "accept": "application/json",
            "x-line-application": self.client.system_type,
            "x-line-access": self.client.auth_token or "",
        }

        http_client = await self.client.request.get_http_client()
        response = await http_client.get(url, headers=headers)

        if response.status_code != 200:
            return {}

        try:
            return response.json()
        except Exception:
            return {}

    async def download_media_e2ee(
        self,
        message: dict,
    ) -> tuple[bytes, str] | None:
        """
        Download and decrypt E2EE media.

        Args:
            message: Message dict containing chunks and metadata

        Returns:
            Tuple of (decrypted_data, filename) or None
        """
        chunks = message.get("chunks", [])
        content_metadata = message.get("contentMetadata", {})

        if not chunks:
            return None

        # Build X-Talk-Meta header
        message_data = self._build_message_thrift(message)
        talk_meta = b64encode(
            json.dumps({"message": b64encode(message_data).decode()}).encode()
        ).decode()

        # Determine obs path based on content type
        content_type = message.get("contentType", 0)
        if isinstance(content_type, str):
            type_map = {"IMAGE": 1, "VIDEO": 2, "AUDIO": 3, "FILE": 14}
            content_type = type_map.get(content_type, 0)

        namespace_map = {1: "emi", 2: "emv", 3: "ema", 14: "emf"}
        obs_namespace = namespace_map.get(content_type, "emi")

        oid = content_metadata.get("OID", "")

        # Download encrypted data
        encrypted_data = await self.download_object(
            obs_path=f"talk/{obs_namespace}",
            oid=oid,
            add_headers={"x-talk-meta": talk_meta},
        )

        # Decrypt message chunks to get key material
        decrypted_meta = await self.client.e2ee.decrypt_e2ee_message(message)
        meta_info = decrypted_meta.get("contentMetadata", {})

        key_material_b64 = meta_info.get("keyMaterial", "")
        if not key_material_b64:
            # Try to get from MEDIA_CONTENT_INFO
            media_info = meta_info.get("MEDIA_CONTENT_INFO", "")
            if media_info:
                try:
                    info = json.loads(media_info)
                    key_material_b64 = info.get("keyMaterial", "")
                except Exception:
                    pass

        if not key_material_b64:
            return None

        key_material = b64decode(key_material_b64)

        # Decrypt file data
        nonce = encrypted_data[:16]
        ciphertext = encrypted_data[16:-16]
        tag = encrypted_data[-16:]

        aes_key = key_material[:16]
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce[:12])
        decrypted_data = cipher.decrypt_and_verify(ciphertext, tag)

        filename = meta_info.get("fileName", content_metadata.get("FILE_NAME", "file"))

        return decrypted_data, filename

    def _build_message_thrift(self, message: dict) -> bytes:
        """Build thrift serialized message for X-Talk-Meta header."""
        # Simplified message struct for OBS
        message_data = []

        if "id" in message:
            message_data.append([11, 4, message["id"]])
        if "from" in message:
            message_data.append([11, 1, message["from"]])
        if "to" in message:
            message_data.append([11, 2, message["to"]])
        if "contentType" in message:
            ct = message["contentType"]
            if isinstance(ct, str):
                type_map = {"IMAGE": 1, "VIDEO": 2, "AUDIO": 3, "FILE": 14}
                ct = type_map.get(ct, 0)
            message_data.append([8, 3, ct])

        return write_thrift(message_data, "")

    async def upload_talk_image(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Upload and send an image.

        Args:
            to: Recipient MID
            data: Image data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        if e2ee:
            return await self.upload_media_e2ee(to, data, "image", filename)
        else:
            result = await self.upload_obj_talk(to, "image", data, filename=filename)
            return await self.client.talk.send_message(
                to=to,
                content_type=1,
                content_metadata={
                    "OID": result["objId"],
                    "FILE_SIZE": str(len(data)),
                },
            )

    async def upload_talk_video(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Upload and send a video.

        Args:
            to: Recipient MID
            data: Video data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        if e2ee:
            return await self.upload_media_e2ee(to, data, "video", filename)
        else:
            result = await self.upload_obj_talk(to, "video", data, filename=filename)
            return await self.client.talk.send_message(
                to=to,
                content_type=2,
                content_metadata={
                    "OID": result["objId"],
                    "FILE_SIZE": str(len(data)),
                },
            )

    async def upload_talk_audio(
        self,
        to: str,
        data: bytes,
        filename: str | None = None,
        e2ee: bool = False,
    ) -> dict:
        """
        Upload and send an audio file.

        Args:
            to: Recipient MID
            data: Audio data
            filename: Optional filename
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        if e2ee:
            return await self.upload_media_e2ee(to, data, "audio", filename)
        else:
            result = await self.upload_obj_talk(to, "audio", data, filename=filename)
            return await self.client.talk.send_message(
                to=to,
                content_type=3,
                content_metadata={
                    "OID": result["objId"],
                    "FILE_SIZE": str(len(data)),
                },
            )

    async def upload_talk_file(
        self,
        to: str,
        data: bytes,
        filename: str,
        e2ee: bool = False,
    ) -> dict:
        """
        Upload and send a file.

        Args:
            to: Recipient MID
            data: File data
            filename: Filename (required for files)
            e2ee: Use E2EE encryption

        Returns:
            Sent message object
        """
        if e2ee:
            return await self.upload_media_e2ee(to, data, "file", filename)
        else:
            result = await self.upload_obj_talk(to, "file", data, filename=filename)
            return await self.client.talk.send_message(
                to=to,
                content_type=14,
                content_metadata={
                    "OID": result["objId"],
                    "FILE_NAME": filename,
                    "FILE_SIZE": str(len(data)),
                },
            )
