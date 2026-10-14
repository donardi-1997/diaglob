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
