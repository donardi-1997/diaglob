"""PII-free, fail-closed readiness assessment for a received Shopify privacy case.

An assessment is NOT an export, deletion, fulfillment approval, data-subject
identity attestation or legally sufficient retention decision. It provides a
reviewable summary only after durable signed-receipt evidence is established.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest
from .shopify_privacy_inventory_coverage import inspect_shopify_privacy_coverage
from .shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError,
    preview_shopify_privacy_scope,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")

# Static operational blockers: coverage snapshots and signed intake never
# authorize live customer-data export or erasure.
RELEASE_BLOCKERS = (
    "LEGAL_RETENTION_POLICY_NOT_APPROVED",
    "EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED",
    "BACKUP_RESTORE_AND_REINGESTION_UNVERIFIED",
    "LIVE_FULFILLMENT_NOT_IMPLEMENTED",
)


class ShopifyPrivacyAssessmentError(ValueError):
    """No information about a case may be returned for invalid input."""


@dataclass(frozen=True)
class ShopifyPrivacyCaseAssessment:
    request_id: str
    verified_signed_intake: bool
    verified_shop_scope: bool
    scope_status: str
    matched_customer_profiles: int
    matched_store_orders: int
    matched_store_conversations: int
    matched_conversational_checkouts: int
    shared_customers_protected: int
    incomplete_table_count: int
    missing_declared_table_count: int
    unclassified_sensitive_table_count: int
    external_review_area_count: int
    blockers: tuple[str, ...]
    requires_manual_review: bool = True
    fulfillment_authorized: bool = False

    def safe_dict(self) -> dict:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


def assess_shopify_privacy_case(
    db: Session, *, request_id: str,
) -> ShopifyPrivacyCaseAssessment | None:
    """Inspect evidence for one opaque receipt without changing any records.

    A receipt without a matching signed-intake audit remains untrusted; in
    particular, this function never decrypts its customer selector or probes
    the Shopify store's personal data.
    """
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyAssessmentError("INVALID_PRIVACY_REQUEST_ID")

    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        return None

    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first() is not None

    scope_status = "scope_not_checked"
    verified_scope = False
    counts = (0, 0, 0, 0, 0)
    blockers = list(RELEASE_BLOCKERS)
    if not signed:
        blockers.append("SIGNED_INTAKE_EVIDENCE_MISSING")
    else:
        try:
            scope = preview_shopify_privacy_scope(db, receipt)
        except (ShopifyPrivacyScopeError, ValueError) as exc:
            if str(exc) == "SHOPIFY_PRIVACY_SIGNED_SHOP_HISTORY_CONFLICT":
                blockers.append("SHOPIFY_SIGNED_SHOP_HISTORY_CONFLICT")
            blockers.append("SHOP_SCOPE_NOT_VERIFIED")
        else:
            scope_status = (
                "subject_unresolved"
                if scope.scope_status == "subject_unresolved"
                else "scope_preview_only"
            )
            verified_scope = scope.scope_status != "subject_unresolved"
            counts = (
                scope.matched_customer_profiles,
                scope.matched_store_orders,
                scope.matched_store_conversations,
                scope.matched_conversational_checkouts,
                scope.shared_customers_protected,
            )
            if not verified_scope:
                blockers.append("SHOPIFY_SUBJECT_UNRESOLVED")

    inventory = inspect_shopify_privacy_coverage()
    incomplete = sum(
        item.coverage != "complete" for item in inventory.tables
    )
    if (
        incomplete
        or inventory.unclassified_sensitive_tables
        or inventory.missing_declared_tables
    ):
        blockers.append("DATA_SURFACE_COVERAGE_INCOMPLETE")
    if inventory.unclassified_sensitive_tables:
        blockers.append("UNCLASSIFIED_PII_TABLES_REQUIRE_REVIEW")
    if inventory.missing_declared_tables:
        blockers.append("DECLARED_PRIVACY_TABLES_MISSING")
    if inventory.external_review_areas:
        blockers.append("EXTERNAL_PRIVACY_AREAS_REQUIRE_REVIEW")

    return ShopifyPrivacyCaseAssessment(
        request_id=request_id,
        verified_signed_intake=signed,
        verified_shop_scope=verified_scope,
        scope_status=scope_status,
        matched_customer_profiles=counts[0],
        matched_store_orders=counts[1],
        matched_store_conversations=counts[2],
        matched_conversational_checkouts=counts[3],
        shared_customers_protected=counts[4],
        incomplete_table_count=incomplete,
        missing_declared_table_count=len(inventory.missing_declared_tables),
        unclassified_sensitive_table_count=len(inventory.unclassified_sensitive_tables),
        external_review_area_count=len(inventory.external_review_areas),
        blockers=tuple(blockers),
    )


def prepare_shopify_privacy_export_manifest(
    db: Session, *, request_id: str,
) -> dict | None:
    """Preview source coverage for customer access requests, without exporting PII.

    A signed receipt and a verified subject/store are required before even
    returning source counts. This manifest is NOT an export, fulfillment, or a
    delivery authorization; unresolved processors stay blocked.
    """
    assessment = assess_shopify_privacy_case(db, request_id=request_id)
    if assessment is None:
        return None
    if not assessment.verified_signed_intake:
        raise ShopifyPrivacyAssessmentError("SIGNED_INTAKE_EVIDENCE_MISSING")

    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None or receipt.topic != "customers/data_request":
        raise ShopifyPrivacyAssessmentError("CUSTOMER_EXPORT_TOPIC_REQUIRED")
    if not assessment.verified_shop_scope:
        raise ShopifyPrivacyAssessmentError("SHOPIFY_SUBJECT_UNRESOLVED")

    sources = (
        ("customer_store_profiles", assessment.matched_customer_profiles),
        ("orders", assessment.matched_store_orders),
        ("conversations", assessment.matched_store_conversations),
        ("conversational_checkouts", assessment.matched_conversational_checkouts),
    )
    return {
        "request_id": request_id,
        "topic": "customers/data_request",
        "scope_status": assessment.scope_status,
        "sources": [
            {"name": name, "matching_records": count, "status": "review_required"}
            for name, count in sources
        ],
        "shared_customers_protected": assessment.shared_customers_protected,
        "unclassified_sensitive_table_count": assessment.unclassified_sensitive_table_count,
        "external_review_area_count": assessment.external_review_area_count,
        "blockers": list(assessment.blockers),
        "contains_personal_data": False,
        "export_generated": False,
        "delivery_authorized": False,
        "fulfillment_complete": False,
    }
