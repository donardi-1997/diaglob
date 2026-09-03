-- V2.2: Flow Builder - Multi-Step Automation Engine

-- Flow definitions (top-level)
CREATE TABLE IF NOT EXISTS automation_flows (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    description TEXT,
    current_version_id INTEGER,
    active_version_id INTEGER,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_automation_flows_org ON automation_flows(organization_id);
CREATE INDEX idx_automation_flows_store ON automation_flows(store_id);
CREATE INDEX idx_automation_flows_status ON automation_flows(status);
CREATE UNIQUE INDEX uq_flow_org_store_name ON automation_flows(organization_id, store_id, name);

-- Immutable flow versions (graph snapshots)
CREATE TABLE IF NOT EXISTS automation_flow_versions (
    id SERIAL PRIMARY KEY,
    flow_id INTEGER NOT NULL REFERENCES automation_flows(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    graph JSON NOT NULL,
    published_at TIMESTAMP,
    activated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_flow_versions_flow ON automation_flow_versions(flow_id);
CREATE UNIQUE INDEX uq_flow_version_number ON automation_flow_versions(flow_id, version_number);

-- Flow runs (one trigger occurrence)
CREATE TABLE IF NOT EXISTS automation_flow_runs (
    id SERIAL PRIMARY KEY,
    flow_id INTEGER NOT NULL REFERENCES automation_flows(id) ON DELETE CASCADE,
    flow_version_id INTEGER NOT NULL REFERENCES automation_flow_versions(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    trigger_key VARCHAR(255),
    total_recipients INTEGER NOT NULL DEFAULT 0,
    completed_recipients INTEGER NOT NULL DEFAULT 0,
    failed_recipients INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_flow_runs_flow ON automation_flow_runs(flow_id);
CREATE INDEX idx_flow_runs_org ON automation_flow_runs(organization_id);
CREATE INDEX idx_flow_runs_status ON automation_flow_runs(status);
CREATE UNIQUE INDEX uq_flow_run_trigger_key ON automation_flow_runs(flow_id, trigger_key) WHERE trigger_key IS NOT NULL;

-- Flow recipient executions (per-customer progress through the graph)
CREATE TABLE IF NOT EXISTS automation_flow_recipient_executions (
    id SERIAL PRIMARY KEY,
    flow_run_id INTEGER NOT NULL REFERENCES automation_flow_runs(id) ON DELETE CASCADE,
    flow_version_id INTEGER NOT NULL REFERENCES automation_flow_versions(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    current_node_id VARCHAR(100),
    next_action_at TIMESTAMP,
    claim_token VARCHAR(100),
    claim_expires_at TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(50),
    error_message VARCHAR(500),
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_flow_recipient_run ON automation_flow_recipient_executions(flow_run_id);
CREATE INDEX idx_flow_recipient_customer ON automation_flow_recipient_executions(customer_id);
CREATE INDEX idx_flow_recipient_status ON automation_flow_recipient_executions(status);
CREATE INDEX idx_flow_recipient_next_action ON automation_flow_recipient_executions(next_action_at);
CREATE INDEX idx_flow_recipient_claim ON automation_flow_recipient_executions(claim_expires_at);
CREATE UNIQUE INDEX uq_flow_recipient_run_customer ON automation_flow_recipient_executions(flow_run_id, customer_id);

-- Node execution history (per-node traversal audit)
CREATE TABLE IF NOT EXISTS automation_node_executions (
    id SERIAL PRIMARY KEY,
    flow_recipient_execution_id INTEGER NOT NULL REFERENCES automation_flow_recipient_executions(id) ON DELETE CASCADE,
    node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(50),
    provider_message_id VARCHAR(255),
    error_code VARCHAR(50),
    error_message VARCHAR(500),
    extra_data JSON,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);
CREATE INDEX idx_node_exec_recipient ON automation_node_executions(flow_recipient_execution_id);
CREATE INDEX idx_node_exec_node ON automation_node_executions(node_id);
