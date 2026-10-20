"""PII-free preflight for legacy automations and AI privacy data surfaces.

Legacy automations store arbitrary input/result JSON without customer FK.
Shop-level membership is not evidence that a record belongs to a particular
Shopify buyer. Never parse payloads, match by email/phone or return row IDs.
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..db import Base
from ..models import Automation, AutomationExecution


class ShopifyLegacyAttributionError(ValueError):
    """Stable error codes only; never include subject values in an error."""


# All are unverified: a model-level customer FK is not equivalent to a proven
# Shopify store/subject mapping; indirect and free-form references may exist.
_AI_REVIEW_SOURCES = (
    "agent_action_approvals",
    "agent_chat_sessions",
    "agent_chat_messages",
    "agent_chat_tool_calls",
    "knowledge_sources",
    "customer_risk_reports",
    "customer_risk_disputes",
    "auto_fulfillment_jobs",
)


def inspect_shopify_legacy_ai_attribution(
    db: Session, *, organization_id: int, store_id: int,
) -> dict:
    """Count only potentially relevant legacy execution IDs and inspect schema.

    Call ONLY from a previously authenticated, signed, verified Shopify case.
    This does not resolve buyer ownership; a zero count in one category does
    not prove there are no buyer data in another store, queue or processor.
    """
    if (
        not isinstance(organization_id, int) or isinstance(organization_id, bool)
        or not isinstance(store_id, int) or isinstance(store_id, bool)
        or organization_id <= 0 or store_id <= 0
    ):
        raise ShopifyLegacyAttributionError("UNVERIFIED_LEGACY_TENANT")

    # An execution and its parent must agree on the organization. A cross-
    # organization parent relationship must not be hidden by store filters.
    conflicting_tenant = (
        db.query(AutomationExecution.id)
        .outerjoin(Automation, AutomationExecution.automation_id == Automation.id)
        .filter(
            or_(
                AutomationExecution.organization_id == organization_id,
                Automation.organization_id == organization_id,
            ),
            or_(
                Automation.id.is_(None),
                AutomationExecution.organization_id != Automation.organization_id,
            ),
        )
        .first()
    )
    if conflicting_tenant is not None:
        raise ShopifyLegacyAttributionError("LEGACY_AUTOMATION_PARENT_TENANT_MISMATCH")

    def count(*conditions) -> int:
        return int(
            db.query(func.count(AutomationExecution.id))
            .join(Automation, AutomationExecution.automation_id == Automation.id)
            .filter(
                Automation.organization_id == organization_id,
                AutomationExecution.organization_id == organization_id,
                *conditions,
            ).scalar() or 0
        )

    # A parent and execution may both declare a store, only one might, or
    # neither might. Never infer buyer identity from ANY of these categories.
    store_matched = count(
        Automation.store_id == store_id,
        AutomationExecution.store_id == store_id,
    )
    parent_only = count(
        Automation.store_id == store_id,
        AutomationExecution.store_id.is_(None),
    )
    execution_only = count(
        Automation.store_id.is_(None),
        AutomationExecution.store_id == store_id,
    )
    organization_wide = count(
        Automation.store_id.is_(None),
        AutomationExecution.store_id.is_(None),
    )
    conflicting_store = count(
        or_(
            and_(
                Automation.store_id == store_id,
                AutomationExecution.store_id.is_not(None),
                AutomationExecution.store_id != store_id,
            ),
            and_(
                AutomationExecution.store_id == store_id,
                Automation.store_id.is_not(None),
                Automation.store_id != store_id,
            ),
        )
    )
    if conflicting_store:
        raise ShopifyLegacyAttributionError("LEGACY_AUTOMATION_PARENT_STORE_MISMATCH")

    tables = Base.metadata.tables
    ai_sources = []
    for name in _AI_REVIEW_SOURCES:
        table = tables.get(name)
        if table is None:
            status = "model_missing_requires_review"
            has_customer_fk = False
            has_store = False
        else:
            status = "subject_attribution_unverified"
            has_customer_fk = any(
                fk.target_fullname == "customers.id"
                for column in table.columns for fk in column.foreign_keys
            )
            has_store = "store_id" in table.columns
        ai_sources.append({
            "source": name,
            "status": status,
            "store_key_present": has_store,
            "direct_customer_fk_present": has_customer_fk,
            "customer_shopify_identity_verified": False,
            "matching_subject_rows": None,
            "export_verified": False,
        })

    return {
        "legacy_automation_executions": {
            "both_store_keys_match": store_matched,
            "parent_store_only": parent_only,
            "execution_store_only": execution_only,
            "organization_wide_potential_copies": organization_wide,
            "buyer_linkage": "unavailable_no_customer_fk",
            "matching_subject_rows": None,
            "read_input_or_result_payload": False,
            "export_verified": False,
        },
        "ai_and_derived_sources": ai_sources,
        "blockers": [
            "LEGACY_AUTOMATION_CUSTOMER_ATTRIBUTION_UNVERIFIED",
            "LEGACY_AUTOMATION_JSON_AND_ERROR_PAYLOADS_NOT_EXPORTED",
            "ORGANIZATION_WIDE_RECORDS_REQUIRE_INDEPENDENT_REVIEW",
            "AI_PROMPTS_RESPONSES_AND_DERIVED_DATA_UNATTRIBUTED",
        ],
        "live_export_authorized": False,
        "contains_personal_data": False,
    }
