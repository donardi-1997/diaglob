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
