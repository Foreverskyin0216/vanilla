"""MIME type to file extension mappings."""

MIME_TO_EXT: dict[str, str] = {
    # Images
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/tiff": "tiff",
    "image/x-icon": "ico",
    # Video
    "video/mp4": "mp4",
    "video/mpeg": "mpg",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/x-flv": "flv",
    "video/webm": "webm",
    "video/3gpp": "3gp",
    "video/x-matroska": "mkv",
    # Audio
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/x-wav": "wav",
    "audio/x-aiff": "aiff",
    "audio/midi": "midi",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/aac": "aac",
    "audio/webm": "weba",
    # Documents
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    # Archives
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed": "7z",
    "application/gzip": "gz",
    "application/x-tar": "tar",
    # Text
    "text/plain": "txt",
    "text/html": "html",
    "text/css": "css",
    "text/javascript": "js",
    "application/json": "json",
    "application/xml": "xml",
    # Other
    "application/octet-stream": "bin",
}

EXT_TO_MIME: dict[str, str] = {v: k for k, v in MIME_TO_EXT.items()}


def get_extension(mime_type: str) -> str:
    """Get file extension from MIME type."""
    return MIME_TO_EXT.get(mime_type, "bin")


def get_mime_type(extension: str) -> str:
    """Get MIME type from file extension."""
    ext = extension.lstrip(".")
    return EXT_TO_MIME.get(ext, "application/octet-stream")
