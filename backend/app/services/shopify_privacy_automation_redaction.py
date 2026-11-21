"""Scoped scrub of automation recipient payloads during permitted Shopify redaction.

Never infer ownership from Customer.id alone: campaign/run and flow-run store
provenance is mandatory. No commits or external-provider calls here. This
service is invoked by the permitted local redaction transaction before
CustomerStoreProfile links are removed.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (
    AutomationAudienceMember, AutomationCampaign, AutomationDeliveryAttempt,
    AutomationFlowRecipientExecution, AutomationFlowRun, AutomationNodeExecution,
    AutomationRecipientExecution, AutomationRun,
)

_CAMPAIGN_PENDING = frozenset(("queued", "retry_wait", "processing", "sending"))
_FLOW_PENDING = frozenset(("active", "waiting"))


def scrub_shopify_automation_scope(
    db: Session, *, organization_id: int, store_id: int,
    customer_ids: set[int] | None, now: datetime | None = None,
) -> dict:
    """Scrub only the verified store, optionally its exact local customers.

    customer_ids=None means shop/redact, all rows for the authorized shop.
    customer_ids=set() means no matched buyers: do NOT select all recipients.
    Caller must have verified signed Shopify scope, legal permit and restore
    checkpoint, and must commit atomically with the local SQL redaction.
    """
    if (type(organization_id) is not int or organization_id <= 0
            or type(store_id) is not int or store_id <= 0
            or customer_ids is not None and (
                not isinstance(customer_ids, set)
                or any(type(x) is not int or x <= 0 for x in customer_ids)
            )):
        raise ValueError("PRIVACY_AUTOMATION_SCOPE_INVALID")
    now = now or datetime.utcnow()
    report = {
        "audience_members_removed": 0,
        "campaign_recipients_scrubbed": 0,
        "campaign_attempts_scrubbed": 0,
        "flow_recipients_scrubbed": 0,
        "flow_nodes_scrubbed": 0,
        "flow_contexts_scrubbed": 0,
        "mixed_recipient_contexts_unverified": 0,
        "possible_inflight_deliveries": 0,
        "provider_handles_pending_external_erasure": 0,
        "provider_erasure_verified": False,
        "fulfillment_complete": False,
    }

    campaign_scope = (
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
        AutomationRun.organization_id == organization_id,
    )
    audience = db.query(AutomationAudienceMember).join(
        AutomationCampaign, AutomationAudienceMember.automation_id == AutomationCampaign.id,
    ).filter(
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
    )
    recipients = db.query(AutomationRecipientExecution).join(
        AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id,
    ).join(
        AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id,
    ).filter(*campaign_scope)
    if customer_ids is not None:
        audience = audience.filter(AutomationAudienceMember.customer_id.in_(customer_ids))
        recipients = recipients.filter(AutomationRecipientExecution.customer_id.in_(customer_ids))

    # Scrub snapshots and free-text errors. Preserve minimal opaque provider
    # delivery handles until the external provider acknowledges deletion;
    # otherwise DIAGLOB would lose the only handle needed to request erasure.
    # Handles remain a separate external-processor closure blocker.
    selected = recipients.with_for_update(of=AutomationRecipientExecution).all()
    selected_ids = [r.id for r in selected]
    if selected_ids:
        attempts = db.query(AutomationDeliveryAttempt).filter(
            AutomationDeliveryAttempt.recipient_execution_id.in_(selected_ids),
        ).with_for_update().all()
        for attempt in attempts:
            if attempt.provider_message_id:
                report["provider_handles_pending_external_erasure"] += 1
            attempt.error_message = None
        report["campaign_attempts_scrubbed"] = len(attempts)
    for recipient in selected:
        if recipient.status in _CAMPAIGN_PENDING:
            if recipient.status in ("sending", "processing"):
                report["possible_inflight_deliveries"] += 1
            recipient.status = "ambiguous" if recipient.status == "sending" else "skipped"
            recipient.exclusion_reason = "privacy_suppressed"
        recipient.rendered_message = None
        recipient.template_data = {}
        recipient.error_message = None
        if recipient.provider_message_id:
            report["provider_handles_pending_external_erasure"] += 1
        recipient.next_attempt_at = None
        recipient.claimed_at = None
        recipient.lease_expires_at = None
    report["campaign_recipients_scrubbed"] = len(selected)

    # Fixed campaign audiences are linked to a specific campaign store.
    # Never delete a shared customer object or another campaign membership.
    members = audience.with_for_update(of=AutomationAudienceMember).all()
    for member in members:
        db.delete(member)
    report["audience_members_removed"] = len(members)

    flows = db.query(AutomationFlowRecipientExecution).join(
        AutomationFlowRun,
        AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id,
    ).filter(
        AutomationFlowRun.organization_id == organization_id,
        AutomationFlowRun.store_id == store_id,
        AutomationFlowRecipientExecution.organization_id == organization_id,
    )
    if customer_ids is not None:
        flows = flows.filter(AutomationFlowRecipientExecution.customer_id.in_(customer_ids))
    selected_flows = flows.with_for_update(of=AutomationFlowRecipientExecution).all()
    flow_recipient_ids = [r.id for r in selected_flows]
    for recipient in selected_flows:
        if recipient.claim_token is not None:
            report["possible_inflight_deliveries"] += 1
        if recipient.status in _FLOW_PENDING:
            recipient.status = "failed"
            recipient.error_code = "privacy_suppressed"
            recipient.completed_at = now
        recipient.current_node_id = None
        recipient.error_message = None
        recipient.claim_token = None
        recipient.claim_expires_at = None
        recipient.next_action_at = None
    report["flow_recipients_scrubbed"] = len(selected_flows)
    if flow_recipient_ids:
        nodes = db.query(AutomationNodeExecution).filter(
            AutomationNodeExecution.flow_recipient_execution_id.in_(flow_recipient_ids),
        ).with_for_update().all()
        for node in nodes:
            node.extra_data = None
            node.error_message = None
            if node.provider_message_id:
                report["provider_handles_pending_external_erasure"] += 1
        report["flow_nodes_scrubbed"] = len(nodes)

    # A flow run's trigger_context can be shared by multiple customers. For
    # customers/redact clear only if the run has no non-target recipients.
    # An ambiguous shared context remains an explicit closure blocker.
    flow_runs = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.organization_id == organization_id,
        AutomationFlowRun.store_id == store_id,
    ).with_for_update().all()
    for run in flow_runs:
        if run.trigger_context is None:
            continue
        if customer_ids is None:
            run.trigger_context = None
            report["flow_contexts_scrubbed"] += 1
            continue
        related = db.query(AutomationFlowRecipientExecution.customer_id).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id,
            AutomationFlowRecipientExecution.organization_id == organization_id,
        ).all()
        all_customers = {x[0] for x in related}
        if all_customers and not all_customers.isdisjoint(customer_ids):
            if all_customers.issubset(customer_ids):
                run.trigger_context = None
                report["flow_contexts_scrubbed"] += 1
            else:
                report["mixed_recipient_contexts_unverified"] += 1

    return report
