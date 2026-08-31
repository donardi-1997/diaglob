-- Migration 005: Google Sheets as Knowledge Source
-- Adds Google OAuth state tracking, Google connection model,
-- and extends knowledge_sources for Google Sheet metadata.
--
-- PostgreSQL compatible. Idempotent where possible.
-- DO NOT execute on production without review.

BEGIN;

-- ============================================================
-- google_oauth_states
-- ============================================================
CREATE TABLE IF NOT EXISTS google_oauth_states (
    id SERIAL PRIMARY KEY,
    state_token VARCHAR(128) NOT NULL,
    organization_id INTEGER NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    scopes TEXT,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_google_oauth_states_token
    ON google_oauth_states(state_token);

CREATE INDEX IF NOT EXISTS
    idx_google_oauth_states_org
    ON google_oauth_states(organization_id);

CREATE INDEX IF NOT EXISTS
    idx_google_oauth_states_expires
    ON google_oauth_states(expires_at);

-- ============================================================
-- google_connections
-- ============================================================
CREATE TABLE IF NOT EXISTS google_connections (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255),
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT,
    token_expiry TIMESTAMP,
    scopes TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'connected',
    connected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_google_connection_org
    ON google_connections(organization_id);

-- ============================================================
-- knowledge_sources: extend for Google Sheets
-- ============================================================
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS external_name VARCHAR(500);

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS sheet_name VARCHAR(255);

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS sync_status VARCHAR(30);

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS sync_error TEXT;

ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS metadata_json TEXT;

-- Prevent duplicate same sheet+tab within same KB
CREATE UNIQUE INDEX IF NOT EXISTS
    uq_knowledge_source_kb_sheet_tab
    ON knowledge_sources(knowledge_base_id, external_id, sheet_name)
    WHERE external_id IS NOT NULL AND sheet_name IS NOT NULL;

COMMIT;
