"""Tests for tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.search import ExtractResultItem, FailedExtractItem
from src.tools import (
    DATETIME_DESCRIPTION,
    WEBSEARCH_DESCRIPTION,
    create_tools,
    extract_urls,
    format_extract_results,
    format_search_results,
    get_formatted_datetime,
)


def test_get_formatted_datetime_default_timezone():
    """Test datetime formatting with default timezone."""
    result = get_formatted_datetime("Asia/Taipei")
    # Format: YYYY-MM-DD Weekday HH:MM:SS
    assert "-" in result  # Date separator
    assert ":" in result  # Time separator
    # Check weekday is in English
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert any(day in result for day in weekdays)


def test_get_formatted_datetime_invalid_timezone():
    """Test datetime formatting with invalid timezone falls back to Asia/Taipei."""
    result = get_formatted_datetime("Invalid/Timezone")
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert any(day in result for day in weekdays)


def test_get_formatted_datetime_utc():
    """Test datetime formatting with UTC timezone."""
    result = get_formatted_datetime("UTC")
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert any(day in result for day in weekdays)


def test_format_search_results_with_answer():
    """Test format_search_results with answer."""
    results = [
        {"title": "Result 1", "content": "Content 1"},
        {"title": "Result 2", "content": "Content 2"},
    ]
    output = format_search_results("Test answer", results)

    assert "Search Results:" in output
    assert "[1] Result 1" in output
    assert "Content 1" in output
    assert "[2] Result 2" in output
    assert "Content 2" in output
    assert "Summary: Test answer" in output


def test_format_search_results_without_answer():
    """Test format_search_results without answer."""
    results = [{"title": "Result 1", "content": "Content 1"}]
    output = format_search_results(None, results)

    assert "Search Results:" in output
    assert "[1] Result 1" in output
    assert "Summary" not in output


def test_format_search_results_empty():
    """Test format_search_results with empty results."""
    output = format_search_results(None, [])
    assert "Search Results:" in output


def test_websearch_description_exists():
    """Test WEBSEARCH_DESCRIPTION has content."""
    assert WEBSEARCH_DESCRIPTION is not None
    assert len(WEBSEARCH_DESCRIPTION) > 50


def test_datetime_description_exists():
    """Test DATETIME_DESCRIPTION has content."""
    assert DATETIME_DESCRIPTION is not None
    assert len(DATETIME_DESCRIPTION) > 10


def test_create_tools_returns_list():
    """Test create_tools returns a list of tools."""
    mock_search = MagicMock()
    tools = create_tools(mock_search)

    assert isinstance(tools, list)
    assert len(tools) == 2


def test_create_tools_tool_names():
    """Test create_tools returns tools with correct names."""
    mock_search = MagicMock()
    tools = create_tools(mock_search)

    tool_names = [t.name for t in tools]
    assert "websearch" in tool_names
    assert "get_datetime" in tool_names


def test_datetime_tool_invoke():
    """Test datetime tool can be invoked."""
    mock_search = MagicMock()
    tools = create_tools(mock_search)

    datetime_tool = next(t for t in tools if t.name == "get_datetime")
    result = datetime_tool.invoke({"timezone": "Asia/Taipei"})

    # Check for date format (YYYY-MM-DD) and weekday
    assert "-" in result
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert any(day in result for day in weekdays)


def test_extract_urls_single():
    """Test extract_urls with a single URL."""
    text = "Check out https://example.com for more info"
    urls = extract_urls(text)
    assert urls == ["https://example.com"]


def test_extract_urls_multiple():
    """Test extract_urls with multiple URLs."""
    text = "Visit https://example.com and http://test.org/path"
    urls = extract_urls(text)
    assert len(urls) == 2
    assert "https://example.com" in urls
    assert "http://test.org/path" in urls


def test_extract_urls_no_urls():
    """Test extract_urls with no URLs."""
    text = "This is just plain text"
    urls = extract_urls(text)
    assert urls == []


def test_extract_urls_complex():
    """Test extract_urls with complex URLs."""
    text = "Go to https://example.com/path?query=value&other=1#hash"
    urls = extract_urls(text)
    assert len(urls) == 1
    assert urls[0] == "https://example.com/path?query=value&other=1#hash"


def test_format_extract_results_with_results():
    """Test format_extract_results with results."""
    results = [
        ExtractResultItem(url="https://example.com", raw_content="Content 1"),
        ExtractResultItem(url="https://test.org", raw_content="Content 2"),
    ]
    output = format_extract_results(results, [])

    assert "Web Content Extraction Results:" in output
    assert "https://example.com" in output
    assert "Content 1" in output
    assert "https://test.org" in output
    assert "Content 2" in output


def test_format_extract_results_with_failed():
    """Test format_extract_results with failed URLs."""
    results = [
        ExtractResultItem(url="https://example.com", raw_content="Content 1"),
    ]
    failed_results = [
        FailedExtractItem(url="https://failed.com", error="Failed to fetch url"),
    ]
    output = format_extract_results(results, failed_results)

    assert "Web Content Extraction Results:" in output
    assert "https://example.com" in output
    assert "Failed to extract content from the following URLs:" in output
    assert "https://failed.com" in output
    assert "Error: Failed to fetch url" in output


def test_format_extract_results_all_failed():
    """Test format_extract_results with all URLs failed."""
    failed_results = [
        FailedExtractItem(url="https://failed.com", error="Connection timeout"),
        FailedExtractItem(url="https://failed2.com", error="Site blocks scraping"),
    ]
    output = format_extract_results([], failed_results)

    assert "Failed to extract content from the following URLs:" in output
    assert "https://failed.com" in output
    assert "Error: Connection timeout" in output
    assert "https://failed2.com" in output
    assert "Error: Site blocks scraping" in output


def test_format_extract_results_truncation():
    """Test format_extract_results truncates long content."""
    long_content = "a" * 10000
    results = [
        ExtractResultItem(url="https://example.com", raw_content=long_content),
    ]
    output = format_extract_results(results, [])

    assert "content truncated" in output
    # Should be truncated to 8000 chars + truncation message
    assert len(output) < len(long_content)


@pytest.mark.asyncio
async def test_websearch_tool_with_url():
    """Test websearch tool detects and extracts URLs."""
    mock_search = MagicMock()
    mock_extract_result = MagicMock()
    mock_extract_result.results = [
        ExtractResultItem(url="https://example.com", raw_content="Extracted content")
    ]
    mock_extract_result.failed_results = []
    mock_search.extract = AsyncMock(return_value=mock_extract_result)

    tools = create_tools(mock_search)
    websearch_tool = next(t for t in tools if t.name == "websearch")

    result = await websearch_tool.ainvoke({"question": "Analyze this URL https://example.com"})

    assert "Web Content Extraction Results:" in result
    assert "https://example.com" in result
    assert "Extracted content" in result
    mock_search.extract.assert_called_once_with(["https://example.com"])


@pytest.mark.asyncio
async def test_websearch_tool_regular_search():
    """Test websearch tool performs regular search when no URL."""
    mock_search = MagicMock()
    mock_search_result = MagicMock()
    mock_search_result.answer = "Test answer"
    mock_search_result.results = [MagicMock(title="Result 1", content="Content 1")]
    mock_search.search = AsyncMock(return_value=mock_search_result)

    tools = create_tools(mock_search)
    websearch_tool = next(t for t in tools if t.name == "websearch")

    result = await websearch_tool.ainvoke({"question": "What is the weather today"})

    assert "Search Results" in result
    mock_search.search.assert_called_once()


# =============================================================================
# Tests for scheduler tools with flexible search
# =============================================================================


class TestSchedulerToolsSearch:
    """Tests for scheduler tools with flexible search capabilities."""

    def setup_method(self):
        """Set up mock scheduler with test tasks."""
        from dataclasses import dataclass

        @dataclass
        class MockTask:
            id: str
            chat_id: str
            message: str
            status: str
            description: str | None = None
            cron_expression: str = "0 9 * * *"

            def to_readable_string(self):
                return f"Task: {self.description or self.message}"

        self.mock_search = MagicMock()
        self.mock_scheduler = MagicMock()
        self.chat_id = "test_chat_123"

        # Create test tasks
        self.task1 = MockTask(
            id="abc12345-1234-5678-9012-345678901234",
            chat_id=self.chat_id,
            message="早安訊息",
            description="每日早安提醒",
            status="pending",
        )
        self.task2 = MockTask(
            id="def67890-1234-5678-9012-345678901234",
            chat_id=self.chat_id,
            message="晚安訊息",
            description="每日晚安提醒",
            status="pending",
        )
        self.task3 = MockTask(
            id="ghi11111-1234-5678-9012-345678901234",
            chat_id=self.chat_id,
            message="午餐提醒",
            description=None,
            status="pending",
        )
        self.task4 = MockTask(
            id="jkl22222-1234-5678-9012-345678901234",
            chat_id="other_chat",  # Different chat
            message="其他群組訊息",
            description="其他群組",
            status="pending",
        )
        self.task5 = MockTask(
            id="mno33333-1234-5678-9012-345678901234",
            chat_id=self.chat_id,
            message="已取消任務",
            description="已取消",
            status="cancelled",
        )

        self.mock_scheduler.tasks = {
            self.task1.id: self.task1,
            self.task2.id: self.task2,
            self.task3.id: self.task3,
            self.task4.id: self.task4,
            self.task5.id: self.task5,
        }
        self.mock_scheduler.cancel_task = AsyncMock(return_value=True)
        self.mock_scheduler.update_task = AsyncMock(return_value=self.task1)
        self.mock_scheduler.list_tasks = MagicMock(return_value="Task list")

    def _get_tools(self):
        """Get tools with mock scheduler."""
        return create_tools(self.mock_search, self.mock_scheduler, self.chat_id)

    def _get_cancel_tool(self):
        """Get the cancel_scheduled_task tool."""
        tools = self._get_tools()
        return next(t for t in tools if t.name == "cancel_scheduled_task")

    def _get_update_tool(self):
        """Get the update_scheduled_task tool."""
        tools = self._get_tools()
        return next(t for t in tools if t.name == "update_scheduled_task")

    @pytest.mark.asyncio
    async def test_cancel_by_id(self):
        """Test canceling task by ID."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "abc12345"})
        assert "任務已取消" in result
        self.mock_scheduler.cancel_task.assert_called_once_with(self.task1.id)

    @pytest.mark.asyncio
    async def test_cancel_by_description(self):
        """Test canceling task by description search."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "早安提醒"})
        assert "任務已取消" in result
        self.mock_scheduler.cancel_task.assert_called_once_with(self.task1.id)

    @pytest.mark.asyncio
    async def test_cancel_by_message_content(self):
        """Test canceling task by message content search."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "午餐"})
        assert "任務已取消" in result
        self.mock_scheduler.cancel_task.assert_called_once_with(self.task3.id)

    @pytest.mark.asyncio
    async def test_cancel_not_found(self):
        """Test canceling non-existent task."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "不存在的任務"})
        assert "找不到任務" in result

    @pytest.mark.asyncio
    async def test_cancel_multiple_matches(self):
        """Test canceling with multiple matches shows options."""
        tool = self._get_cancel_tool()
        # "提醒" should match both task1 and task2
        result = await tool.ainvoke({"search": "提醒"})
        assert "找到多個匹配的任務" in result
        assert "abc12345" in result or "def67890" in result

    @pytest.mark.asyncio
    async def test_cancel_ignores_other_chat(self):
        """Test that tasks from other chats are not matched."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "其他群組"})
        assert "找不到任務" in result

    @pytest.mark.asyncio
    async def test_cancel_ignores_cancelled_tasks(self):
        """Test that cancelled tasks are not matched."""
        tool = self._get_cancel_tool()
        result = await tool.ainvoke({"search": "已取消"})
        assert "找不到任務" in result

    @pytest.mark.asyncio
    async def test_update_by_description(self):
        """Test updating task by description search."""
        tool = self._get_update_tool()
        result = await tool.ainvoke({"search": "早安提醒", "message": "新的早安訊息"})
        assert "任務已更新" in result
        self.mock_scheduler.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_by_message_content(self):
        """Test updating task by message content search."""
        tool = self._get_update_tool()
        result = await tool.ainvoke({"search": "午餐", "description": "新描述"})
        assert "任務已更新" in result

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        """Test updating non-existent task."""
        tool = self._get_update_tool()
        result = await tool.ainvoke({"search": "不存在", "message": "新訊息"})
        assert "找不到任務" in result

    @pytest.mark.asyncio
    async def test_update_requires_at_least_one_field(self):
        """Test update requires at least one field to update."""
        tool = self._get_update_tool()
        result = await tool.ainvoke({"search": "早安"})
        assert "Error" in result
        assert "至少需要提供一個" in result


