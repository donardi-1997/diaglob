"""Privacy inventory is metadata-only and must fail closed on new PII fields."""
from sqlalchemy import Column, Integer, MetaData, String, Table

from app.services.shopify_privacy_inventory_coverage import (
    inspect_shopify_privacy_coverage,
)


def test_inventory_explicitly_flags_shared_customer_and_uncovered_ai():
    inventory = inspect_shopify_privacy_coverage()
    by_table = {entry.table: entry for entry in inventory.tables}

    assert by_table["customers"].ownership == "organization_shared"
    assert by_table["customers"].coverage == "uncovered"
    assert by_table["customer_store_profiles"].coverage == "partial"
    assert by_table["orders"].coverage == "partial"
    assert by_table["messages"].coverage == "partial"
    assert by_table["agent_chat_messages"].coverage == "uncovered"
    assert by_table["conversational_checkouts"].coverage == "partial"
    assert by_table["knowledge_sources"].coverage == "uncovered"
    assert inventory.ready_for_live_privacy_processing is False
    assert "application_logs_monitoring_and_backups" in inventory.external_review_areas
    assert "retention_legal_holds_and_restore_reingestion" in inventory.external_review_areas


def test_new_sensitive_table_is_reported_not_silently_approved():
    metadata = MetaData()
    Table(
        "new_customer_personalization",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email_address", String(255)),
    )
    Table(
        "non_sensitive_statistics",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("count", Integer),
    )
    inventory = inspect_shopify_privacy_coverage(metadata)
    assert inventory.unclassified_sensitive_tables == (
        "new_customer_personalization",
    )
    assert "non_sensitive_statistics" not in inventory.unclassified_sensitive_tables
    assert "customers" in inventory.missing_declared_tables
    assert inventory.ready_for_live_privacy_processing is False


def test_inventory_has_no_data_query_or_identity_fields():
    inventory = inspect_shopify_privacy_coverage()
    output = repr(inventory)
    assert "shopify_privacy_audit_events" not in inventory.unclassified_sensitive_tables
    for sensitive_value in ("customer@example.com", "Bearer ", "secret-token"):
        assert sensitive_value not in output
    assert len({entry.table for entry in inventory.tables}) == len(inventory.tables)


def test_linked_automation_rows_are_partial_while_parent_and_legacy_rows_stay_uncovered():
    inventory = inspect_shopify_privacy_coverage()
    by_table = {entry.table: entry for entry in inventory.tables}
    linked = (
        "automation_audience_members", "automation_recipient_executions",
        "automation_delivery_attempts", "automation_flow_recipient_executions",
        "automation_node_executions",
    )
    uncovered = (
        "automations", "automation_executions", "automation_campaigns",
        "automation_runs",
        "automation_flows", "automation_flow_versions",
        "automation_flow_runs", "agent_chat_sessions",
        "agent_chat_messages", "agent_chat_tool_calls",
    )
    assert all(by_table[name].coverage == "partial" for name in linked)
    assert all(by_table[name].coverage == "uncovered" for name in uncovered)
    assert inventory.ready_for_live_privacy_processing is False
