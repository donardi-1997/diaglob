"""Static field-level privacy coverage audit; never reads customer records.

This inventory is diagnostic only. It cannot authorize live exports, erasure,
merchant delivery, or retention decisions.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import MetaData

from ..db import Base
from .. import models as _models  # noqa: F401
from .shopify_privacy_inventory_coverage import DECLARED_COVERAGE

# Fields below are inferred from the existing partial local export and redaction
# manifest. They are NOT approval to export/delete those records in production.
# The "customers" row is organization-shared and MUST NOT be auto-mutated
# because a customer can belong to multiple independent Shopify stores.
EXPORT_FIELD_CANDIDATES = {
    "customer_store_profiles": (
        "external_customer_id", "orders_count", "total_spent",
        "currency", "last_order_ref",
    ),
    "orders": (
        "shopify_order_id", "order_number", "financial_status", "total_amount",
        "currency", "shipping_address", "note",
    ),
    "order_items": ("title", "sku", "quantity", "unit_price"),
    "conversations": ("channel", "preview"),
    "messages": ("sender", "text", "created_at"),
    "conversational_checkouts": (
        "status", "customer_name", "phone", "address_raw", "address_line",
        "address_complement", "neighborhood", "city", "region",
        "country_code", "postal_code", "delivery_reference", "failure_reason",
    ),
}
REDACTION_FIELD_CANDIDATES = {
    "customers": ("name", "phone", "email"),
    "customer_store_profiles": ("external_customer_id", "last_order_ref"),
    "orders": ("note", "shipping_address", "invoice_url", "external_last_error"),
    "order_items": ("title", "sku", "shopify_line_item_id"),
    "conversations": ("preview", "tags"),
    "messages": ("text", "external_message_id"),
    "conversational_checkouts": (
        "customer_name", "phone", "address_raw", "address_line",
        "address_complement", "neighborhood", "city", "region",
        "postal_code", "delivery_reference", "failure_reason",
    ),
}
LINEAGE_FIELD_CANDIDATES = {
    "customers": ("organization_id",),
    "customer_store_profiles": ("organization_id", "store_id", "customer_id"),
    "orders": ("organization_id", "store_id", "customer_id"),
    "order_items": ("organization_id", "store_id", "order_id"),
    "conversations": ("organization_id", "store_id", "customer_id"),
    "messages": ("conversation_id",),
    "conversational_checkouts": (
        "organization_id", "store_id", "customer_id", "conversation_id",
    ),
}
SOURCE_FIELDS = {
    name: tuple(sorted(set(
        EXPORT_FIELD_CANDIDATES.get(name, ())
        + REDACTION_FIELD_CANDIDATES.get(name, ())
        + LINEAGE_FIELD_CANDIDATES.get(name, ())
    )))
    for name in sorted(set(EXPORT_FIELD_CANDIDATES)
                       | set(REDACTION_FIELD_CANDIDATES)
                       | set(LINEAGE_FIELD_CANDIDATES))
}


@dataclass(frozen=True)
class ShopifyPrivacyFieldCoverage:
    source: str
    declared_fields: tuple[str, ...]
    present_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unmapped_columns: tuple[str, ...]
    status: str = "review_required"
    ownership: str = "unverified"


def audit_shopify_privacy_field_coverage(
    metadata: MetaData | None = None,
) -> tuple[ShopifyPrivacyFieldCoverage, ...]:
    """Return only schema identifiers; never raw values or database rows."""
    metadata = metadata if metadata is not None else Base.metadata
    declared_tables = {entry.table: entry.ownership for entry in DECLARED_COVERAGE}
    result = []
    for source, fields in sorted(SOURCE_FIELDS.items()):
        if source not in declared_tables:
            raise ValueError("PRIVACY_SOURCE_NOT_DECLARED")
        table = metadata.tables.get(source)
        columns = {col.name for col in table.columns} if table is not None else set()
        present = tuple(sorted(set(fields) & columns))
        missing = tuple(sorted(set(fields) - columns))
        unmapped = tuple(sorted(columns - set(fields)))
        result.append(ShopifyPrivacyFieldCoverage(
            source=source,
            declared_fields=tuple(fields),
            present_fields=present,
            missing_fields=missing,
            unmapped_columns=unmapped,
            ownership=declared_tables[source],
        ))
    return tuple(result)


def summarize_shopify_privacy_export_schema_readiness(
    metadata: MetaData | None = None,
) -> dict:
    """Report schema drift without reading rows or permitting a live export.

    Coverage of column names is necessary but insufficient: lineage,
    subject-to-record matching, retention and external processors still need
    explicit approvals. Even a completely mapped schema cannot clear the gate.
    """
    audit = audit_shopify_privacy_field_coverage(metadata)
    sources = [
        {
            "source": item.source,
            "ownership": item.ownership,
            "declared_field_count": len(item.declared_fields),
            "candidate_export_fields": list(EXPORT_FIELD_CANDIDATES.get(item.source, ())),
            "candidate_redaction_fields": list(REDACTION_FIELD_CANDIDATES.get(item.source, ())),
            "candidate_lineage_fields": list(LINEAGE_FIELD_CANDIDATES.get(item.source, ())),
            "missing_fields": list(item.missing_fields),
            "unmapped_columns": list(item.unmapped_columns),
            "status": item.status,
        }
        for item in audit
    ]
    blockers = [
        "FIELD_LEVEL_PROVENANCE_REQUIRES_REVIEW",
        "SHARED_CUSTOMER_FIELD_OWNERSHIP_UNRESOLVED",
    ]
    if any(item.missing_fields for item in audit):
        blockers.append("DECLARED_EXPORT_FIELDS_MISSING")
    if any(item.unmapped_columns for item in audit):
        blockers.append("UNMAPPED_EXPORT_COLUMNS_REQUIRE_REVIEW")
    return {
        "sources": sources,
        "blockers": blockers,
        "contains_personal_data": False,
        "real_export_authorized": False,
        "delivery_authorized": False,
        "fulfillment_complete": False,
    }
