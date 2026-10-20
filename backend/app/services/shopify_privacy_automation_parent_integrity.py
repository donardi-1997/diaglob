"""Fail-closed automation parent-key integrity checks for Shopify privacy.

Count only IDs, never message bodies or provider payloads. Verify tenant, store
and flow-version lineage before accepting a scoped recipient count/extraction.
"""
from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import (
    AutomationCampaign, AutomationFlow, AutomationFlowRecipientExecution,
    AutomationFlowRun, AutomationFlowVersion, AutomationRecipientExecution,
    AutomationRun,
)
from .shopify_privacy_scope_preview import ShopifyPrivacyScopeError


def verify_automation_parent_lineage(
    db: Session, *, organization_id: int, store_id: int,
    subject_ids: tuple[int, ...] | None,
) -> None:
    """Block mismatched in-scope campaign/flow records rather than omit them."""
    campaign = (
        db.query(AutomationRecipientExecution.id)
        .join(AutomationRun, AutomationRecipientExecution.run_id == AutomationRun.id)
        .join(AutomationCampaign, AutomationRun.automation_id == AutomationCampaign.id)
        .filter(
            AutomationCampaign.organization_id == organization_id,
            AutomationCampaign.store_id == store_id,
            AutomationRun.organization_id != organization_id,
        )
    )
    if subject_ids is not None:
        campaign = campaign.filter(
            AutomationRecipientExecution.customer_id.in_(subject_ids),
        )
    if campaign.first() is not None:
        raise ShopifyPrivacyScopeError("AUTOMATION_CAMPAIGN_PARENT_TENANCY_MISMATCH")

    # Scan by parent OR execution scope. Inconsistent runs must not disappear
    # merely because the filtering path omitted a corrupted relation.
    flow = (
        db.query(AutomationFlowRecipientExecution.id)
        .join(
            AutomationFlowRun,
            AutomationFlowRecipientExecution.flow_run_id == AutomationFlowRun.id,
        )
        .join(AutomationFlow, AutomationFlowRun.flow_id == AutomationFlow.id)
        .outerjoin(
            AutomationFlowVersion,
            AutomationFlowRun.flow_version_id == AutomationFlowVersion.id,
        )
        .filter(
            or_(
                and_(
                    AutomationFlow.organization_id == organization_id,
                    AutomationFlow.store_id == store_id,
                ),
                and_(
                    AutomationFlowRun.organization_id == organization_id,
                    AutomationFlowRun.store_id == store_id,
                ),
            ),
            or_(
                AutomationFlowRun.organization_id != AutomationFlow.organization_id,
                AutomationFlowRun.store_id != AutomationFlow.store_id,
                AutomationFlowVersion.id.is_(None),
                AutomationFlowVersion.flow_id != AutomationFlowRun.flow_id,
                AutomationFlowVersion.organization_id != AutomationFlowRun.organization_id,
                AutomationFlowRecipientExecution.organization_id
                != AutomationFlowRun.organization_id,
                AutomationFlowRecipientExecution.flow_version_id
                != AutomationFlowRun.flow_version_id,
            ),
        )
    )
    if subject_ids is not None:
        flow = flow.filter(
            AutomationFlowRecipientExecution.customer_id.in_(subject_ids),
        )
    if flow.first() is not None:
        raise ShopifyPrivacyScopeError("AUTOMATION_FLOW_PARENT_PROVENANCE_MISMATCH")
