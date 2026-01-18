"""Tests for user preferences module."""

import pytest

from src.preferences import (
    UserPreference,
    UserPreferencesStore,
    format_preferences_for_prompt,
)


class TestUserPreference:
    """Tests for UserPreference dataclass."""

    def test_preference_creation(self):
        """Test basic preference creation with required chat_id."""
        pref = UserPreference(
            id="test-id",
            user_id="user123",
            chat_id="chat456",
            rule_type="nickname",
            rule_key="call_me",
            rule_value="小王爺",
        )
        assert pref.id == "test-id"
        assert pref.user_id == "user123"
        assert pref.chat_id == "chat456"
        assert pref.rule_type == "nickname"
        assert pref.rule_key == "call_me"
        assert pref.rule_value == "小王爺"
        assert pref.is_active is True

    def test_preference_with_different_types(self):
        """Test preference creation with different rule types."""
        pref = UserPreference(
            id="test-id",
            user_id="user123",
            chat_id="chat456",
            rule_type="trigger",
            rule_key="greeting",
            rule_value="晚安",
        )
        assert pref.rule_type == "trigger"
        assert pref.rule_key == "greeting"
        assert pref.rule_value == "晚安"

    def test_to_readable_string(self):
        """Test readable string output."""
        pref = UserPreference(
            id="12345678-abcd-efgh",
            user_id="user123",
            chat_id="chat456",
            rule_type="nickname",
            rule_key="call_me",
            rule_value="小王爺",
        )
        readable = pref.to_readable_string()
        assert "ID: 12345678" in readable
        assert "Type: nickname" in readable
        assert "Key: call_me" in readable
        assert "Value: 小王爺" in readable
        assert "Active: Yes" in readable
        # No more "Scope" field since all are chat-specific now
        assert "Scope" not in readable

    def test_to_readable_string_inactive(self):
        """Test readable string for inactive preference."""
        pref = UserPreference(
            id="12345678-abcd-efgh",
            user_id="user123",
            chat_id="chat456",
            rule_type="nickname",
            rule_key="call_me",
            rule_value="小王爺",
            is_active=False,
        )
        readable = pref.to_readable_string()
        assert "Active: No" in readable


class TestUserPreferencesStore:
    """Tests for UserPreferencesStore class (without database)."""

    def test_store_init(self):
        """Test store initialization without PostgreSQL."""
        store = UserPreferencesStore()
        assert store._postgres_url is None

    def test_store_init_with_url(self):
        """Test store initialization with PostgreSQL URL."""
        store = UserPreferencesStore(postgres_url="postgresql://test:test@localhost/test")
        assert store._postgres_url == "postgresql://test:test@localhost/test"

    @pytest.mark.asyncio
    async def test_get_preference_no_db(self):
        """Test get_preference returns None without database."""
        store = UserPreferencesStore()
        result = await store.get_preference("user1", "chat1", "nickname", "call_me")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_preferences_for_user_no_db(self):
        """Test get_preferences_for_user returns empty list without database."""
        store = UserPreferencesStore()
        result = await store.get_preferences_for_user("user1", "chat1")
        assert result == []

    @pytest.mark.asyncio
    async def test_delete_preference_no_db(self):
        """Test delete_preference returns False without database."""
        store = UserPreferencesStore()
        result = await store.delete_preference("user1", "chat1", "nickname", "call_me")
        assert result is False


class TestFormatPreferencesForPrompt:
    """Tests for format_preferences_for_prompt function."""

    def test_empty_preferences(self):
        """Test formatting empty preferences."""
        result = format_preferences_for_prompt([])
        assert result == ""

    def test_nickname_preference(self):
        """Test formatting nickname preference."""
        prefs = [
            UserPreference(
                id="test-id",
                user_id="user1",
                chat_id="chat1",
                rule_type="nickname",
                rule_key="call_me",
                rule_value="小王爺",
            )
        ]
        result = format_preferences_for_prompt(prefs)
        assert "此用戶有以下個人偏好規則，請務必遵守" in result
        assert "請稱呼此用戶為「小王爺」" in result

    def test_trigger_preference(self):
        """Test formatting trigger preference."""
        prefs = [
            UserPreference(
                id="test-id",
                user_id="user1",
                chat_id="chat1",
                rule_type="trigger",
                rule_key="greeting",
                rule_value="晚安",
            )
        ]
        result = format_preferences_for_prompt(prefs)
        assert "觸發規則 (greeting): 晚安" in result

    def test_behavior_preference(self):
        """Test formatting behavior preference."""
        prefs = [
            UserPreference(
                id="test-id",
                user_id="user1",
                chat_id="chat1",
                rule_type="behavior",
                rule_key="no_honorifics",
                rule_value="true",
            )
        ]
        result = format_preferences_for_prompt(prefs)
        assert "行為規則 (no_honorifics): true" in result

    def test_multiple_preferences(self):
        """Test formatting multiple preferences."""
        prefs = [
            UserPreference(
                id="test-id-1",
                user_id="user1",
                chat_id="chat1",
                rule_type="nickname",
                rule_key="call_me",
                rule_value="小王爺",
            ),
            UserPreference(
                id="test-id-2",
                user_id="user1",
                chat_id="chat1",
                rule_type="trigger",
                rule_key="greeting",
                rule_value="晚安",
            ),
        ]
        result = format_preferences_for_prompt(prefs)
        assert "請稱呼此用戶為「小王爺」" in result
        assert "觸發規則 (greeting): 晚安" in result

    def test_custom_preference(self):
        """Test formatting custom preference."""
        prefs = [
            UserPreference(
                id="test-id",
                user_id="user1",
                chat_id="chat1",
                rule_type="custom",
                rule_key="special_rule",
                rule_value="some value",
            )
        ]
        result = format_preferences_for_prompt(prefs)
        assert "custom/special_rule: some value" in result

    def test_other_nickname_key(self):
        """Test formatting nickname with non-call_me key."""
        prefs = [
            UserPreference(
                id="test-id",
                user_id="user1",
                chat_id="chat1",
                rule_type="nickname",
                rule_key="other_key",
                rule_value="王子",
            )
        ]
        result = format_preferences_for_prompt(prefs)
        assert "暱稱規則 (other_key): 王子" in result
