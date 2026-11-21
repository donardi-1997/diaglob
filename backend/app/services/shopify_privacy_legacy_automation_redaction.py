"""Conservative GDPR redaction of old automation JSON/event payloads.

Exact source ownership is established from organization+store Automation
parents, and for customer requests also from explicit recipient provenance.
Never parse JSON/text to infer Shopify identities. No implicit commit.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..model_domains.automation_provenance import AutomationExecutionProvenance
from ..models import Automation, AutomationExecution

MAX_LEGACY_ROWS = 5000
_RUNNING = frozenset(("running", "pending", "queued", "processing", "retry_wait"))


class ShopifyLegacyAutomationPrivacyError(ValueError):
    """Stable PII-free failure codes."""


def scrub_shopify_legacy_automations(
    db: Session, *, organization_id: int, store_id: int,
    customer_ids: set[int] | None, now: datetime | None = None,
) -> dict:
    """Wipe verified store-specific legacy payloads without other-store impact.

    customer_ids=None: shop/redact (all executions in store-owned rules).
    customer_ids=set(): no exact buyer link; nothing is scrubbed for buyer.
    Other/unattributed JSON is NEVER guessed: report an unresolved blocker.
    """
    if (type(organization_id) is not int or organization_id <= 0
            or type(store_id) is not int or store_id <= 0
            or (customer_ids is not None and (
                not isinstance(customer_ids, set)
                or any(type(cid) is not int or cid <= 0 for cid in customer_ids)
            ))):
        raise ShopifyLegacyAutomationPrivacyError("LEGACY_AUTOMATION_SCOPE_INVALID")
    now = now or datetime.utcnow()

    # Establish parent lineage before reading any body or writing mutations.
    owned = db.query(Automation).filter(
        Automation.organization_id == organization_id,
        Automation.store_id == store_id,
    ).with_for_update().limit(MAX_LEGACY_ROWS + 1).all()
    if len(owned) > MAX_LEGACY_ROWS:
        raise ShopifyLegacyAutomationPrivacyError("LEGACY_AUTOMATION_SCOPE_LIMIT")
    parent_ids = [row.id for row in owned]
    executions = db.query(AutomationExecution).filter(
        AutomationExecution.automation_id.in_(parent_ids),
        AutomationExecution.organization_id == organization_id,
    ).with_for_update().limit(MAX_LEGACY_ROWS + 1).all() if parent_ids else []
    if len(executions) > MAX_LEGACY_ROWS:
        raise ShopifyLegacyAutomationPrivacyError("LEGACY_AUTOMATION_SCOPE_LIMIT")
    execution_ids = [row.id for row in executions]
    provenance = db.query(AutomationExecutionProvenance).filter(
        AutomationExecutionProvenance.execution_id.in_(execution_ids),
    ).with_for_update().all() if execution_ids else []
    by_execution = {row.execution_id: row for row in provenance}

    # Any drift across organizations/shops is an integrity failure: never
    # scrub data from another store merely because the parent ID matches.
    for execution in executions:
        if execution.store_id not in (None, store_id):
            raise ShopifyLegacyAutomationPrivacyError("LEGACY_AUTOMATION_PARENT_STORE_DRIFT")
        prov = by_execution.get(execution.id)
        if prov and (prov.organization_id != organization_id
                     or prov.store_id not in (None, store_id)):
            raise ShopifyLegacyAutomationPrivacyError("LEGACY_AUTOMATION_PROVENANCE_DRIFT")

    # Organization-wide parent rules are shared. Event-specific store
    # selectors are insufficient to authorize wiping their template/rules
    # or all executions. Keep them for independent attribution review.
    shared_execution_count = int(
        db.query(AutomationExecution.id).join(
            Automation, AutomationExecution.automation_id == Automation.id,
        ).filter(
            Automation.organization_id == organization_id,
            Automation.store_id.is_(None),
            AutomationExecution.organization_id == organization_id,
            AutomationExecution.store_id == store_id,
        ).count()
    )

    selected = []
    unknown = 0
    for execution in executions:
        prov = by_execution.get(execution.id)
        if customer_ids is None:
            selected.append(execution)
        elif prov is None or prov.customer_id is None or prov.store_id != store_id:
            unknown += 1
        elif prov.customer_id in customer_ids:
            selected.append(execution)

    possible_inflight = sum(
        execution.status in ("running", "processing") for execution in selected
    )
    for execution in selected:
        execution.input_json = "{}"
        execution.result_json = "{}"
        execution.event_id = None
        execution.error_message = None
        if execution.status in _RUNNING:
            execution.status = "failed"
            execution.completed_at = now
        prov = by_execution.get(execution.id)
        if prov is not None:
            prov.customer_id = None
            prov.subject_linkage = "subject_link_erased"

    rules_scrubbed = 0
    if customer_ids is None:
        for rule in owned:
            rule.active = False
            rule.name = f"Redacted store automation {rule.id}"
            rule.description = None
            rule.conditions_json = "[]"
            rule.actions_json = "[]"
            rules_scrubbed += 1

    return {
        "legacy_execution_payloads_scrubbed": len(selected),
        "legacy_rules_scrubbed": rules_scrubbed,
        "legacy_possible_inflight_actions": possible_inflight,
        "legacy_unattributed_executions_for_review": unknown,
        "legacy_shared_parent_executions_for_review": shared_execution_count,
        "legacy_rules_with_unstructured_conditions_for_review": (
            0 if customer_ids is None else len(owned)
        ),
        "legacy_external_delivery_verified": False,
        "fulfillment_complete": False,
    }
