-- Migration 011: WhatsApp automation delivery compliance. Additive only.
-- DO NOT execute on production without review.
BEGIN;
CREATE TABLE IF NOT EXISTS whatsapp_message_templates (
 id SERIAL PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 whatsapp_connection_id INTEGER NOT NULL REFERENCES whatsapp_connections(id) ON DELETE CASCADE,
 provider_template_id VARCHAR(255), provider_template_name VARCHAR(512) NOT NULL,
 language_code VARCHAR(32) NOT NULL, category VARCHAR(50), status VARCHAR(30) NOT NULL,
 components JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CONSTRAINT uq_whatsapp_template_connection_name_language UNIQUE (whatsapp_connection_id, provider_template_name, language_code)
);
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS message_mode VARCHAR(20) NOT NULL DEFAULT 'free_form';
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS whatsapp_template_id INTEGER REFERENCES whatsapp_message_templates(id) ON DELETE SET NULL;
ALTER TABLE automation_campaigns ADD COLUMN IF NOT EXISTS template_variables JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE automation_recipient_executions ADD COLUMN IF NOT EXISTS template_data JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS ix_whatsapp_template_connection_status ON whatsapp_message_templates (whatsapp_connection_id, status);
COMMIT;
