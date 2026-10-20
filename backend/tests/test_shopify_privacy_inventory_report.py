"""Metadata-only privacy inventory and legally gated retention templates."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, Text

from app.api.shopify_privacy_backlog import (
    get_shopify_privacy_inventory,
    get_shopify_privacy_retention_template,
)
from app.services.shopify_privacy_inventory_report import (
    build_shopify_privacy_field_inventory,
    build_shopify_retention_review_template,
)


def test_field_inventory_flags_unknown_json_text_credentials_and_contact():
    metadata = MetaData()
    Table(
        "unknown_events", metadata,
        Column("id", Integer, primary_key=True),
        Column("blob", JSON),
        Column("memo", Text),
        Column("api_key", String(255)),
        Column("email", String(255)),
    )
    Table(
        "safe_numeric_counts", metadata,
        Column("id", Integer, primary_key=True),
        Column("counter", Integer),
    )
    result = build_shopify_privacy_field_inventory(metadata)
    assert result["table_count"] == 2
    assert result["candidate_field_count"] == 4
    assert result["unclassified_sensitive_tables"] == ["unknown_events"]
    assert not any(
        record["table"] == "safe_numeric_counts"
        for record in result["field_reviews"]
    )
    categories = {item["column"]: item["category"] for item in result["field_reviews"]}
    assert categories == {
        "blob": "json_or_dynamic_payload",
        "memo": "unstructured_text",
        "api_key": "credential_or_secret",
        "email": "contact",
    }
    assert all(item["retention_review"] == "required" for item in result["field_reviews"])
    assert result["ready_for_live_privacy_processing"] is False
    assert result["live_export_authorized"] is False
    assert result["live_erasure_authorized"] is False


def test_unknown_json_only_table_fails_review_without_naming_hint():
    metadata = MetaData()
    Table(
        "events_v2", metadata,
        Column("id", Integer, primary_key=True),
        Column("blob", JSON),
    )
    result = build_shopify_privacy_field_inventory(metadata)
    assert result["unclassified_sensitive_tables"] == ["events_v2"]


def test_inventory_schema_fingerprint_detects_ddl_drift_but_no_data():
    metadata = MetaData()
    table = Table(
        "risk_features", metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(255)),
    )
    first = build_shopify_privacy_field_inventory(metadata)
    second = build_shopify_privacy_field_inventory(metadata)
    assert first["schema_sha256"] == second["schema_sha256"]
    table.append_column(Column("customer_notes", Text))
    third = build_shopify_privacy_field_inventory(metadata)
    assert third["schema_sha256"] != first["schema_sha256"]
    assert third["candidate_field_count"] == first["candidate_field_count"] + 1
    assert "customer@example.com" not in json.dumps(third)
    assert third["field_provenance_verified"] is False


def test_real_orm_field_inventory_never_approves_shared_customer_data():
    report = build_shopify_privacy_field_inventory()
    by_table = {item["table"]: item for item in report["table_reviews"]}
    assert by_table["customers"]["coverage"] == "uncovered"
    assert by_table["customer_store_profiles"]["coverage"] == "partial"
    assert by_table["agent_chat_messages"]["coverage"] == "uncovered"
    assert report["external_sources"]
    assert all(not item["independently_verified"] for item in report["external_sources"])
    assert report["ready_for_live_privacy_processing"] is False


def test_retention_template_never_infers_a_period_or_legal_approval():
    template = build_shopify_retention_review_template()
    assert template["version"] == 1
    assert template["categories"]
    assert "financial_orders" in {item["category"] for item in template["categories"]}
    for category in template["categories"]:
        assert category["retention_duration"] is None
        assert category["legal_hold_policy"] is None
        assert category["approval_evidence"] is None
        assert category["independently_approved"] is False
        assert category["erasure_authorized"] is False
        assert "lawful_basis_and_jurisdiction" in category["required_decisions"]
        assert "backup_expiry_and_restore_reconciliation" in category["required_decisions"]
    assert template["policy_approved"] is False
    assert template["live_erasure_authorized"] is False


def test_read_only_endpoints_reject_missing_or_wrong_internal_secret(monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-expected-secret")
    for handler in (get_shopify_privacy_inventory, get_shopify_privacy_retention_template):
        for value in (None, "", "incorrect-secret"):
            with pytest.raises(HTTPException) as exc:
                handler(x_internal_secret=value)
            assert exc.value.status_code == 401
    inventory = get_shopify_privacy_inventory(x_internal_secret="synthetic-expected-secret")
    retention = get_shopify_privacy_retention_template(x_internal_secret="synthetic-expected-secret")
    assert inventory["inventory_type"] == "schema_metadata_review_only"
    assert retention["policy_approved"] is False


def test_read_only_endpoints_fail_closed_when_internal_secret_unconfigured(monkeypatch):
    monkeypatch.delenv("DIAGLOB_INTERNAL_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        get_shopify_privacy_inventory(x_internal_secret="a-client-provided-value")
    assert exc.value.status_code == 401
