"""User preferences module for persistent user-specific rules and settings."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import psycopg

from src.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEZONE = "Asia/Taipei"

# Rule types for user preferences
RuleType = Literal["nickname", "trigger", "behavior", "custom"]


@dataclass
class UserPreference:
    """A user preference rule.

    Attributes:
        id: Unique preference ID.
        user_id: LINE user ID.
        chat_id: Chat ID where this rule applies (chat-specific, no global rules).
        rule_type: Type of rule (nickname, trigger, behavior, custom).
        rule_key: Key identifying the rule (e.g., 'call_me', 'greeting').
        rule_value: The rule value (e.g., '小王爺', '晚安').
        is_active: Whether the rule is active.
        created_at: When the rule was created.
        updated_at: When the rule was last updated.
    """

    id: str
    user_id: str
    chat_id: str
    rule_type: str
    rule_key: str
    rule_value: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo(DEFAULT_TIMEZONE)))
    updated_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo(DEFAULT_TIMEZONE)))

    def to_readable_string(self) -> str:
        """Convert preference to a human-readable string."""
        return (
            f"ID: {self.id[:8]}\n"
            f"Type: {self.rule_type}\n"
            f"Key: {self.rule_key}\n"
            f"Value: {self.rule_value}\n"
            f"Active: {'Yes' if self.is_active else 'No'}"
        )


class UserPreferencesStore:
    """
    Store for managing user preferences with PostgreSQL persistence.

    Handles creation, retrieval, update, and deletion of user-specific rules.
    """

    def __init__(self, postgres_url: str | None = None):
        """
        Initialize the preferences store.

        Args:
            postgres_url: PostgreSQL connection string for persistence.
        """
        self._postgres_url = postgres_url

    async def setup(self) -> None:
        """Set up the preferences database table."""
        if not self._postgres_url:
            await logger.awarning("No PostgreSQL URL provided, preferences will not be persisted")
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_preferences (
                            id VARCHAR(36) PRIMARY KEY,
                            user_id VARCHAR(255) NOT NULL,
                            chat_id VARCHAR(255),
                            rule_type VARCHAR(50) NOT NULL,
                            rule_key VARCHAR(255) NOT NULL,
                            rule_value TEXT NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE(user_id, chat_id, rule_type, rule_key)
                        )
                    """)
                    # Create indexes for efficient querying
                    await cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id
                        ON user_preferences(user_id)
                    """)
                    await cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_user_preferences_user_chat
                        ON user_preferences(user_id, chat_id)
                    """)
                    await conn.commit()
            await logger.ainfo("User preferences database table set up successfully")
        except Exception as e:
            await logger.aerror(f"Failed to set up preferences database: {e}")
            raise

    async def set_preference(
        self,
        user_id: str,
        chat_id: str,
        rule_type: str,
        rule_key: str,
        rule_value: str,
    ) -> UserPreference:
        """
        Set or update a user preference (chat-specific).

        If a preference with the same user_id, chat_id, rule_type, and rule_key exists,
        it will be updated. Otherwise, a new preference will be created.

        Args:
            user_id: LINE user ID.
            chat_id: Chat ID where this rule applies.
            rule_type: Type of rule (nickname, trigger, behavior, custom).
            rule_key: Key identifying the rule.
            rule_value: The rule value.

        Returns:
            The created or updated preference.
        """
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        now = datetime.now(tz)

        # Check if preference exists
        existing = await self.get_preference(user_id, rule_type, rule_key, chat_id)

        if existing:
            # Update existing preference
            existing.rule_value = rule_value
            existing.is_active = True
            existing.updated_at = now
            await self._update_preference(existing)
            await logger.ainfo(f"Updated preference for user {user_id[:8]}: {rule_type}/{rule_key}")
            return existing
        else:
            # Create new preference
            pref_id = str(uuid.uuid4())
            pref = UserPreference(
                id=pref_id,
                user_id=user_id,
                chat_id=chat_id,
                rule_type=rule_type,
                rule_key=rule_key,
                rule_value=rule_value,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            await self._save_preference(pref)
            await logger.ainfo(f"Created preference for user {user_id[:8]}: {rule_type}/{rule_key}")
            return pref

    async def get_preference(
        self,
        user_id: str,
        chat_id: str,
        rule_type: str,
        rule_key: str,
    ) -> UserPreference | None:
        """
        Get a specific preference (chat-specific).

        Args:
            user_id: LINE user ID.
            chat_id: Chat ID where this rule applies.
            rule_type: Type of rule.
            rule_key: Key identifying the rule.

        Returns:
            The preference if found, None otherwise.
        """
        if not self._postgres_url:
            return None

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, user_id, chat_id, rule_type, rule_key, rule_value,
                               is_active, created_at, updated_at
                        FROM user_preferences
                        WHERE user_id = %s AND chat_id = %s AND rule_type = %s AND rule_key = %s
                        """,
                        (user_id, chat_id, rule_type, rule_key),
                    )
                    row = await cur.fetchone()
                    if row:
                        return UserPreference(
                            id=row[0],
                            user_id=row[1],
                            chat_id=row[2],
                            rule_type=row[3],
                            rule_key=row[4],
                            rule_value=row[5],
                            is_active=row[6],
                            created_at=row[7],
                            updated_at=row[8],
                        )
        except Exception as e:
            await logger.aerror(f"Failed to get preference: {e}")
        return None

    async def get_preferences_for_user(
        self,
        user_id: str,
        chat_id: str,
        active_only: bool = True,
    ) -> list[UserPreference]:
        """
        Get all preferences for a user in a specific chat.

        Args:
            user_id: LINE user ID.
            chat_id: Chat ID to get preferences for.
            active_only: Whether to only return active preferences.

        Returns:
            List of preferences.
        """
        if not self._postgres_url:
            return []

        preferences = []
        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    conditions = ["user_id = %s", "chat_id = %s"]
                    params: list = [user_id, chat_id]

                    if active_only:
                        conditions.append("is_active = TRUE")

                    query = f"""
                        SELECT id, user_id, chat_id, rule_type, rule_key, rule_value,
                               is_active, created_at, updated_at
                        FROM user_preferences
                        WHERE {" AND ".join(conditions)}
                        ORDER BY rule_type, rule_key
                    """
                    await cur.execute(query, params)
                    rows = await cur.fetchall()

                    for row in rows:
                        preferences.append(
                            UserPreference(
                                id=row[0],
                                user_id=row[1],
                                chat_id=row[2],
                                rule_type=row[3],
                                rule_key=row[4],
                                rule_value=row[5],
                                is_active=row[6],
                                created_at=row[7],
                                updated_at=row[8],
                            )
                        )
        except Exception as e:
            await logger.aerror(f"Failed to get preferences for user: {e}")
        return preferences

    async def delete_preference(
        self,
        user_id: str,
        chat_id: str,
        rule_type: str,
        rule_key: str,
    ) -> bool:
        """
        Delete a preference (soft delete by setting is_active = False).

        Args:
            user_id: LINE user ID.
            chat_id: Chat ID where this rule applies.
            rule_type: Type of rule.
            rule_key: Key identifying the rule.

        Returns:
            True if deleted, False if not found.
        """
        if not self._postgres_url:
            return False

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE user_preferences
                        SET is_active = FALSE, updated_at = NOW()
                        WHERE user_id = %s AND chat_id = %s AND rule_type = %s AND rule_key = %s
                        """,
                        (user_id, chat_id, rule_type, rule_key),
                    )
                    await conn.commit()
                    deleted = cur.rowcount > 0
                    if deleted:
                        await logger.ainfo(
                            f"Deleted preference for user {user_id[:8]}: {rule_type}/{rule_key}"
                        )
                    return deleted
        except Exception as e:
            await logger.aerror(f"Failed to delete preference: {e}")
        return False

    async def _save_preference(self, pref: UserPreference) -> None:
        """Save a new preference to the database."""
        if not self._postgres_url:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO user_preferences
                            (id, user_id, chat_id, rule_type, rule_key, rule_value,
                             is_active, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            pref.id,
                            pref.user_id,
                            pref.chat_id,
                            pref.rule_type,
                            pref.rule_key,
                            pref.rule_value,
                            pref.is_active,
                            pref.created_at,
                            pref.updated_at,
                        ),
                    )
                    await conn.commit()
        except Exception as e:
            await logger.aerror(f"Failed to save preference {pref.id}: {e}")

    async def _update_preference(self, pref: UserPreference) -> None:
        """Update an existing preference in the database."""
        if not self._postgres_url:
            return

        try:
            async with await psycopg.AsyncConnection.connect(self._postgres_url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE user_preferences
                        SET rule_value = %s, is_active = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (pref.rule_value, pref.is_active, pref.updated_at, pref.id),
                    )
                    await conn.commit()
        except Exception as e:
            await logger.aerror(f"Failed to update preference {pref.id}: {e}")


def format_preferences_for_prompt(preferences: list[UserPreference]) -> str:
    """
    Format user preferences into a string for injection into the system prompt.

    Args:
        preferences: List of user preferences.

    Returns:
        Formatted string describing the preferences.
    """
    if not preferences:
        return ""

    lines = ["此用戶有以下個人偏好規則，請務必遵守："]

    for pref in preferences:
        if pref.rule_type == "nickname":
            if pref.rule_key == "call_me":
                lines.append(f"  - 請稱呼此用戶為「{pref.rule_value}」")
            else:
                lines.append(f"  - 暱稱規則 ({pref.rule_key}): {pref.rule_value}")
        elif pref.rule_type == "trigger":
            lines.append(f"  - 觸發規則 ({pref.rule_key}): {pref.rule_value}")
        elif pref.rule_type == "behavior":
            lines.append(f"  - 行為規則 ({pref.rule_key}): {pref.rule_value}")
        else:
            lines.append(f"  - {pref.rule_type}/{pref.rule_key}: {pref.rule_value}")

    return "\n".join(lines)
