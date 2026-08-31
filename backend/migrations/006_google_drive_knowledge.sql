-- Migration 006: Google Drive + Docs Knowledge Sources
-- Adds columns for Drive file/folder/Doc tracking.
-- Extends Google scopes support for drive.readonly.
--
-- PostgreSQL compatible. Idempotent.
-- DO NOT execute on production without review.

BEGIN;

-- ============================================================
-- knowledge_sources: extend for Google Drive / Docs
-- ============================================================

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS external_mime_type VARCHAR(255);

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS external_modified_at TIMESTAMP;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS parent_source_id INTEGER
        REFERENCES knowledge_sources(id) ON DELETE SET NULL;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS external_size BIGINT;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS sync_generation INTEGER
        NOT NULL DEFAULT 0;

-- Index for parent-child folder queries
CREATE INDEX IF NOT EXISTS
    idx_knowledge_source_parent
    ON knowledge_sources(parent_source_id)
    WHERE parent_source_id IS NOT NULL;

-- Index for freshness queries (external modified time)
CREATE INDEX IF NOT EXISTS
    idx_knowledge_source_modified
    ON knowledge_sources(external_modified_at)
    WHERE external_modified_at IS NOT NULL;

-- Prevent the same active Drive item from being attached twice to one KB.
-- Sheets keep their migration 005 tab-specific uniqueness rule.
CREATE UNIQUE INDEX IF NOT EXISTS
    uq_knowledge_source_kb_drive_item
    ON knowledge_sources(
        knowledge_base_id,
        external_id,
        source_type
    )
    WHERE active IS TRUE
      AND external_id IS NOT NULL
      AND source_type IN (
          'google_doc',
          'google_drive_file',
          'google_drive_folder'
      );

-- ============================================================
-- google_connections: store granted scopes for
-- incremental auth detection
-- ============================================================

-- scopes column already exists (Text, nullable).
-- No schema change needed. The OAuth callback already
-- stores granted scopes in GoogleConnection.scopes.

COMMIT;
