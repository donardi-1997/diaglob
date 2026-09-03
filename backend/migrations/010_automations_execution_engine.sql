-- Migration 010: durable Automations V2.1A execution engine.
-- PostgreSQL compatible. Additive only. DO NOT execute on production without review.
BEGIN;
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMPTZ;
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS execution_enabled_at TIMESTAMPTZ;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(255);
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS error_code VARCHAR(50);
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS error_message VARCHAR(500);
CREATE TABLE IF NOT EXISTS automation_delivery_attempts (
 id SERIAL PRIMARY KEY, recipient_execution_id INTEGER NOT NULL REFERENCES automation_recipient_executions(id) ON DELETE CASCADE,
 attempt_number INTEGER NOT NULL, status VARCHAR(30) NOT NULL, provider_message_id VARCHAR(255), error_code VARCHAR(50), error_message VARCHAR(500),
 started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS automation_rate_limits (
 id SERIAL PRIMARY KEY, connection_id INTEGER NOT NULL REFERENCES whatsapp_connections(id) ON DELETE CASCADE,
 window_start TIMESTAMPTZ NOT NULL, sent_count INTEGER NOT NULL DEFAULT 0,
 CONSTRAINT uq_automation_rate_limit_window UNIQUE (connection_id, window_start)
);
CREATE INDEX IF NOT EXISTS ix_campaign_due ON automation_campaigns (status, next_run_at);
CREATE INDEX IF NOT EXISTS ix_recipient_due ON automation_recipient_executions (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_recipient_lease ON automation_recipient_executions (lease_expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_run_scheduled_for ON automation_runs (automation_id, scheduled_for) WHERE scheduled_for IS NOT NULL;
COMMIT;
