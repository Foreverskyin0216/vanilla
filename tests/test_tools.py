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
