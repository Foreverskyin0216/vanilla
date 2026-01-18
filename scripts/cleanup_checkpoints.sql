-- Checkpoint cleanup SQL for Vanilla chatbot
-- This script creates a function and optional scheduled job to clean up
-- checkpoints older than 30 days.

-- Create cleanup function
CREATE OR REPLACE FUNCTION cleanup_old_checkpoints(retention_days INTEGER DEFAULT 30)
RETURNS TABLE(deleted_count BIGINT) AS $$
DECLARE
    cutoff_time TIMESTAMPTZ;
    rows_deleted BIGINT;
BEGIN
    cutoff_time := NOW() - (retention_days || ' days')::INTERVAL;

    -- Delete old checkpoint writes first (foreign key constraint)
    DELETE FROM checkpoint_writes
    WHERE thread_id IN (
        SELECT DISTINCT thread_id
        FROM checkpoints
        WHERE checkpoint_id IS NOT NULL
    );

    -- Delete old checkpoints
    -- The checkpoint table uses thread_id and checkpoint_id
    -- We need to identify old checkpoints by their metadata or creation time
    WITH deleted AS (
        DELETE FROM checkpoints
        WHERE thread_id IN (
            SELECT thread_id
            FROM checkpoints
            GROUP BY thread_id
            HAVING MAX(
                COALESCE(
                    (metadata->>'created_at')::TIMESTAMPTZ,
                    '1970-01-01'::TIMESTAMPTZ
                )
            ) < cutoff_time
        )
        RETURNING *
    )
    SELECT COUNT(*) INTO rows_deleted FROM deleted;

    RETURN QUERY SELECT rows_deleted;
END;
$$ LANGUAGE plpgsql;

-- Create a simpler cleanup based on checkpoint_id timestamp prefix
-- LangGraph checkpoint_id format includes timestamp information
CREATE OR REPLACE FUNCTION cleanup_checkpoints_by_age(retention_days INTEGER DEFAULT 30)
RETURNS TABLE(
    checkpoints_deleted BIGINT,
    writes_deleted BIGINT,
    blobs_deleted BIGINT
) AS $$
DECLARE
    cutoff_time TIMESTAMPTZ;
    cp_deleted BIGINT := 0;
    wr_deleted BIGINT := 0;
    bl_deleted BIGINT := 0;
    old_threads TEXT[];
BEGIN
    cutoff_time := NOW() - (retention_days || ' days')::INTERVAL;

    -- Find threads that haven't been updated in retention_days
    -- by checking the latest checkpoint timestamp in metadata
    SELECT ARRAY_AGG(DISTINCT thread_id) INTO old_threads
    FROM checkpoints c
    WHERE NOT EXISTS (
        SELECT 1 FROM checkpoints c2
        WHERE c2.thread_id = c.thread_id
        AND COALESCE(
            to_timestamp((c2.metadata->>'created_at')::BIGINT / 1000),
            to_timestamp(0)
        ) >= cutoff_time
    );

    IF old_threads IS NOT NULL AND array_length(old_threads, 1) > 0 THEN
        -- Delete checkpoint writes for old threads
        WITH deleted_writes AS (
            DELETE FROM checkpoint_writes
            WHERE thread_id = ANY(old_threads)
            RETURNING *
        )
        SELECT COUNT(*) INTO wr_deleted FROM deleted_writes;

        -- Delete checkpoint blobs for old threads (if table exists)
        BEGIN
            WITH deleted_blobs AS (
                DELETE FROM checkpoint_blobs
                WHERE thread_id = ANY(old_threads)
                RETURNING *
            )
            SELECT COUNT(*) INTO bl_deleted FROM deleted_blobs;
        EXCEPTION WHEN undefined_table THEN
            bl_deleted := 0;
        END;

        -- Delete checkpoints for old threads
        WITH deleted_checkpoints AS (
            DELETE FROM checkpoints
            WHERE thread_id = ANY(old_threads)
            RETURNING *
        )
        SELECT COUNT(*) INTO cp_deleted FROM deleted_checkpoints;
    END IF;

    RETURN QUERY SELECT cp_deleted, wr_deleted, bl_deleted;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission (adjust user as needed)
-- GRANT EXECUTE ON FUNCTION cleanup_checkpoints_by_age TO vanilla;

-- Optional: Create pg_cron schedule (requires pg_cron extension)
-- Run this manually if pg_cron is installed:
--
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule(
--     'cleanup-vanilla-checkpoints',
--     '0 3 * * *',  -- Run at 3 AM daily
--     $$SELECT * FROM cleanup_checkpoints_by_age(30)$$
-- );

COMMENT ON FUNCTION cleanup_checkpoints_by_age IS
'Cleans up LangGraph checkpoints older than the specified retention period (default 30 days).
Returns the count of deleted rows from each table.';
