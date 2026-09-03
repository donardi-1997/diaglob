-- Migration 013: enforce same-flow ownership for automation flow version pointers.
-- PostgreSQL compatible. Abort without changing data if existing pointers are invalid.
-- Manual rollback (only after confirming no cross-flow pointers): drop the two
-- foreign keys and uq_flow_version_flow_id_id in reverse order.
BEGIN;

DO $$
DECLARE
    invalid_current_count INTEGER;
    invalid_active_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO invalid_current_count
    FROM automation_flows f
    LEFT JOIN automation_flow_versions v
      ON v.id = f.current_version_id
    WHERE f.current_version_id IS NOT NULL
      AND (v.id IS NULL OR v.flow_id <> f.id);

    SELECT COUNT(*) INTO invalid_active_count
    FROM automation_flows f
    LEFT JOIN automation_flow_versions v
      ON v.id = f.active_version_id
    WHERE f.active_version_id IS NOT NULL
      AND (v.id IS NULL OR v.flow_id <> f.id);

    IF invalid_current_count > 0 OR invalid_active_count > 0 THEN
        RAISE EXCEPTION
            'Migration 013 aborted: invalid automation flow version pointers (current=%, active=%)',
            invalid_current_count, invalid_active_count;
    END IF;
END
$$;

ALTER TABLE automation_flow_versions
    ADD CONSTRAINT uq_flow_version_flow_id_id UNIQUE (flow_id, id);

ALTER TABLE automation_flows
    ADD CONSTRAINT fk_flow_current_version_same_flow
    FOREIGN KEY (id, current_version_id)
    REFERENCES automation_flow_versions (flow_id, id);

ALTER TABLE automation_flows
    ADD CONSTRAINT fk_flow_active_version_same_flow
    FOREIGN KEY (id, active_version_id)
    REFERENCES automation_flow_versions (flow_id, id);

COMMIT;
