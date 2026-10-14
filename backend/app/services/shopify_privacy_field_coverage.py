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

# Only proposed field candidates. Every entry still requires a privacy review.
SOURCE_FIELDS = {
    "customer_store_profiles": ("external_customer_id", "customer_id"),
    "orders": ("customer_id", "order_number", "note"),
    "conversations": ("customer_id",),
    "conversational_checkouts": ("customer_id",),
}


@dataclass(frozen=True)
class ShopifyPrivacyFieldCoverage:
    source: str
    declared_fields: tuple[str, ...]
    present_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unmapped_columns: tuple[str, ...]
    status: str = "review_required"


def audit_shopify_privacy_field_coverage(
    metadata: MetaData | None = None,
) -> tuple[ShopifyPrivacyFieldCoverage, ...]:
    """Return only schema identifiers; never raw values or database rows."""
    metadata = metadata if metadata is not None else Base.metadata
    declared_tables = {entry.table for entry in DECLARED_COVERAGE}
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
            "declared_field_count": len(item.declared_fields),
            "missing_fields": list(item.missing_fields),
            "unmapped_columns": list(item.unmapped_columns),
            "status": item.status,
        }
        for item in audit
    ]
    blockers = ["FIELD_LEVEL_PROVENANCE_REQUIRES_REVIEW"]
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
