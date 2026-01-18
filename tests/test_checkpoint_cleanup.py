"""Tests for checkpoint cleanup module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.checkpoint_cleanup import cleanup_old_checkpoints, get_checkpoint_stats


class TestCleanupOldCheckpoints:
    """Tests for cleanup_old_checkpoints function."""

    @pytest.mark.asyncio
    async def test_cleanup_no_old_checkpoints(self):
        """Test cleanup when there are no old checkpoints."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])  # No old threads

        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_cursor), __aexit__=AsyncMock()
            )
        )
        mock_conn.commit = AsyncMock()

        with patch(
            "psycopg.AsyncConnection.connect",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            ),
        ):
            results = await cleanup_old_checkpoints("postgresql://test", retention_days=30)

        assert results["threads_cleaned"] == 0
        assert results["checkpoints_deleted"] == 0
        assert results["writes_deleted"] == 0
        assert results["blobs_deleted"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_old_checkpoints(self):
        """Test cleanup when there are old checkpoints to remove."""
        mock_cursor = AsyncMock()
        # Return old threads
        mock_cursor.fetchall = AsyncMock(return_value=[("thread1",), ("thread2",)])
        mock_cursor.rowcount = 5

        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_cursor), __aexit__=AsyncMock()
            )
        )
        mock_conn.commit = AsyncMock()

        with patch(
            "psycopg.AsyncConnection.connect",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            ),
        ):
            results = await cleanup_old_checkpoints("postgresql://test", retention_days=30)

        assert results["threads_cleaned"] == 2
        # rowcount is 5 for each delete operation
        assert results["checkpoints_deleted"] == 5
        assert results["writes_deleted"] == 5

    @pytest.mark.asyncio
    async def test_cleanup_handles_connection_error(self):
        """Test cleanup raises error on connection failure."""
        with patch("psycopg.AsyncConnection.connect", side_effect=Exception("Connection failed")):
            with pytest.raises(Exception) as exc_info:
                await cleanup_old_checkpoints("postgresql://invalid", retention_days=30)
            assert "Connection failed" in str(exc_info.value)


class TestGetCheckpointStats:
    """Tests for get_checkpoint_stats function."""

    @pytest.mark.asyncio
    async def test_get_stats_empty_database(self):
        """Test getting stats from empty database."""
        mock_cursor = AsyncMock()
        # First query: count threads
        # Second query: count checkpoints
        # Third query: min/max created_at
        mock_cursor.fetchone = AsyncMock(side_effect=[(0,), (0,), (None, None)])

        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_cursor), __aexit__=AsyncMock()
            )
        )

        with patch(
            "psycopg.AsyncConnection.connect",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            ),
        ):
            stats = await get_checkpoint_stats("postgresql://test")

        assert stats["total_threads"] == 0
        assert stats["total_checkpoints"] == 0
        assert stats["oldest_checkpoint_age_days"] is None
        assert stats["newest_checkpoint_age_days"] is None

    @pytest.mark.asyncio
    async def test_get_stats_with_checkpoints(self):
        """Test getting stats with existing checkpoints."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        one_day_ago_ms = now_ms - (24 * 60 * 60 * 1000)

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            side_effect=[
                (5,),  # 5 threads
                (100,),  # 100 checkpoints
                (one_day_ago_ms, now_ms),  # min/max created_at
            ]
        )

        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_cursor), __aexit__=AsyncMock()
            )
        )

        with patch(
            "psycopg.AsyncConnection.connect",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            ),
        ):
            stats = await get_checkpoint_stats("postgresql://test")

        assert stats["total_threads"] == 5
        assert stats["total_checkpoints"] == 100
        # Oldest should be about 1 day old
        assert stats["oldest_checkpoint_age_days"] is not None
        assert 0.9 < stats["oldest_checkpoint_age_days"] < 1.1
        # Newest should be about 0 days old
        assert stats["newest_checkpoint_age_days"] is not None
        assert stats["newest_checkpoint_age_days"] < 0.1

    @pytest.mark.asyncio
    async def test_get_stats_handles_error(self):
        """Test get_stats handles connection errors gracefully."""
        with patch("psycopg.AsyncConnection.connect", side_effect=Exception("Connection failed")):
            stats = await get_checkpoint_stats("postgresql://invalid")

        # Should return default stats on error
        assert stats["total_threads"] == 0
        assert stats["total_checkpoints"] == 0
