"""Export customer-linked automation records for a Shopify access request.

Only rows joined through the verified store's campaign/run or flow/run lineage
are returned. Shared run context, merchant-authored templates, Copilot content,
legacy automation payloads and provider-side copies remain outside this export.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (
    AutomationAudienceMember,
    AutomationCampaign,
    AutomationDeliveryAttempt,
    AutomationFlowRecipientExecution,
    AutomationFlowRun,
    AutomationNodeExecution,
    AutomationRecipientExecution,
    AutomationRun,
    ShopifyPrivacyRequest,
)
from .shopify_privacy_automation_provenance import (
    inspect_shopify_automation_privacy_impact,
)

MAX_EXPORT_ROWS_PER_TABLE = 250


class ShopifyAutomationExportError(ValueError):
    """Fail-closed automation export error containing no personal data."""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _limited(query, table: str):
    rows = query.limit(MAX_EXPORT_ROWS_PER_TABLE + 1).all()
    if len(rows) > MAX_EXPORT_ROWS_PER_TABLE:
        raise ShopifyAutomationExportError(f"AUTOMATION_EXPORT_{table.upper()}_LIMIT")
    return rows


def export_linked_automation_records(
    db: Session, *, receipt: ShopifyPrivacyRequest, customer_id: int,
) -> dict:
    """Return all bounded automation rows explicitly linked to this subject.

    The independent impact counter verifies shop and subject provenance and
    parent lineage before any payload-bearing columns are selected. Counts are
    compared after extraction so concurrent or incomplete reads fail closed.
    """
    impact = inspect_shopify_automation_privacy_impact(db, receipt)
    if impact.attribution != "verified_external_customer_id":
        raise ShopifyAutomationExportError("AUTOMATION_EXPORT_SUBJECT_UNVERIFIED")

    org, store = receipt.organization_id, receipt.store_id
    audience = _limited(
        db.query(AutomationAudienceMember)
        .join(AutomationCampaign, AutomationAudienceMember.automation_id == AutomationCampaign.id)
        .filter(
            AutomationCampaign.organization_id == org,
            AutomationCampaign.store_id == store,
            AutomationAudienceMember.customer_id == customer_id,
        )
        .order_by(AutomationAudienceMember.id),
        "audience_members",
    )
    recipients = _limited(
        db.query(AutomationRecipientExecution)
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationRun.organization_id == org,
            AutomationCampaign.organization_id == org,
            AutomationCampaign.store_id == store,
            AutomationRecipientExecution.customer_id == customer_id,
        )
        .order_by(AutomationRecipientExecution.id),
        "campaign_recipients",
    )
    recipient_ids = [row.id for row in recipients]
    deliveries = _limited(
        db.query(AutomationDeliveryAttempt)
        .filter(AutomationDeliveryAttempt.recipient_execution_id.in_(recipient_ids))
        .order_by(AutomationDeliveryAttempt.id),
        "delivery_attempts",
    ) if recipient_ids else []
    flow_recipients = _limited(
        db.query(AutomationFlowRecipientExecution)
        .join(AutomationFlowRun, AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id)
        .filter(
            AutomationFlowRun.organization_id == org,
            AutomationFlowRun.store_id == store,
            AutomationFlowRecipientExecution.organization_id == org,
            AutomationFlowRecipientExecution.customer_id == customer_id,
        )
        .order_by(AutomationFlowRecipientExecution.id),
        "flow_recipients",
    )
    flow_recipient_ids = [row.id for row in flow_recipients]
    nodes = _limited(
        db.query(AutomationNodeExecution)
        .filter(AutomationNodeExecution.flow_recipient_execution_id.in_(flow_recipient_ids))
        .order_by(AutomationNodeExecution.id),
        "flow_node_executions",
    ) if flow_recipient_ids else []

    actual = (
        len(audience), len(recipients), len(deliveries),
        len(flow_recipients), len(nodes),
    )
    expected = (
        impact.audience_members, impact.campaign_recipients, impact.delivery_attempts,
        impact.flow_recipients, impact.flow_node_executions,
    )
    if actual != expected:
        raise ShopifyAutomationExportError("AUTOMATION_EXPORT_COUNT_MISMATCH")

    return {
        "coverage": "linked_rows_included_field_review_pending",
        "audience_members": [{
            "included": row.included,
            "created_at": _iso(row.created_at),
        } for row in audience],
        "campaign_recipients": [{
            "status": row.status,
            "exclusion_reason": row.exclusion_reason,
            "rendered_message": row.rendered_message,
            "sent_at": _iso(row.sent_at),
            "attempt_count": row.attempt_count,
            "next_attempt_at": _iso(row.next_attempt_at),
            "provider_message_id": row.provider_message_id,
            "error_code": row.error_code,
            "error_detail_present": row.error_message is not None,
            "template_data": row.template_data,
        } for row in recipients],
        "delivery_attempts": [{
            "attempt_number": row.attempt_number,
            "status": row.status,
            "provider_message_id": row.provider_message_id,
            "error_code": row.error_code,
            "error_detail_present": row.error_message is not None,
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
        } for row in deliveries],
        "flow_recipients": [{
            "status": row.status,
            "current_node_id": row.current_node_id,
            "next_action_at": _iso(row.next_action_at),
            "attempt_count": row.attempt_count,
            "error_code": row.error_code,
            "error_detail_present": row.error_message is not None,
            "started_at": _iso(row.started_at),
            "completed_at": _iso(row.completed_at),
            "created_at": _iso(row.created_at),
        } for row in flow_recipients],
        "flow_node_executions": [{
            "node_id": row.node_id,
            "node_type": row.node_type,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "outcome": row.outcome,
            "provider_message_id": row.provider_message_id,
            "error_code": row.error_code,
            "error_detail_present": row.error_message is not None,
            "extra_data": row.extra_data,
            "started_at": _iso(row.started_at),
            "completed_at": _iso(row.completed_at),
        } for row in nodes],
        "not_covered": [
            "shared_run_context",
            "merchant_authored_templates",
            "merchant_copilot_content",
            "legacy_automation_payloads",
            "provider_side_copies",
            "provider_error_detail_content",
        ],
    }
