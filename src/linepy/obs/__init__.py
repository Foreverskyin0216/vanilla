"""Object storage service for media upload/download."""

from .mime import MIME_TO_EXT
from .obs import OBS

__all__ = ["OBS", "MIME_TO_EXT"]
