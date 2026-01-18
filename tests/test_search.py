"""Tests for search module."""

import pytest

from src.search import (
    ExtractResult,
    ExtractResultItem,
    FailedExtractItem,
    Search,
    SearchResult,
    SearchResultItem,
)


def test_search_result_item():
    """Test SearchResultItem dataclass."""
    item = SearchResultItem(
        title="Test Title",
        url="https://example.com",
        content="Test content",
    )
    assert item.title == "Test Title"
    assert item.url == "https://example.com"
    assert item.content == "Test content"


def test_search_result():
    """Test SearchResult dataclass."""
    result = SearchResult(
        answer="Test answer",
        results=[
            SearchResultItem(title="T1", url="u1", content="c1"),
            SearchResultItem(title="T2", url="u2", content="c2"),
        ],
    )
    assert result.answer == "Test answer"
    assert len(result.results) == 2


def test_search_init_without_api_key():
    """Test Search initialization without API key raises error."""
    import os

    # Temporarily remove the env var if it exists
    original = os.environ.pop("TAVILY_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="Tavily API key is required"):
            Search()
    finally:
        if original:
            os.environ["TAVILY_API_KEY"] = original


def test_extract_result_item():
    """Test ExtractResultItem dataclass."""
    item = ExtractResultItem(
        url="https://example.com",
        raw_content="Test content",
        images=["https://example.com/image.png"],
    )
    assert item.url == "https://example.com"
    assert item.raw_content == "Test content"
    assert item.images == ["https://example.com/image.png"]


def test_extract_result_item_default_images():
    """Test ExtractResultItem dataclass with default images."""
    item = ExtractResultItem(
        url="https://example.com",
        raw_content="Test content",
    )
    assert item.url == "https://example.com"
    assert item.raw_content == "Test content"
    assert item.images is None


def test_extract_result():
    """Test ExtractResult dataclass."""
    result = ExtractResult(
        results=[
            ExtractResultItem(url="https://example.com", raw_content="Content 1"),
            ExtractResultItem(url="https://example2.com", raw_content="Content 2"),
        ],
        failed_results=[
            FailedExtractItem(url="https://failed.com", error="Failed to fetch url"),
        ],
    )
    assert len(result.results) == 2
    assert result.results[0].url == "https://example.com"
    assert len(result.failed_results) == 1
    assert result.failed_results[0].url == "https://failed.com"
    assert result.failed_results[0].error == "Failed to fetch url"


def test_extract_result_empty():
    """Test ExtractResult dataclass with empty results."""
    result = ExtractResult(
        results=[],
        failed_results=[],
    )
    assert len(result.results) == 0
    assert len(result.failed_results) == 0


def test_failed_extract_item():
    """Test FailedExtractItem dataclass."""
    item = FailedExtractItem(
        url="https://failed.com",
        error="Site blocked scraping",
    )
    assert item.url == "https://failed.com"
    assert item.error == "Site blocked scraping"
