"""Read-only, privacy-safe per-request export provenance reconciliation.

This is a diagnostic for engineers and reviewers, not an export or a release
decision. Only exact signed Shopify subject/store joins are counted. Sources
without such a verified join must remain visibly *unknown*, never zero.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest
from .shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError, assess_shopify_privacy_case,
)
from .shopify_privacy_inventory_coverage import inspect_shopify_privacy_coverage
from .shopify_privacy_inventory_report import build_shopify_privacy_field_inventory
from .shopify_privacy_local_processor import (
    ShopifyLocalPrivacyError, inspect_local_customer_export_counts,
)
from .shopify_privacy_legacy_ai_attribution import (
    ShopifyLegacyAttributionError, inspect_shopify_legacy_ai_attribution,
)

# Local partial encrypted snapshot includes nested item and message rows, but
# does not attest field completeness, third-party copies or delivery approval.
_PARTIAL_SNAPSHOT_COUNTS = {
    "customer_store_profiles": "profiles",
    "orders": "orders",
    "order_items": "order_items",
    "conversations": "conversations",
    "messages": "messages",
    "conversational_checkouts": "checkouts",
}
# Scoped automation counts are deliberately not in the local ciphertext.
_LINKED_AUTOMATION_COUNTS = {
    "automation_audience_members": "automation_audience_members",
    "automation_recipient_executions": "automation_campaign_recipients",
    "automation_delivery_attempts": "automation_delivery_attempts",
    "automation_flow_recipient_executions": "automation_flow_recipients",
    "automation_node_executions": "automation_flow_node_executions",
}


class ShopifyExportCoverageError(ValueError):
    """Stable codes only. Never echo a customer, shop or selector."""


def inspect_shopify_export_provenance(
    db: Session, *, request_id: str,
) -> dict:
    """Reconcile known schema coverage with exact scoped database COUNTs.

    Explicitly unscanned surfaces remain unknown, even when *other* sources
    contain zero rows. This prevents false readiness of incomplete exports.
    """
    try:
        assessment = assess_shopify_privacy_case(db, request_id=request_id)
    except ShopifyPrivacyAssessmentError as exc:
        raise ShopifyExportCoverageError("INVALID_PRIVACY_REQUEST_ID") from exc
    if assessment is None:
        raise ShopifyExportCoverageError("PRIVACY_REQUEST_NOT_FOUND")
    if not assessment.verified_signed_intake:
        raise ShopifyExportCoverageError("SIGNED_INTAKE_REQUIRED")
    if not assessment.verified_shop_scope:
        raise ShopifyExportCoverageError("SHOPIFY_SUBJECT_OR_STORE_UNRESOLVED")
    state = db.query(
        ShopifyPrivacyRequest.status, ShopifyPrivacyRequest.completed_at,
        ShopifyPrivacyRequest.organization_id, ShopifyPrivacyRequest.store_id,
    ).filter(ShopifyPrivacyRequest.request_id == request_id).first()
    if (
        state is None
        or state.status != "pending_policy_review"
        or state.completed_at is not None
    ):
        raise ShopifyExportCoverageError("HISTORICAL_OR_NONPENDING_CASE_REQUIRES_REVIEW")
    # Reuse the existing *read-only* counting path; unlike a real data export it
    # never reads names, contact columns, order notes or message bodies.
    try:
        counts = inspect_local_customer_export_counts(db, request_id=request_id)
    except ShopifyLocalPrivacyError as exc:
        raise ShopifyExportCoverageError(str(exc)) from exc

    try:
        unattributed = inspect_shopify_legacy_ai_attribution(
            db, organization_id=state.organization_id, store_id=state.store_id,
        )
    except ShopifyLegacyAttributionError as exc:
        raise ShopifyExportCoverageError(str(exc)) from exc

    inventory = inspect_shopify_privacy_coverage()
    field_inventory = build_shopify_privacy_field_inventory()
    field_summaries = {
        row["table"]: row for row in field_inventory["table_reviews"]
    }
    surface_counts = {
        **{name: getattr(counts, attr) for name, attr in _PARTIAL_SNAPSHOT_COUNTS.items()},
        **{name: getattr(counts, attr) for name, attr in _LINKED_AUTOMATION_COUNTS.items()},
    }
    sources = []
    for entry in inventory.tables:
        # A count is *not* permission to include a column or evidence that
        # it is absent from another source or provider.
        count = surface_counts.get(entry.table)
        if entry.table in _PARTIAL_SNAPSHOT_COUNTS:
            state = "partial_snapshot_unapproved"
            blocker = "FIELD_LEVEL_PROVENANCE_NOT_APPROVED"
        elif entry.table in _LINKED_AUTOMATION_COUNTS:
            state = "linked_count_only_not_exported"
            blocker = "AUTOMATION_EXPORT_NOT_IMPLEMENTED"
        else:
            state = "not_attributed_or_exported"
            blocker = "SOURCE_ATTRIBUTION_AND_EXPORT_NOT_VERIFIED"
        field_review = field_summaries.get(entry.table, {})
        sources.append({
            "source": entry.table,
            "ownership": entry.ownership,
            "inventory_coverage": entry.coverage,
            "candidate_sensitive_columns": field_review.get("candidate_field_count", 0),
            "schema_subject_linkage": field_review.get(
                "subject_linkage", "unverified",
            ),
            "matched_subject_store_rows": count,
            "reconciliation_state": state,
            "blocker_code": blocker,
            "export_verified": False,
        })

    blockers = {
        "FIELD_LEVEL_PROVENANCE_NOT_APPROVED",
        "UNSCANNED_SENSITIVE_SOURCES_REMAIN",
        "EXTERNAL_PROCESSOR_AND_FILE_EXPORT_UNVERIFIED",
        "RETENTION_AND_LEGAL_HOLD_APPROVAL_MISSING",
        "INDEPENDENT_DELIVERY_AUTHORIZATION_MISSING",
    }
    blockers.update(unattributed["blockers"])
    if counts.requested_orders_not_resolved:
        blockers.add("REQUESTED_SHOPIFY_ORDERS_UNRESOLVED")
    if assessment.shared_customers_protected:
        blockers.add("SHARED_CUSTOMER_IDENTITY_REQUIRES_REVIEW")
    if field_inventory["unclassified_sensitive_tables"]:
        blockers.add("UNCLASSIFIED_SENSITIVE_TABLES_REQUIRE_REVIEW")
    if inventory.missing_declared_tables:
        blockers.add("MISSING_DECLARED_SOURCE_TABLES_REQUIRE_REVIEW")
    if counts.automation_attribution != "verified_external_customer_id":
        blockers.add("AUTOMATION_SUBJECT_ATTRIBUTION_UNVERIFIED")

    return {
        "schema": "diaglob.shopify.export_provenance_review.v1",
        "schema_sha256": field_inventory["schema_sha256"],
        "candidate_sensitive_column_count": field_inventory["candidate_field_count"],
        "request_id": request_id,
        "topic": "customers/data_request",
        "signed_intake_verified": True,
        "subject_store_scope_verified": True,
        "counted_local_snapshot_sources": len(_PARTIAL_SNAPSHOT_COUNTS),
        "counted_automation_sources": len(_LINKED_AUTOMATION_COUNTS),
        "unresolved_requested_order_count": counts.requested_orders_not_resolved,
        "shared_customer_records_requiring_review": assessment.shared_customers_protected,
        "unattributed_legacy_and_ai": unattributed,
        "sources": sources,
        "unclassified_sensitive_tables": field_inventory["unclassified_sensitive_tables"],
        "missing_declared_tables": list(inventory.missing_declared_tables),
        "external_review_areas": [
            {"area": area, "reconciliation_state": "unverified"}
            for area in inventory.external_review_areas
        ],
        "blockers": sorted(blockers),
        "contains_customer_data": False,
        "complete": False,
        "live_export_authorized": False,
        "merchant_delivery_authorized": False,
        "shopify_fulfillment_complete": False,
    }
