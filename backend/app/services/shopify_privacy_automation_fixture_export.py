"""Encrypted automation privacy extraction for disposable SQLite fixtures ONLY.

No FastAPI route, background worker, storage or production invocation. This
extractor proves exact Shopify store/customer joins and reconciles row counts
to the existing read-only provenance audit; it is NEVER GDPR fulfillment.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..models import (
    AutomationAudienceMember, AutomationCampaign, AutomationDeliveryAttempt,
    AutomationFlowRecipientExecution, AutomationFlowRun, AutomationNodeExecution,
    AutomationRecipientExecution, AutomationRun, CustomerStoreProfile,
)
from .shopify_privacy_automation_provenance import (
    inspect_shopify_automation_privacy_impact,
)
from .shopify_privacy_local_processor import (
    ShopifyLocalPrivacyError, _receipt, _selectors,
)
from .shopify_privacy_scope_preview import ShopifyPrivacyScopeError
from .shopify_privacy_scoped_extraction import (
    ShopifyPrivacyExtractionError, _require_in_memory_fixture,
)

_MAX_ROWS = 250
_MAX_PLAINTEXT_BYTES = 1_000_000


@dataclass(frozen=True)
class EncryptedShopifyAutomationFixture:
    request_id: str
    ciphertext: bytes = field(repr=False)
    sha256: str
    source_counts: dict[str, int]
    fixture_only: bool = True
    delivery_authorized: bool = False
    fulfillment_complete: bool = False


def _rows(query, name: str):
    rows = query.limit(_MAX_ROWS + 1).all()
    if len(rows) > _MAX_ROWS:
        raise ShopifyPrivacyExtractionError("AUTOMATION_EXPORT_ROW_LIMIT")
    return rows


def build_encrypted_shopify_automation_fixture(
    db: Session, *, request_id: str, encryption_key: bytes,
    fixture_authorized: bool = False,
) -> EncryptedShopifyAutomationFixture:
    """Exercise customer-scoped automation joins, never on production DBs.

    Signed receipt, current shop identity and an exact one-to-one Shopify
    customer/profile link are required. It is unsafe to match by email/phone.
    Campaign recipient records belong to their original shop, even if the
    global Customer is shared with another store. Never export a campaign
    template, flow trigger context or organization-level customer details.
    """
    if fixture_authorized is not True:
        raise ShopifyPrivacyExtractionError("LIVE_AUTOMATION_EXPORT_DISABLED")
    _require_in_memory_fixture(db)
    try:
        cipher = Fernet(encryption_key)
    except (TypeError, ValueError) as exc:
        raise ShopifyPrivacyExtractionError("INVALID_EXPORT_ENCRYPTION_KEY") from exc
    try:
        receipt = _receipt(db, request_id)
        if (
            receipt.topic != "customers/data_request"
            or receipt.completed_at is not None
            or receipt.status == "completed"
        ):
            raise ShopifyPrivacyExtractionError("CUSTOMER_EXPORT_SCOPE_REQUIRED")
        selector = _selectors(receipt)
        customer = selector.get("customer")
        if not isinstance(customer, dict) or customer.get("id") is None:
            raise ShopifyPrivacyExtractionError("EXACT_CUSTOMER_ID_REQUIRED")
        external_id = str(customer["id"]).strip()
        if not external_id:
            raise ShopifyPrivacyExtractionError("EXACT_CUSTOMER_ID_REQUIRED")
        org, shop = receipt.organization_id, receipt.store_id
        identities = (
            db.query(CustomerStoreProfile.customer_id)
            .filter(
                CustomerStoreProfile.organization_id == org,
                CustomerStoreProfile.store_id == shop,
                CustomerStoreProfile.external_customer_id == external_id,
            ).limit(2).all()
        )
        if len(identities) != 1 or identities[0][0] is None:
            raise ShopifyPrivacyExtractionError("AUTOMATION_SUBJECT_AMBIGUOUS")
        subject_id = identities[0][0]
        impact = inspect_shopify_automation_privacy_impact(db, receipt)
    except (ShopifyPrivacyScopeError, ShopifyLocalPrivacyError) as exc:
        raise ShopifyPrivacyExtractionError("AUTOMATION_SCOPE_UNVERIFIED") from exc
    if impact.attribution != "verified_external_customer_id":
        raise ShopifyPrivacyExtractionError("AUTOMATION_SUBJECT_AMBIGUOUS")

    audience = _rows(
        db.query(AutomationAudienceMember).join(
            AutomationCampaign,
            AutomationAudienceMember.automation_id == AutomationCampaign.id,
        ).filter(
            AutomationCampaign.organization_id == org,
            AutomationCampaign.store_id == shop,
            AutomationAudienceMember.customer_id == subject_id,
        ).order_by(AutomationAudienceMember.id), "audience",
    )
    recipients_query = (
        db.query(AutomationRecipientExecution)
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationRun.organization_id == org,
            AutomationCampaign.organization_id == org,
            AutomationCampaign.store_id == shop,
            AutomationRecipientExecution.customer_id == subject_id,
        )
    )
    recipients = _rows(
        recipients_query.order_by(AutomationRecipientExecution.id), "recipients",
    )
    attempts = _rows(
        db.query(AutomationDeliveryAttempt)
        .join(
            AutomationRecipientExecution,
            AutomationDeliveryAttempt.recipient_execution_id
            == AutomationRecipientExecution.id,
        )
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationRun.organization_id == org,
            AutomationCampaign.organization_id == org,
            AutomationCampaign.store_id == shop,
            AutomationRecipientExecution.customer_id == subject_id,
        ).order_by(AutomationDeliveryAttempt.id), "delivery_attempts",
    )
    flow_recipients = _rows(
        db.query(AutomationFlowRecipientExecution)
        .join(
            AutomationFlowRun,
            AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id,
        )
        .filter(
            AutomationFlowRun.organization_id == org,
            AutomationFlowRun.store_id == shop,
            AutomationFlowRecipientExecution.organization_id == org,
            AutomationFlowRecipientExecution.customer_id == subject_id,
        ).order_by(AutomationFlowRecipientExecution.id), "flow_recipients",
    )
    nodes = _rows(
        db.query(AutomationNodeExecution)
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
            AutomationFlowRun.organization_id == org,
            AutomationFlowRun.store_id == shop,
            AutomationFlowRecipientExecution.organization_id == org,
            AutomationFlowRecipientExecution.customer_id == subject_id,
        ).order_by(AutomationNodeExecution.id), "node_executions",
    )
    source_counts = {
        "audience_members": len(audience),
        "campaign_recipients": len(recipients),
        "delivery_attempts": len(attempts),
        "flow_recipients": len(flow_recipients),
        "flow_node_executions": len(nodes),
    }
    expected = {
        name: getattr(impact, name)
        for name in source_counts
    }
    if source_counts != expected:
        raise ShopifyPrivacyExtractionError("AUTOMATION_EXPORT_SCOPE_CHANGED")

    # Project only buyer-linked recipient/attempt content, not campaign/flow
    # definitions, which are merchant-wide and can contain other subjects.
    payload = {
        "schema": "diaglob.shopify.automation_fixture_export.v1",
        "request_id": request_id,
        "fixture_only": True,
        "complete": False,
        "coverage": "explicitly_linked_rows_only",
        "sources": {
            "audience_members": [
                {"included": row.included} for row in audience
            ],
            "campaign_recipients": [
                {"status": row.status, "rendered_message": row.rendered_message,
                 "template_data": row.template_data,
                 "provider_message_id": row.provider_message_id}
                for row in recipients
            ],
            "delivery_attempts": [
                {"status": row.status, "provider_message_id": row.provider_message_id,
                 "error_message": row.error_message}
                for row in attempts
            ],
            "flow_recipients": [
                {"status": row.status, "error_message": row.error_message}
                for row in flow_recipients
            ],
            "flow_node_executions": [
                {"status": row.status, "node_type": row.node_type,
                 "provider_message_id": row.provider_message_id,
                 "error_message": row.error_message,
                 "extra_data": row.extra_data}
                for row in nodes
            ],
        },
    }
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(raw) > _MAX_PLAINTEXT_BYTES:
        raise ShopifyPrivacyExtractionError("AUTOMATION_EXPORT_PAYLOAD_LIMIT")
    sealed = cipher.encrypt(raw)
    return EncryptedShopifyAutomationFixture(
        request_id=request_id,
        ciphertext=sealed,
        sha256=hashlib.sha256(sealed).hexdigest(),
        source_counts=source_counts,
    )
