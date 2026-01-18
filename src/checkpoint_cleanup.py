"""Checkpoint cleanup utilities for managing LangGraph checkpoint retention."""

import asyncio
from datetime import datetime, timedelta, timezone

import psycopg

from src.logging import get_logger

logger = get_logger(__name__)


async def cleanup_old_checkpoints(
    postgres_url: str,
    retention_days: int = 30,
) -> dict[str, int]:
    """
    Clean up checkpoints older than the specified retention period.

    This function removes checkpoints, checkpoint_writes, and checkpoint_blobs
    for threads that haven't been updated within the retention period.

    Args:
        postgres_url: PostgreSQL connection string.
        retention_days: Number of days to retain checkpoints (default: 30).

    Returns:
        Dictionary with counts of deleted rows from each table.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_timestamp_ms = int(cutoff_time.timestamp() * 1000)

    results = {
        "checkpoints_deleted": 0,
        "writes_deleted": 0,
        "blobs_deleted": 0,
        "threads_cleaned": 0,
    }

    try:
        async with await psycopg.AsyncConnection.connect(postgres_url) as conn:
            async with conn.cursor() as cur:
                # Find threads that haven't been updated in retention_days
                # LangGraph stores created_at as milliseconds since epoch in metadata
                await cur.execute(
                    """
                    SELECT DISTINCT thread_id
                    FROM checkpoints
                    WHERE thread_id NOT IN (
                        SELECT DISTINCT thread_id
                        FROM checkpoints
                        WHERE COALESCE(
                            (metadata->>'created_at')::BIGINT,
                            0
                        ) >= %s
                    )
                    """,
                    (cutoff_timestamp_ms,),
                )
                rows = await cur.fetchall()
                old_threads = [row[0] for row in rows]

                if not old_threads:
                    await logger.ainfo("No old checkpoints to clean up")
                    return results

                results["threads_cleaned"] = len(old_threads)
                await logger.ainfo(f"Found {len(old_threads)} threads to clean up")

                # Delete checkpoint_writes for old threads
                await cur.execute(
                    """
                    DELETE FROM checkpoint_writes
                    WHERE thread_id = ANY(%s)
                    """,
                    (old_threads,),
                )
                results["writes_deleted"] = cur.rowcount or 0

                # Try to delete checkpoint_blobs if table exists
                try:
                    await cur.execute(
                        """
                        DELETE FROM checkpoint_blobs
                        WHERE thread_id = ANY(%s)
                        """,
                        (old_threads,),
                    )
                    results["blobs_deleted"] = cur.rowcount or 0
                except psycopg.errors.UndefinedTable:
                    pass  # Table doesn't exist, skip

                # Delete checkpoints for old threads
                await cur.execute(
                    """
                    DELETE FROM checkpoints
                    WHERE thread_id = ANY(%s)
                    """,
                    (old_threads,),
                )
                results["checkpoints_deleted"] = cur.rowcount or 0

                await conn.commit()

                await logger.ainfo(
                    f"Cleanup complete: {results['checkpoints_deleted']} checkpoints, "
                    f"{results['writes_deleted']} writes, "
                    f"{results['blobs_deleted']} blobs deleted "
                    f"from {results['threads_cleaned']} threads"
                )

    except Exception as e:
        await logger.aerror(f"Error during checkpoint cleanup: {e}")
        raise

    return results


async def get_checkpoint_stats(postgres_url: str) -> dict:
    """
    Get statistics about checkpoints in the database.

    Args:
        postgres_url: PostgreSQL connection string.

    Returns:
        Dictionary with checkpoint statistics.
    """
    stats = {
        "total_threads": 0,
        "total_checkpoints": 0,
        "oldest_checkpoint_age_days": None,
        "newest_checkpoint_age_days": None,
    }

    try:
        async with await psycopg.AsyncConnection.connect(postgres_url) as conn:
            async with conn.cursor() as cur:
                # Count distinct threads
                await cur.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoints")
                row = await cur.fetchone()
                stats["total_threads"] = row[0] if row else 0

                # Count total checkpoints
                await cur.execute("SELECT COUNT(*) FROM checkpoints")
                row = await cur.fetchone()
                stats["total_checkpoints"] = row[0] if row else 0

                # Get oldest and newest checkpoint ages
                await cur.execute(
                    """
                    SELECT
                        MIN((metadata->>'created_at')::BIGINT),
                        MAX((metadata->>'created_at')::BIGINT)
                    FROM checkpoints
                    WHERE metadata->>'created_at' IS NOT NULL
                    """
                )
                row = await cur.fetchone()
                if row and row[0] and row[1]:
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    stats["oldest_checkpoint_age_days"] = (now_ms - row[0]) / (1000 * 60 * 60 * 24)
                    stats["newest_checkpoint_age_days"] = (now_ms - row[1]) / (1000 * 60 * 60 * 24)

    except Exception as e:
        await logger.aerror(f"Error getting checkpoint stats: {e}")

    return stats


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()

    async def main():
        postgres_url = os.environ.get("POSTGRES_URL")
        if not postgres_url:
            print("Error: POSTGRES_URL environment variable not set")
            return

        print("Checkpoint Statistics:")
        stats = await get_checkpoint_stats(postgres_url)
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

        print("\nRunning cleanup (30 day retention)...")
        results = await cleanup_old_checkpoints(postgres_url, retention_days=30)
        print("Cleanup Results:")
        for key, value in results.items():
            print(f"  {key}: {value}")

    asyncio.run(main())
