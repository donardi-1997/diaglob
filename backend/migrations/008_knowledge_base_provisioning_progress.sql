-- Migration 008: Knowledge Base provisioning progress
-- PostgreSQL compatible. Idempotent.
-- DO NOT execute on production without review.

BEGIN;

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS provisioning_stage VARCHAR(50);

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS provisioning_started_at TIMESTAMPTZ;

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS provisioning_stage_started_at TIMESTAMPTZ;

UPDATE knowledge_bases
SET provisioning_stage = CASE
    WHEN external_status = 'ready' THEN 'ready'
    WHEN external_status = 'retrying' THEN 'retrying'
    WHEN external_status = 'failed' THEN 'failed'
    WHEN external_status = 'deleting' THEN 'deleting'
    WHEN external_status = 'pending' THEN 'queued'
    WHEN external_status = 'provisioning' THEN 'creating_vector_index'
    ELSE provisioning_stage
END
WHERE provisioning_stage IS NULL;

COMMIT;
