"""Privacy field mapping scans metadata only; never reads stored values."""
from sqlalchemy import MetaData, Table, Column, Integer, String

from app.services.shopify_privacy_field_coverage import (
    SOURCE_FIELDS, audit_shopify_privacy_field_coverage,
)


def test_coverage_audit_returns_identifiers_only():
    result = audit_shopify_privacy_field_coverage()
    assert len(result) == len(SOURCE_FIELDS)
    assert all(item.status == "review_required" for item in result)
    assert all(item.source in SOURCE_FIELDS for item in result)
    assert all(set(item.present_fields).isdisjoint(item.missing_fields)
               for item in result)
    assert "fulfillment_complete" not in str(result)


def test_coverage_audit_reports_missing_fields_without_reading_values():
    metadata = MetaData()
    Table("orders", metadata,
          Column("customer_id", Integer),
          Column("unmapped_new_payload", String))
    results = {x.source: x for x in audit_shopify_privacy_field_coverage(metadata)}
    assert "order_number" in results["orders"].missing_fields
    assert "unmapped_new_payload" in results["orders"].unmapped_columns
    assert results["orders"].status == "review_required"
    assert results["conversations"].missing_fields


def test_export_schema_readiness_stays_blocked_with_current_models():
    from app.services.shopify_privacy_field_coverage import (
        summarize_shopify_privacy_export_schema_readiness,
    )
    result = summarize_shopify_privacy_export_schema_readiness()
    assert result["real_export_authorized"] is False
    assert result["delivery_authorized"] is False
    assert result["fulfillment_complete"] is False
    assert result["contains_personal_data"] is False
    assert "FIELD_LEVEL_PROVENANCE_REQUIRES_REVIEW" in result["blockers"]
    assert len(result["sources"]) == len(SOURCE_FIELDS)


def test_export_schema_readiness_flags_missing_and_unmapped_fields():
    from app.services.shopify_privacy_field_coverage import (
        summarize_shopify_privacy_export_schema_readiness,
    )
    metadata = MetaData()
    Table("orders", metadata, Column("customer_id", Integer),
          Column("potential_contact_payload", String))
    result = summarize_shopify_privacy_export_schema_readiness(metadata)
    assert "DECLARED_EXPORT_FIELDS_MISSING" in result["blockers"]
    assert "UNMAPPED_EXPORT_COLUMNS_REQUIRE_REVIEW" in result["blockers"]
    assert result["real_export_authorized"] is False
    orders = next(item for item in result["sources"] if item["source"] == "orders")
    assert "order_number" in orders["missing_fields"]
    assert "potential_contact_payload" in orders["unmapped_columns"]


def test_export_schema_gate_never_authorizes_even_if_only_declared_columns():
    from app.services.shopify_privacy_field_coverage import (
        summarize_shopify_privacy_export_schema_readiness,
    )
    metadata = MetaData()
    for source, fields in SOURCE_FIELDS.items():
        Table(source, metadata, *(Column(field, String) for field in fields))
    result = summarize_shopify_privacy_export_schema_readiness(metadata)
    assert result["blockers"] == ["FIELD_LEVEL_PROVENANCE_REQUIRES_REVIEW"]
    assert result["real_export_authorized"] is False