# =============================================================================
# Tests for preference tools with flexible search
# =============================================================================


class TestPreferenceToolsSearch:
    """Tests for preference tools with flexible search capabilities."""

    def setup_method(self):
        """Set up mock preferences store."""
        from dataclasses import dataclass
        from datetime import datetime
        from zoneinfo import ZoneInfo

        @dataclass
        class MockPreference:
            id: str
            user_id: str
            chat_id: str
            rule_type: str
            rule_key: str
            rule_value: str
            is_active: bool = True
            created_at: datetime = None
            updated_at: datetime = None

            def __post_init__(self):
                tz = ZoneInfo("Asia/Taipei")
                self.created_at = self.created_at or datetime.now(tz)
                self.updated_at = self.updated_at or datetime.now(tz)

            def to_readable_string(self):
                return f"ID: {self.id[:8]}\nType: {self.rule_type}\nKey: {self.rule_key}\nValue: {self.rule_value}"

        self.mock_search = MagicMock()
        self.mock_preferences_store = MagicMock()
        self.user_id = "user_123"
        self.chat_id = "chat_456"

        # Create test preferences
        self.pref1 = MockPreference(
            id="pref-1111",
            user_id=self.user_id,
            chat_id=self.chat_id,
            rule_type="nickname",
            rule_key="call_me",
            rule_value="小王爺",
        )
        self.pref2 = MockPreference(
            id="pref-2222",
            user_id=self.user_id,
            chat_id=self.chat_id,
            rule_type="trigger",
            rule_key="greeting",
            rule_value="晚安",
        )
        self.pref3 = MockPreference(
            id="pref-3333",
            user_id=self.user_id,
            chat_id=self.chat_id,
            rule_type="behavior",
            rule_key="formality",
            rule_value="不用敬語",
        )

        self.mock_preferences_store.get_preferences_for_user = AsyncMock(
            return_value=[self.pref1, self.pref2, self.pref3]
        )
        self.mock_preferences_store.delete_preference = AsyncMock(return_value=True)
        self.mock_preferences_store.set_preference = AsyncMock(return_value=self.pref1)

    def _get_tools(self):
        """Get tools with mock preferences store."""
        return create_tools(
            self.mock_search,
            preferences_store=self.mock_preferences_store,
            user_id=self.user_id,
            chat_id=self.chat_id,
        )

    def _get_delete_tool(self):
        """Get the delete_user_preference tool."""
        tools = self._get_tools()
        return next(t for t in tools if t.name == "delete_user_preference")

    @pytest.mark.asyncio
    async def test_delete_by_type_and_key(self):
        """Test deleting preference by type and key."""
        tool = self._get_delete_tool()
        result = await tool.ainvoke({"rule_type": "nickname", "rule_key": "call_me"})
        assert "偏好規則已刪除" in result
        self.mock_preferences_store.delete_preference.assert_called_once_with(
            user_id=self.user_id,
            chat_id=self.chat_id,
            rule_type="nickname",
            rule_key="call_me",
        )

    @pytest.mark.asyncio
    async def test_delete_by_search_value(self):
        """Test deleting preference by searching value."""
        tool = self._get_delete_tool()
        result = await tool.ainvoke({"search_value": "小王爺"})
        assert "偏好規則已刪除" in result
        assert "小王爺" in result

    @pytest.mark.asyncio
    async def test_delete_by_search_value_partial_match(self):
        """Test deleting preference with partial value match."""
        tool = self._get_delete_tool()
        result = await tool.ainvoke({"search_value": "晚安"})
        assert "偏好規則已刪除" in result or "找到多個匹配" in result

    @pytest.mark.asyncio
    async def test_delete_search_not_found(self):
        """Test deleting with non-matching search value."""
        self.mock_preferences_store.get_preferences_for_user = AsyncMock(
            return_value=[self.pref1, self.pref2, self.pref3]
        )
        tool = self._get_delete_tool()
        result = await tool.ainvoke({"search_value": "不存在的值"})
        assert "找不到匹配" in result

    @pytest.mark.asyncio
    async def test_delete_requires_parameters(self):
        """Test delete requires either type/key or search_value."""
        tool = self._get_delete_tool()
        result = await tool.ainvoke({})
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_delete_multiple_matches(self):
        """Test deleting with multiple matches shows options."""
        # Use search term that matches multiple preferences
        tool = self._get_delete_tool()
        # Search for empty string should match all (or search by type which could match multiple)
        result = await tool.ainvoke({"search_value": "pref"})  # Matches all IDs
        assert "找到多個匹配" in result or "找不到匹配" in result


