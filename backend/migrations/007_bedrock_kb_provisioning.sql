-- Migration 007: Bedrock Knowledge Base Provisioning Status
-- Adds provisioning status tracking for dynamically created Bedrock KBs.
--
-- PostgreSQL compatible. Idempotent.
-- DO NOT execute on production without review.

BEGIN;

-- ============================================================
-- knowledge_bases: add provisioning status fields
-- ============================================================

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS external_status VARCHAR(30);

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS external_last_error TEXT;

-- Backfill existing rows:
-- KB with both external_id and external_data_source_id -> ready
-- Others -> pending
UPDATE knowledge_bases
SET external_status =
    CASE
        WHEN external_id IS NOT NULL
         AND external_data_source_id IS NOT NULL
        THEN 'ready'
        ELSE 'pending'
    END
WHERE external_status IS NULL;

-- Set default for future rows
ALTER TABLE knowledge_bases
    ALTER COLUMN external_status SET DEFAULT 'pending';

COMMIT;
