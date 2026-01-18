"""Tests for linepy/client/exceptions.py."""

import pytest

from src.linepy.client.exceptions import (
    AuthException,
    ChannelException,
    InternalError,
    LineError,
    LoginError,
    SquareException,
    TalkException,
    TimeoutError,
)


class TestLineError:
    """Tests for LineError base exception."""

    def test_init_with_message(self):
        error = LineError("Test error")
        assert error.message == "Test error"
        assert error.data == {}

    def test_init_with_message_and_data(self):
        error = LineError("Test error", {"code": 123})
        assert error.message == "Test error"
        assert error.data == {"code": 123}

    def test_str_without_data(self):
        error = LineError("Test error")
        assert str(error) == "Test error"

    def test_str_with_data(self):
        error = LineError("Test error", {"code": 123})
        assert str(error) == "Test error: {'code': 123}"

    def test_is_exception_subclass(self):
        error = LineError("Test")
        assert isinstance(error, Exception)


class TestInternalError:
    """Tests for InternalError exception."""

    def test_init(self):
        error = InternalError("E001", "Internal error occurred")
        assert error.code == "E001"
        assert error.message == "Internal error occurred"
        assert error.data == {"code": "E001"}

    def test_init_with_data(self):
        error = InternalError("E001", "Error", {"extra": "info"})
        assert error.code == "E001"
        assert error.data == {"extra": "info", "code": "E001"}

    def test_is_line_error_subclass(self):
        error = InternalError("E001", "Error")
        assert isinstance(error, LineError)


class TestTalkException:
    """Tests for TalkException."""

    def test_init(self):
        error = TalkException("Talk error")
        assert error.message == "Talk error"

    def test_is_line_error_subclass(self):
        error = TalkException("Error")
        assert isinstance(error, LineError)


class TestSquareException:
    """Tests for SquareException."""

    def test_init(self):
        error = SquareException("Square error")
        assert error.message == "Square error"

    def test_is_line_error_subclass(self):
        error = SquareException("Error")
        assert isinstance(error, LineError)


class TestChannelException:
    """Tests for ChannelException."""

    def test_init(self):
        error = ChannelException("Channel error")
        assert error.message == "Channel error"

    def test_is_line_error_subclass(self):
        error = ChannelException("Error")
        assert isinstance(error, LineError)


class TestAuthException:
    """Tests for AuthException."""

    def test_init(self):
        error = AuthException("Auth error")
        assert error.message == "Auth error"

    def test_is_line_error_subclass(self):
        error = AuthException("Error")
        assert isinstance(error, LineError)


class TestLoginError:
    """Tests for LoginError."""

    def test_init(self):
        error = LoginError("Login failed")
        assert error.message == "Login failed"

    def test_is_line_error_subclass(self):
        error = LoginError("Error")
        assert isinstance(error, LineError)


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_init(self):
        error = TimeoutError("Request timed out")
        assert error.message == "Request timed out"

    def test_is_line_error_subclass(self):
        error = TimeoutError("Error")
        assert isinstance(error, LineError)


class TestExceptionRaising:
    """Tests for raising exceptions."""

    def test_raise_line_error(self):
        with pytest.raises(LineError) as exc_info:
            raise LineError("Test error")
        assert str(exc_info.value) == "Test error"

    def test_raise_internal_error(self):
        with pytest.raises(InternalError) as exc_info:
            raise InternalError("E001", "Internal error")
        assert exc_info.value.code == "E001"

    def test_catch_as_base_exception(self):
        try:
            raise TalkException("Talk error")
        except LineError as e:
            assert e.message == "Talk error"
        else:
            pytest.fail("Should have raised TalkException")
