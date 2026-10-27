"""Billing-channel policy shared by authenticated billing operations."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization
from ..model_domains.paddle_billing import PaddleBillingSubscription


def paddle_migration_cancellation_verified(db: Session, organization: Organization) -> bool:
    """Require Paddle's tenant-bound mirror to confirm final cancellation."""
    subscription_id = getattr(organization, "billing_subscription_id", None)
    customer_id = getattr(organization, "billing_customer_id", None)
    if (
        getattr(organization, "subscription_status", None) != "canceled"
        or bool(getattr(organization, "auto_renew_enabled", True))
        or not subscription_id or not customer_id
    ):
        return False
    subscription = db.get(PaddleBillingSubscription, subscription_id)
    return bool(
        subscription
        and subscription.status == "canceled"
        and subscription.organization_id == getattr(organization, "id", None)
        and subscription.customer_id == customer_id
    )


def external_app_billing_block_reason(
    db: Session,
    organization: Organization,
) -> str | None:
    """Return why Paddle cannot be used for this organization, if applicable.

    Shopify installation provenance is checked first. For legacy/direct
    signups, any Shopify connection not explicitly revoked makes this a
    Shopify-integrated organization and requires Shopify App Pricing for app
    subscription charges.
    """
    provider = (getattr(organization, "billing_provider", None) or "").strip().lower()
    if provider == "shopify":
        return "SHOPIFY_MANAGED_BILLING"
    if getattr(organization, "billing_onboarding_channel", None) == "shopify_install":
        return "SHOPIFY_INSTALL_BILLING_PENDING"

    organization_id = getattr(organization, "id", None)
    if type(organization_id) is not int or organization_id < 1:
        return None

    connection = (
        db.query(CommerceConnection.id)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status != "revoked",
        )
        .first()
    )
    return "SHOPIFY_APP_PRICING_REQUIRED" if connection is not None else None