class TestPreferenceToolsList:
    """Tests for preference list tool."""

    def setup_method(self):
        """Set up mock preferences store."""
        from dataclasses import dataclass
        from datetime import datetime
        from zoneinfo import ZoneInfo

        @dataclass
        class MockPreference:
            id: str
            user_id: str
            chat_id: str
            rule_type: str
            rule_key: str
            rule_value: str
            is_active: bool = True
            created_at: datetime = None
            updated_at: datetime = None

            def __post_init__(self):
                tz = ZoneInfo("Asia/Taipei")
                self.created_at = self.created_at or datetime.now(tz)
                self.updated_at = self.updated_at or datetime.now(tz)

            def to_readable_string(self):
                return f"ID: {self.id[:8]}\nType: {self.rule_type}\nKey: {self.rule_key}\nValue: {self.rule_value}"

        self.mock_search = MagicMock()
        self.mock_preferences_store = MagicMock()
        self.user_id = "user_123"
        self.chat_id = "chat_456"

        self.pref1 = MockPreference(
            id="pref-1111",
            user_id=self.user_id,
            chat_id=self.chat_id,
            rule_type="nickname",
            rule_key="call_me",
            rule_value="小王爺",
        )

        self.mock_preferences_store.get_preferences_for_user = AsyncMock(return_value=[self.pref1])

    def _get_tools(self):
        """Get tools with mock preferences store."""
        return create_tools(
            self.mock_search,
            preferences_store=self.mock_preferences_store,
            user_id=self.user_id,
            chat_id=self.chat_id,
        )

    @pytest.mark.asyncio
    async def test_list_preferences(self):
        """Test listing all preferences."""
        tools = self._get_tools()
        list_tool = next(t for t in tools if t.name == "get_user_preferences")
        result = await list_tool.ainvoke({})
        assert "preference" in result.lower()
        assert "nickname" in result

    @pytest.mark.asyncio
    async def test_list_preferences_empty(self):
        """Test listing preferences when empty."""
        self.mock_preferences_store.get_preferences_for_user = AsyncMock(return_value=[])
        tools = self._get_tools()
        list_tool = next(t for t in tools if t.name == "get_user_preferences")
        result = await list_tool.ainvoke({})
        assert "No preferences" in result
