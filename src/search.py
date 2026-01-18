"""Search functionality using Tavily API."""

import os
from dataclasses import dataclass
from typing import Literal

from tavily import AsyncTavilyClient

SearchTopic = Literal["general", "news"]


@dataclass
class SearchResultItem:
    """A single search result item."""

    title: str
    url: str
    content: str


@dataclass
class SearchResult:
    """Search results with optional answer."""

    answer: str | None
    results: list[SearchResultItem]


@dataclass
class ExtractResultItem:
    """A single URL extraction result."""

    url: str
    raw_content: str
    images: list[str] | None = None


@dataclass
class FailedExtractItem:
    """A failed URL extraction result with error details."""

    url: str
    error: str


@dataclass
class ExtractResult:
    """URL extraction results."""

    results: list[ExtractResultItem]
    failed_results: list[FailedExtractItem]


class Search:
    """Tavily search wrapper."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize the search client.

        Args:
            api_key: Tavily API key. If not provided, uses TAVILY_API_KEY env var.
        """
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            raise ValueError("Search setup failed. A Tavily API key is required.")
        self.client = AsyncTavilyClient(api_key=key)

    async def search(self, question: str, topic: SearchTopic = "general") -> SearchResult:
        """
        Perform a search query.

        Args:
            question: The search query.
            topic: Search topic - "general" or "news".

        Returns:
            SearchResult with answer and results.
        """
        response = await self.client.search(
            query=question,
            search_depth="advanced",
            max_results=6,
            topic=topic,
            include_answer=True,
        )

        results = [
            SearchResultItem(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            )
            for r in response.get("results", [])
        ]

        return SearchResult(
            answer=response.get("answer"),
            results=results,
        )

    async def extract(self, urls: str | list[str]) -> ExtractResult:
        """
        Extract content from one or more URLs.

        Args:
            urls: A single URL or list of URLs to extract content from.

        Returns:
            ExtractResult with extracted content and any failed URLs.
        """
        if isinstance(urls, str):
            urls = [urls]

        response = await self.client.extract(
            urls=urls,
            include_images=False,
            extract_depth="advanced",
            format="markdown",
        )

        results = [
            ExtractResultItem(
                url=r.get("url", ""),
                raw_content=r.get("raw_content", ""),
                images=r.get("images"),
            )
            for r in response.get("results", [])
        ]

        failed_results = [
            FailedExtractItem(
                url=r.get("url", ""),
                error=r.get("error", "Unknown error"),
            )
            for r in response.get("failed_results", [])
        ]

        return ExtractResult(
            results=results,
            failed_results=failed_results,
        )
