"""Read-only merchant Copilot store-impact inventory for Shopify privacy review.

Merchant Copilot sessions belong to DIAGLOB users, not Shopify customers.
A Shopify buyer ID must never be inferred from chat text, email or phone.
This module counts records for the verified store only, WITHOUT fetching
their content, decrypting customer selectors, or treating them as buyer records.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..model_domains.ai_agent import (
    AgentActionApproval,
    AgentChatMessage,
    AgentChatSession,
    AgentChatToolCall,
)
from ..models import ShopifyPrivacyRequest
from .shopify_privacy_scope_preview import preview_shopify_privacy_scope


@dataclass(frozen=True)
class ShopifyCopilotPrivacyImpact:
    topic: str
    store_sessions_for_review: int
    store_messages_for_review: int
    store_tool_calls_for_review: int
    store_action_approvals_for_review: int
    customer_attribution: str = "unavailable_no_verified_customer_relationship"
    content_review_required: bool = True
    complete: bool = False
    # These are STORE-WIDE figures, never Shopify buyer-specific counts.
    # External AI/provider copies, content, logging and retention are uncovered.


def inspect_shopify_copilot_privacy_impact(
    db: Session,
    receipt: ShopifyPrivacyRequest,
) -> ShopifyCopilotPrivacyImpact:
    """Count *store-wide* merchant-Copilot metadata after shop verification.

    For customer events the counts mean "store content needing review", NOT
    content associated with the requested customer. For shop/redact they
    represent candidate store-owned resources requiring a lawful decision.
    No delete, export, message scan, payload read, or completion flag.
    """
    preview = preview_shopify_privacy_scope(db, receipt)
    org_id = receipt.organization_id
    store_id = receipt.store_id

    sessions = (
        db.query(func.count(AgentChatSession.id))
        .filter(
            AgentChatSession.organization_id == org_id,
            AgentChatSession.store_id == store_id,
        )
        .scalar()
    )
    messages = (
        db.query(func.count(AgentChatMessage.id))
        .select_from(AgentChatMessage)
        .join(
            AgentChatSession,
            AgentChatMessage.session_id == AgentChatSession.id,
        )
        .filter(
            AgentChatSession.organization_id == org_id,
            AgentChatSession.store_id == store_id,
        )
        .scalar()
    )
    tools = (
        db.query(func.count(AgentChatToolCall.id))
        .select_from(AgentChatToolCall)
        .join(
            AgentChatSession,
            AgentChatToolCall.session_id == AgentChatSession.id,
        )
        .filter(
            AgentChatSession.organization_id == org_id,
            AgentChatSession.store_id == store_id,
        )
        .scalar()
    )
    approvals = (
        db.query(func.count(AgentActionApproval.id))
        .filter(
            AgentActionApproval.organization_id == org_id,
            AgentActionApproval.store_id == store_id,
        )
        .scalar()
    )
    return ShopifyCopilotPrivacyImpact(
        topic=preview.topic,
        store_sessions_for_review=int(sessions or 0),
        store_messages_for_review=int(messages or 0),
        store_tool_calls_for_review=int(tools or 0),
        store_action_approvals_for_review=int(approvals or 0),
    )
