"""Tests for linepy/obs/mime.py."""

from src.linepy.obs.mime import (
    EXT_TO_MIME,
    MIME_TO_EXT,
    get_extension,
    get_mime_type,
)


class TestMimeToExt:
    """Tests for MIME_TO_EXT dictionary."""

    def test_image_jpeg(self):
        assert MIME_TO_EXT["image/jpeg"] == "jpg"

    def test_image_png(self):
        assert MIME_TO_EXT["image/png"] == "png"

    def test_image_gif(self):
        assert MIME_TO_EXT["image/gif"] == "gif"

    def test_video_mp4(self):
        assert MIME_TO_EXT["video/mp4"] == "mp4"

    def test_audio_mpeg(self):
        assert MIME_TO_EXT["audio/mpeg"] == "mp3"

    def test_audio_mp4(self):
        assert MIME_TO_EXT["audio/mp4"] == "m4a"

    def test_application_pdf(self):
        assert MIME_TO_EXT["application/pdf"] == "pdf"

    def test_application_zip(self):
        assert MIME_TO_EXT["application/zip"] == "zip"

    def test_text_plain(self):
        assert MIME_TO_EXT["text/plain"] == "txt"

    def test_application_json(self):
        assert MIME_TO_EXT["application/json"] == "json"

    def test_application_octet_stream(self):
        assert MIME_TO_EXT["application/octet-stream"] == "bin"


class TestExtToMime:
    """Tests for EXT_TO_MIME dictionary."""

    def test_jpg(self):
        assert EXT_TO_MIME["jpg"] == "image/jpeg"

    def test_png(self):
        assert EXT_TO_MIME["png"] == "image/png"

    def test_mp4(self):
        assert EXT_TO_MIME["mp4"] == "video/mp4"

    def test_mp3(self):
        assert EXT_TO_MIME["mp3"] == "audio/mpeg"

    def test_pdf(self):
        assert EXT_TO_MIME["pdf"] == "application/pdf"

    def test_is_reverse_of_mime_to_ext(self):
        for mime, ext in MIME_TO_EXT.items():
            assert EXT_TO_MIME[ext] == mime


class TestGetExtension:
    """Tests for get_extension function."""

    def test_known_mime_types(self):
        assert get_extension("image/jpeg") == "jpg"
        assert get_extension("image/png") == "png"
        assert get_extension("video/mp4") == "mp4"
        assert get_extension("audio/mpeg") == "mp3"
        assert get_extension("application/pdf") == "pdf"

    def test_unknown_mime_type_returns_bin(self):
        assert get_extension("application/unknown") == "bin"
        assert get_extension("foo/bar") == "bin"
        assert get_extension("") == "bin"


class TestGetMimeType:
    """Tests for get_mime_type function."""

    def test_known_extensions(self):
        assert get_mime_type("jpg") == "image/jpeg"
        assert get_mime_type("png") == "image/png"
        assert get_mime_type("mp4") == "video/mp4"
        assert get_mime_type("mp3") == "audio/mpeg"
        assert get_mime_type("pdf") == "application/pdf"

    def test_extension_with_dot(self):
        assert get_mime_type(".jpg") == "image/jpeg"
        assert get_mime_type(".png") == "image/png"
        assert get_mime_type(".pdf") == "application/pdf"

    def test_unknown_extension_returns_octet_stream(self):
        assert get_mime_type("unknown") == "application/octet-stream"
        assert get_mime_type("xyz") == "application/octet-stream"
        assert get_mime_type("") == "application/octet-stream"


class TestMimeTypeCompleteness:
    """Tests to ensure MIME type mappings are complete."""

    def test_has_common_image_types(self):
        assert "image/jpeg" in MIME_TO_EXT
        assert "image/png" in MIME_TO_EXT
        assert "image/gif" in MIME_TO_EXT
        assert "image/webp" in MIME_TO_EXT

    def test_has_common_video_types(self):
        assert "video/mp4" in MIME_TO_EXT
        assert "video/webm" in MIME_TO_EXT
        assert "video/quicktime" in MIME_TO_EXT

    def test_has_common_audio_types(self):
        assert "audio/mpeg" in MIME_TO_EXT
        assert "audio/mp4" in MIME_TO_EXT
        assert "audio/ogg" in MIME_TO_EXT
        assert "audio/flac" in MIME_TO_EXT

    def test_has_common_document_types(self):
        assert "application/pdf" in MIME_TO_EXT
        assert "application/msword" in MIME_TO_EXT
        assert "application/zip" in MIME_TO_EXT

    def test_has_text_types(self):
        assert "text/plain" in MIME_TO_EXT
        assert "text/html" in MIME_TO_EXT
        assert "text/css" in MIME_TO_EXT
        assert "application/json" in MIME_TO_EXT
