-- Migration 009: Automations V2.1 audiences and campaign execution history.
-- PostgreSQL compatible. Additive only. DO NOT execute on production without review.
BEGIN;
CREATE TABLE IF NOT EXISTS automation_campaigns (
    id SERIAL PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE, name VARCHAR(200) NOT NULL,
    automation_type VARCHAR(50) NOT NULL DEFAULT 'custom', status VARCHAR(20) NOT NULL DEFAULT 'draft',
    audience_type VARCHAR(20) NOT NULL DEFAULT 'dynamic', audience_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    schedule_type VARCHAR(30) NOT NULL, schedule_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    timezone VARCHAR(80) NOT NULL, send_window_start VARCHAR(5), send_window_end VARCHAR(5),
    cooldown_days INTEGER NOT NULL DEFAULT 0, channel VARCHAR(30) NOT NULL DEFAULT 'whatsapp', message_template TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_campaign_org_store_name UNIQUE (organization_id, store_id, name)
);
CREATE TABLE IF NOT EXISTS automation_audience_members (id SERIAL PRIMARY KEY, automation_id INTEGER NOT NULL REFERENCES automation_campaigns(id) ON DELETE CASCADE, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE, included BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT uq_campaign_member UNIQUE (automation_id, customer_id));
CREATE TABLE IF NOT EXISTS automation_runs (id SERIAL PRIMARY KEY, automation_id INTEGER NOT NULL REFERENCES automation_campaigns(id) ON DELETE CASCADE, organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, status VARCHAR(20) NOT NULL, run_key VARCHAR(100) NOT NULL, matched_count INTEGER NOT NULL DEFAULT 0, eligible_count INTEGER NOT NULL DEFAULT 0, sent_count INTEGER NOT NULL DEFAULT 0, failed_count INTEGER NOT NULL DEFAULT 0, excluded_count INTEGER NOT NULL DEFAULT 0, started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), completed_at TIMESTAMPTZ, CONSTRAINT uq_campaign_run_key UNIQUE (automation_id, run_key));
CREATE TABLE IF NOT EXISTS automation_recipient_executions (id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE, status VARCHAR(20) NOT NULL, exclusion_reason VARCHAR(50), rendered_message TEXT, sent_at TIMESTAMPTZ, CONSTRAINT uq_campaign_run_customer UNIQUE (run_id, customer_id));
CREATE INDEX IF NOT EXISTS ix_campaign_org_status ON automation_campaigns (organization_id, status);
CREATE INDEX IF NOT EXISTS ix_campaign_recipient_run ON automation_recipient_executions (run_id);
COMMIT;
