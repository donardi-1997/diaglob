"""Per-shop effective privacy data-surface inventory for a signed case.

Orchestrates already-reviewed read-only inspectors (scope preview, Copilot
impact, automation provenance, legacy AI attribution, subprocessor manifest,
backup coverage) and adds knowledge/file surface counts. Output contains
counts, coverage labels and blockers only — never personal data, row IDs,
tokens, object keys or message content. Every area stays uncovered until an
independent review verifies it; this inventory is not an approval, an export
authorization or proof of GDPR compliance.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..model_domains.knowledge import KnowledgeBase, KnowledgeSource
from ..model_domains.tenancy import knowledge_base_stores
from .shopify_privacy_automation_provenance import (
    inspect_shopify_automation_privacy_impact,
)
from .shopify_privacy_backup_coverage import inspect_shopify_privacy_backup_coverage
from .shopify_privacy_controls import _verified_request
from .shopify_privacy_copilot_impact import inspect_shopify_copilot_privacy_impact
from .shopify_privacy_legacy_ai_attribution import (
    inspect_shopify_legacy_ai_attribution,
)
from .shopify_privacy_scope_preview import preview_shopify_privacy_scope
from .shopify_privacy_subprocessors import inspect_shopify_privacy_subprocessors


class ShopifyPrivacyInventoryError(ValueError):
    """Stable, PII-free per-shop inventory failure codes."""


# Stable blockers aligned with the work-item reasons in
# ``shopify_privacy_processing``; the inventory reports them, never clears them.
_BLOCKERS = (
    "RECORD_PROVENANCE_INCOMPLETE",
    "UNSTRUCTURED_SUBJECT_LINKAGE_UNVERIFIED",
    "QUEUED_PAYLOAD_COVERAGE_UNVERIFIED",
    "EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED",
    "LEGAL_RETENTION_POLICY_NOT_APPROVED",
    "BACKUP_RESTORE_COVERAGE_UNVERIFIED",
)

# Local adoption anchors are operational documents, not legal approval.
_LOCAL_POLICY_ANCHORS = (
    "config/shopify-privacy-policy.json",
    "docs/legal/shopify-privacy-retention-policy.md",
    "docs/legal/security-incident-response-policy.md",
)


def _knowledge_surface_counts(
    db: Session, *, organization_id: int, store_id: int,
) -> dict:
    """Count knowledge bases/sources with store-scope attribution; no values."""
    store_linked_ids = select(knowledge_base_stores.c.knowledge_base_id).where(
        knowledge_base_stores.c.store_id == store_id
    )
    visible_kb_ids = select(KnowledgeBase.id).where(
        KnowledgeBase.organization_id == organization_id,
        or_(
            KnowledgeBase.scope == "organization",
            KnowledgeBase.id.in_(store_linked_ids),
        ),
    )
    org_bases = db.query(KnowledgeBase).filter(
        KnowledgeBase.organization_id == organization_id,
    )
    org_sources = db.query(KnowledgeSource).filter(
        KnowledgeSource.organization_id == organization_id,
    )
    return {
        "knowledge_bases_organization_total": int(org_bases.count()),
        "knowledge_bases_visible_to_store": int(
            db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(visible_kb_ids)).count()
        ),
        "knowledge_bases_selected_for_store": int(
            db.query(KnowledgeBase).filter(
                KnowledgeBase.organization_id == organization_id,
                KnowledgeBase.id.in_(store_linked_ids),
            ).count()
        ),
        "knowledge_sources_organization_total": int(org_sources.count()),
        "knowledge_sources_visible_to_store": int(
            db.query(KnowledgeSource).filter(
                KnowledgeSource.knowledge_base_id.in_(visible_kb_ids),
            ).count()
        ),
        "attribution": "organization_and_store_scope_unverified",
        "content_read": False,
        "export_verified": False,
    }


def build_shopify_privacy_shop_inventory(
    db: Session,
    *,
    request_id: str,
) -> dict:
    """Build the six-area effective inventory for one verified shop.

    Requires signed intake and a matching, non-drifting shop identity before
    any count is produced. Any tenant/attribution integrity failure raises
    instead of returning partial results.
    """
    request = _verified_request(db, request_id)
    if request.organization_id is None or request.store_id is None:
        raise ShopifyPrivacyInventoryError("INVENTORY_TENANT_UNRESOLVED")
    preview = preview_shopify_privacy_scope(db, request)
    copilot = inspect_shopify_copilot_privacy_impact(db, request)
    automation = inspect_shopify_automation_privacy_impact(db, request)
    legacy = inspect_shopify_legacy_ai_attribution(
        db,
        organization_id=request.organization_id,
        store_id=request.store_id,
    )
    knowledge = _knowledge_surface_counts(
        db,
        organization_id=request.organization_id,
        store_id=request.store_id,
    )
    subprocessors = inspect_shopify_privacy_subprocessors(
        db,
        organization_id=request.organization_id,
        store_id=request.store_id,
    )
    backups = inspect_shopify_privacy_backup_coverage(
        db,
        organization_id=request.organization_id,
        store_id=request.store_id,
    )

    active_processors = [
        item["key"]
        for item in subprocessors["subprocessors"]
        if item["activation"] in {"connected", "present_unverified"}
    ]

    areas = {
        "local_structured_records": {
            "coverage": "partial_local_execution_available",
            "counts": {
                "customer_profiles": preview.matched_customer_profiles,
                "orders": preview.matched_store_orders,
                "conversations": preview.matched_store_conversations,
                "conversational_checkouts": preview.matched_conversational_checkouts,
            },
            "shared_customers_protected": preview.shared_customers_protected,
            "local_execution_disabled_by_default": True,
            "blockers": ["RECORD_PROVENANCE_INCOMPLETE"],
        },
        "ai_and_unstructured_content": {
            "coverage": "uncovered",
            "copilot_store_wide": {
                "sessions": copilot.store_sessions_for_review,
                "messages": copilot.store_messages_for_review,
                "tool_calls": copilot.store_tool_calls_for_review,
                "action_approvals": copilot.store_action_approvals_for_review,
                "customer_attribution": copilot.customer_attribution,
                "content_review_required": copilot.content_review_required,
            },
            "knowledge_and_files": knowledge,
            "legacy_attribution": {
                "blockers": legacy["blockers"],
                "ai_sources": [
                    {
                        "source": item["source"],
                        "status": item["status"],
                        "store_key_present": item["store_key_present"],
                        "export_verified": item["export_verified"],
                    }
                    for item in legacy["ai_and_derived_sources"]
                ],
                "live_export_authorized": legacy["live_export_authorized"],
            },
            "blockers": [
                "UNSTRUCTURED_SUBJECT_LINKAGE_UNVERIFIED",
                "AI_PROMPTS_RESPONSES_AND_DERIVED_DATA_UNATTRIBUTED",
            ],
        },
        "automation_and_queues": {
            "coverage": "uncovered",
            "counts": {
                "audience_members": automation.audience_members,
                "campaign_recipients": automation.campaign_recipients,
                "delivery_attempts": automation.delivery_attempts,
                "flow_recipients": automation.flow_recipients,
                "flow_node_executions": automation.flow_node_executions,
            },
            "attribution": automation.attribution,
            "legacy_payload_export": "not_exported",
            "fixture_export_only": True,
            "blockers": [
                "QUEUED_PAYLOAD_COVERAGE_UNVERIFIED",
                "LEGACY_AUTOMATION_JSON_AND_ERROR_PAYLOADS_NOT_EXPORTED",
            ],
        },
        "files_and_object_storage": {
            "coverage": "uncovered",
            "knowledge_sources_organization_total": knowledge[
                "knowledge_sources_organization_total"
            ],
            "knowledge_sources_visible_to_store": knowledge[
                "knowledge_sources_visible_to_store"
            ],
            "object_keys_read": False,
            "objects_exported_or_deleted": False,
            "blockers": ["EXTERNAL_PROCESSOR_AND_FILE_EXPORT_UNVERIFIED"],
        },
        "external_processors": {
            "coverage": "unverified",
            "active_processors": active_processors,
            "active_processor_count": subprocessors["active_processor_count"],
            "manifest": subprocessors["subprocessors"],
            "controls_without_manifest_entry": subprocessors[
                "controls_without_manifest_entry"
            ],
            "manifest_entries_without_control": subprocessors[
                "manifest_entries_without_control"
            ],
            "blockers": ["EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED"],
        },
        "retention_and_legal_holds": {
            "coverage": "locally_adopted_independent_approval_pending",
            "local_policy_anchors": list(_LOCAL_POLICY_ANCHORS),
            "independent_legal_approval": False,
            "destruction_authorized": False,
            "blockers": [
                "LEGAL_RETENTION_POLICY_NOT_APPROVED",
                "RETENTION_SCHEDULE_AND_LEGAL_HOLDS_UNAPPROVED",
            ],
        },
        "backups_and_reingestion": backups,
    }

    blockers = sorted(
        set(_BLOCKERS)
        | {code for area in areas.values() for code in area.get("blockers", [])}
    )
    return {
        "request_id": request_id,
        "topic": request.topic,
        "shop_scope": preview.scope_status,
        "signed_intake_verified": True,
        "shop_identity_verified": True,
        "areas": areas,
        "blockers": blockers,
        "independent_review_completed": False,
        "ready_for_live_privacy_processing": False,
        "requires_manual_review": True,
        "fulfillment_authorized": False,
        "fulfillment_complete": False,
    }
