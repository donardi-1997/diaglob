"""Read-only Shopify privacy impact counts for *explicitly linked* automation rows.

This module does not export recipient content, inspect free text, mutate state,
or claim GDPR fulfillment. Attribution requires both original verified Shopify
shop/store provenance and the exact store-local external customer ID.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func
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
    CustomerStoreProfile,
    ShopifyPrivacyRequest,
)
from ..shopify_security import decrypt_shopify_secret
from .shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError,
    preview_shopify_privacy_scope,
)


MAX_SUBJECT_PROFILE_MATCHES = 250


@dataclass(frozen=True)
class ShopifyAutomationPrivacyImpact:
    topic: str
    attribution: str
    audience_members: int
    campaign_recipients: int
    delivery_attempts: int
    flow_recipients: int
    flow_node_executions: int
    complete: bool = False
    # This intentionally excludes orphan/non-recipient execution payloads,
    # merchant Copilot content, external WhatsApp/provider copies and backups.
    copilot_customer_attribution: str = "unavailable_no_customer_fk"
    legacy_automation_payload_coverage: str = "uncovered"
    external_processor_coverage: str = "uncovered"


def inspect_shopify_automation_privacy_impact(
    db: Session,
    receipt: ShopifyPrivacyRequest,
) -> ShopifyAutomationPrivacyImpact:
    """Count identifiable automation rows without reading customer payloads.

    Shopify customer requests require an exact external customer ID/profile
    for this particular store. Shop-redact requests encompass all recipients
    on the verified store. A merchant's Copilot session is not a customer's
    conversation and is never included by text/email/phone matching.
    """
    verified_scope = preview_shopify_privacy_scope(db, receipt)
    organization_id = receipt.organization_id
    store_id = receipt.store_id
    subject_ids: tuple[int, ...] | None = None

    if receipt.topic != "shop/redact":
        try:
            selectors = json.loads(
                decrypt_shopify_secret(receipt.selector_encrypted)
            )
            external_id = str(selectors["customer"]["id"]).strip()
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise ShopifyPrivacyScopeError(
                "SHOPIFY_AUTOMATION_SUBJECT_INVALID"
            ) from exc
        if not external_id:
            raise ShopifyPrivacyScopeError(
                "SHOPIFY_AUTOMATION_SUBJECT_INVALID"
            )
        profiles = (
            db.query(CustomerStoreProfile.customer_id)
            .filter(
                CustomerStoreProfile.organization_id == organization_id,
                CustomerStoreProfile.store_id == store_id,
                CustomerStoreProfile.external_customer_id == external_id,
            )
            .distinct()
            .limit(MAX_SUBJECT_PROFILE_MATCHES + 1)
            .all()
        )
        if len(profiles) > MAX_SUBJECT_PROFILE_MATCHES:
            raise ShopifyPrivacyScopeError(
                "SHOPIFY_AUTOMATION_SUBJECT_AMBIGUOUS"
            )
        subject_ids = tuple(sorted(row[0] for row in profiles))

    def count(query):
        return int(query.scalar() or 0)

    # The same customer may be registered in other stores/organizations.
    # Joins through a campaign/run or flow run are mandatory; a customer_id
    # alone is never sufficient to grant ownership of a recipient record.
    audience = (
        db.query(func.count(AutomationAudienceMember.id))
        .select_from(AutomationAudienceMember)
        .join(
            AutomationCampaign,
            AutomationAudienceMember.automation_id == AutomationCampaign.id,
        )
        .filter(
            AutomationCampaign.organization_id == organization_id,
            AutomationCampaign.store_id == store_id,
        )
    )
    recipients = (
        db.query(func.count(AutomationRecipientExecution.id))
        .select_from(AutomationRecipientExecution)
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationRun.organization_id == organization_id,
            AutomationCampaign.organization_id == organization_id,
            AutomationCampaign.store_id == store_id,
        )
    )
    deliveries = (
        db.query(func.count(AutomationDeliveryAttempt.id))
        .select_from(AutomationDeliveryAttempt)
        .join(
            AutomationRecipientExecution,
            AutomationDeliveryAttempt.recipient_execution_id
            == AutomationRecipientExecution.id,
        )
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationRun.organization_id == organization_id,
            AutomationCampaign.organization_id == organization_id,
            AutomationCampaign.store_id == store_id,
        )
    )
    flow_recipients = (
        db.query(func.count(AutomationFlowRecipientExecution.id))
        .select_from(AutomationFlowRecipientExecution)
        .join(
            AutomationFlowRun,
            AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id,
        )
        .filter(
            AutomationFlowRun.organization_id == organization_id,
            AutomationFlowRun.store_id == store_id,
            AutomationFlowRecipientExecution.organization_id == organization_id,
        )
    )
    nodes = (
        db.query(func.count(AutomationNodeExecution.id))
        .select_from(AutomationNodeExecution)
        .join(
            AutomationFlowRecipientExecution,
            AutomationNodeExecution.flow_recipient_execution_id
            == AutomationFlowRecipientExecution.id,
        )
        .join(
            AutomationFlowRun,
            AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id,
        )
        .filter(
            AutomationFlowRun.organization_id == organization_id,
            AutomationFlowRun.store_id == store_id,
            AutomationFlowRecipientExecution.organization_id == organization_id,
        )
    )
    if subject_ids is not None:
        audience = audience.filter(
            AutomationAudienceMember.customer_id.in_(subject_ids)
        )
        recipients = recipients.filter(
            AutomationRecipientExecution.customer_id.in_(subject_ids)
        )
        deliveries = deliveries.filter(
            AutomationRecipientExecution.customer_id.in_(subject_ids)
        )
        flow_recipients = flow_recipients.filter(
            AutomationFlowRecipientExecution.customer_id.in_(subject_ids)
        )
        nodes = nodes.filter(
            AutomationFlowRecipientExecution.customer_id.in_(subject_ids)
        )

    return ShopifyAutomationPrivacyImpact(
        topic=verified_scope.topic,
        attribution=(
            "verified_store_scope"
            if receipt.topic == "shop/redact"
            else (
                "verified_external_customer_id"
                if subject_ids else "subject_unresolved"
            )
        ),
        audience_members=count(audience),
        campaign_recipients=count(recipients),
        delivery_attempts=count(deliveries),
        flow_recipients=count(flow_recipients),
        flow_node_executions=count(nodes),
    )
