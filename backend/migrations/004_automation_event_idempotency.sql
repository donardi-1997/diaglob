-- Migration 004: Automation Event Idempotency
-- Adds unique partial index to prevent duplicate automation executions for the same event

-- Unique partial index: one execution per automation per event_id
-- Only applies when event_id is not null (manual triggers may not have event_id)
CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_execution_event
ON automation_executions (automation_id, event_id)
WHERE event_id IS NOT NULL;

-- Add index for faster lookups by event_type + event_id (for debugging/monitoring)
CREATE INDEX IF NOT EXISTS ix_automation_execution_event_type_id
ON automation_executions (event_type, event_id)
WHERE event_id IS NOT NULL;