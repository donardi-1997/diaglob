"""Read-only, field-level Shopify privacy review from ORM schema metadata.

This deliberately does not query customer records or attest that a field is
owned by a particular Shopify store. Detection is a review queue, not a proof
of exhaustiveness, erasure authorization, or compliance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from sqlalchemy import MetaData
from sqlalchemy.sql import sqltypes

from ..db import Base
from .. import models as _models  # noqa: F401 - register mapped domains
from .shopify_privacy_inventory_coverage import (
    EXTERNAL_REVIEW_AREAS,
    inspect_shopify_privacy_coverage,
)
from .shopify_privacy_controls import RETENTION_CONTROLS

# Conservative names: free-form payloads and opaque tokens can contain personal
# information even without a column literally named "customer" or "email".
_FIELD_CATEGORIES = (
    ("credential_or_secret", ("secret", "token", "password", "api_key", "access_key", "authorization", "credential")),
    ("contact", ("email", "phone", "mobile", "contact")),
    ("address_or_location", ("address", "street", "postcode", "postal", "zip", "lat", "lon", "location")),
    ("identity", ("customer", "recipient", "person", "profile", "identity", "birth", "user_id", "partner_id", "subject", "ip_address", "device_id")),
    ("communications", ("message", "conversation", "prompt", "response", "chat", "note", "comment", "transcript")),
    ("external_or_linked_id", ("shopify", "external_", "tracking", "session", "shop_id", "order_id", "store_id")),
    ("opaque_or_generated_content", ("payload", "metadata", "content", "raw_", "document", "file", "image", "attachment", "embedding", "result", "output", "input", "description", "name")),
)


@dataclass(frozen=True)
class ReviewField:
    table: str
    column: str
    category: str
    coverage: str
    subject_linkage: str
    retention_review: str = "required"


def _category(name: str, column_type: object) -> str | None:
    name = name.lower()
    for category, hints in _FIELD_CATEGORIES:
        if any(hint in name for hint in hints):
            return category
    if isinstance(column_type, sqltypes.JSON):
        return "json_or_dynamic_payload"
    if isinstance(column_type, sqltypes.LargeBinary):
        return "binary_or_attachment"
    if isinstance(column_type, sqltypes.Text):
        return "unstructured_text"
    return None


def _subject_linkage(table) -> str:
    columns = {column.name for column in table.columns}
    if {"organization_id", "store_id"} <= columns:
        return "tenant_and_store_columns_present_unverified"
    if "store_id" in columns:
        return "store_column_present_unverified"
    if "organization_id" in columns:
        return "organization_column_only_unverified"
    if any(foreign_key for column in table.columns for foreign_key in column.foreign_keys):
        return "foreign_key_chain_requires_review"
    return "no_explicit_tenant_key_requires_review"


def _schema_signature(metadata: MetaData) -> str:
    """Fingerprint schema shape, not table rows or actual personal values."""
    rows = []
    for name, table in sorted(metadata.tables.items()):
        for column in table.columns:
            rows.append((
                name, column.name, str(column.type), bool(column.nullable),
                tuple(sorted(fk.target_fullname for fk in column.foreign_keys)),
            ))
    material = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_shopify_privacy_field_inventory(metadata: MetaData | None = None) -> dict:
    """Return metadata-only review queues; never provide a live processing PASS."""
    metadata = metadata if metadata is not None else Base.metadata
    coverage = inspect_shopify_privacy_coverage(metadata)
    declarations = {entry.table: entry.coverage for entry in coverage.tables}
    reviewed = []
    summary = []
    for table_name, table in sorted(metadata.tables.items()):
        linkage = _subject_linkage(table)
        level = declarations.get(table_name, "unclassified")
        candidates = []
        for column in table.columns:
            category = _category(column.name, column.type)
            if category is None:
                continue
            candidates.append(category)
            reviewed.append(asdict(ReviewField(
                table=table_name,
                column=column.name,
                category=category,
                coverage=level,
                subject_linkage=linkage,
            )))
        if candidates or table_name in declarations:
            summary.append({
                "table": table_name,
                "coverage": level,
                "subject_linkage": linkage,
                "candidate_field_count": len(candidates),
                "requires_independent_review": True,
            })
    # A newly introduced JSON/blob column must be flagged even when its name
    # lacks the simple naming hints used by the legacy table-level inventory.
    unknown_sensitive = sorted(set(coverage.unclassified_sensitive_tables) | {
        entry["table"] for entry in summary
        if entry["coverage"] == "unclassified" and entry["candidate_field_count"] > 0
    })
    return {
        "inventory_type": "schema_metadata_review_only",
        "schema_sha256": _schema_signature(metadata),
        "table_count": len(metadata.tables),
        "candidate_field_count": len(reviewed),
        "table_reviews": summary,
        "field_reviews": reviewed,
        "unclassified_sensitive_tables": unknown_sensitive,
        "missing_declared_tables": list(coverage.missing_declared_tables),
        "external_sources": [
            {"area": area, "independently_verified": False}
            for area in EXTERNAL_REVIEW_AREAS
        ],
        "field_provenance_verified": False,
        "live_export_authorized": False,
        "live_erasure_authorized": False,
        "ready_for_live_privacy_processing": False,
    }


# A retention duration is not inferred from column types, payment system,
# geography, or the Shopify request deadline. Each needs legal approval.
_REQUIRED_RETENTION_DECISIONS = (
    "processing_purpose",
    "lawful_basis_and_jurisdiction",
    "retention_duration_and_start_event",
    "statutory_exception_and_legal_hold",
    "minimum_data_to_retain",
    "deletion_or_anonymization_procedure",
    "external_processors_and_copies",
    "backup_expiry_and_restore_reconciliation",
    "independent_approval_and_evidence",
)


def build_shopify_retention_review_template() -> dict:
    """Produce blank decisions, not an executable or approved policy."""
    return {
        "template_type": "privacy_retention_legal_review_only",
        "version": 1,
        "categories": [
            {
                "category": category,
                "review_owner": owner,
                "proposed_handling": handling,
                "required_decisions": list(_REQUIRED_RETENTION_DECISIONS),
                "retention_duration": None,
                "legal_hold_policy": None,
                "approval_evidence": None,
                "independently_approved": False,
                "erasure_authorized": False,
            }
            for category, owner, handling in RETENTION_CONTROLS
        ],
        "policy_approved": False,
        "live_export_authorized": False,
        "live_erasure_authorized": False,
    }
