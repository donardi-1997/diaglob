-- ============================================================
-- MIGRATION 003: AUTOMATIONS
-- ============================================================
-- Idempotent PostgreSQL migration.
-- Safe to run multiple times.
-- DO NOT execute in production without approval.
-- ============================================================


-- ============================================================
-- AUTOMATIONS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS automations (
    id              SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL
                        REFERENCES organizations(id) ON DELETE CASCADE,
    store_id        INTEGER
                        REFERENCES stores(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_type    VARCHAR(50) NOT NULL DEFAULT 'manual',
    conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    actions_json    JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by      INTEGER
                        REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);


-- Indexes for automations
CREATE INDEX IF NOT EXISTS ix_automations_organization
    ON automations(organization_id);

CREATE INDEX IF NOT EXISTS ix_automations_store
    ON automations(store_id);

CREATE INDEX IF NOT EXISTS ix_automations_trigger
    ON automations(trigger_type);

CREATE INDEX IF NOT EXISTS ix_automations_active
    ON automations(active);


-- Partial unique: same name per store within an org
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_automation_org_store_name'
    ) THEN
        ALTER TABLE automations
            ADD CONSTRAINT uq_automation_org_store_name
            UNIQUE (organization_id, store_id, name);
    END IF;
END $$;


-- ============================================================
-- AUTOMATION EXECUTIONS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS automation_executions (
    id              SERIAL PRIMARY KEY,
    automation_id   INTEGER NOT NULL
                        REFERENCES automations(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL
                        REFERENCES organizations(id) ON DELETE CASCADE,
    store_id        INTEGER
                        REFERENCES stores(id) ON DELETE SET NULL,
    event_type      VARCHAR(50) NOT NULL,
    event_id        VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    input_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message   TEXT,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP
);


-- Indexes for executions
CREATE INDEX IF NOT EXISTS ix_automation_executions_automation
    ON automation_executions(automation_id);

CREATE INDEX IF NOT EXISTS ix_automation_executions_organization
    ON automation_executions(organization_id);

CREATE INDEX IF NOT EXISTS ix_automation_executions_store
    ON automation_executions(store_id);

CREATE INDEX IF NOT EXISTS ix_automation_executions_status
    ON automation_executions(status);

CREATE INDEX IF NOT EXISTS ix_automation_executions_started
    ON automation_executions(started_at DESC);


-- Partial status check
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_automation_execution_status'
    ) THEN
        ALTER TABLE automation_executions
            ADD CONSTRAINT ck_automation_execution_status
            CHECK (status IN ('pending','running','success','failed','skipped'));
    END IF;
END $$;


-- Trigger type check
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_automation_trigger_type'
    ) THEN
        ALTER TABLE automations
            ADD CONSTRAINT ck_automation_trigger_type
            CHECK (trigger_type IN (
                'manual',
                'order.created',
                'order.failed',
                'conversation.created',
                'message.received'
            ));
    END IF;
END $$;
