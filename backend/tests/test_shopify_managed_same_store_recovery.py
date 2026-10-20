"""Shopify managed same-store credential recovery; synthetic grant and tenant only."""
from datetime import datetime
from unittest.mock import patch

import pytest

from app.models import CommerceConnection, Organization, Store, User, OrganizationMembership
from app.services.shopify_service import ShopifyConnectionError
from app.services.shopify_public_install import claim_install
from test_shopify_managed_onboarding import _stage, sandbox


def _fixture(db, *, shop="diaglob-poc.myshopify.com", status="error"):
    org = Organization(
        id=251, name="Existing DIAGLOB merchant", slug="existing-diaglob-merchant",
        plan="pro", subscription_status="active", billing_provider="paddle",
        billing_customer_id="synthetic-paddle-customer",
        billing_subscription_id="synthetic-paddle-subscription",
    )
    user = User(id=252, name="Synthetic Admin", email="managed-recovery@example.invalid", active=True)
    member = OrganizationMembership(
        id=253, organization_id=251, user_id=252, role="admin", all_stores=True, active=True,
    )
    store = Store(
        id=254, organization_id=251, name="Diaglob Colombia", slug="diaglob-colombia-recovery",
        country_code="CO", currency="COP", timezone="America/Bogota",
        shopify_domain=shop, active=True, deleted=False,
    )
    connection = CommerceConnection(
        id=255, organization_id=251, store_id=254, provider="shopify",
        external_store_url=shop, access_token_encrypted="old-encrypted-synthetic",
        status=status, connected_at=datetime.utcnow(), scopes="read_products",
        last_error="SHOPIFY_REAUTH_REQUIRED",
    )
    db.add_all((org, user, member, store, connection))
    db.commit()
    return org, member, store, connection


def test_paddle_billed_shopify_store_can_recover_same_managed_connection_without_billing_change(sandbox):
    code = _stage(sandbox)["claim_code"]
    org, member, store, connection = _fixture(sandbox)
    old_connection_id = connection.id
    old_billing = (org.plan, org.billing_provider, org.billing_customer_id,
                   org.billing_subscription_id, org.subscription_status)
    with patch("app.services.shopify_public_install.confirm_shopify_install_billing") as billing, patch(
        "app.services.shopify_public_install.ensure_shopify_order_webhooks",
        return_value={"ok": True},
    ) as ensure:
        result = claim_install(sandbox, secret=code, membership=member, store=store)
    assert result["connected"] is True
    sandbox.refresh(connection)
    sandbox.refresh(org)
    assert connection.id == old_connection_id
    assert connection.status == "connected"
    assert connection.last_error is None
    assert connection.access_token_encrypted == "encrypted:fixture-online-exchanged-offline"
    assert connection.refresh_token_encrypted == "encrypted:fixture-rotating-refresh"
    assert sandbox.query(CommerceConnection).count() == 1
    assert (org.plan, org.billing_provider, org.billing_customer_id,
            org.billing_subscription_id, org.subscription_status) == old_billing
    billing.assert_not_called()
    ensure.assert_called_once()
    with pytest.raises(Exception, match="EXPIRED"):
        claim_install(sandbox, secret=code, membership=member, store=store)


def test_failed_connection_cannot_recover_different_shop_or_tenant(sandbox):
    code = _stage(sandbox)["claim_code"]
    _, member, store, connection = _fixture(sandbox, shop="another.myshopify.com")
    with pytest.raises(ShopifyConnectionError, match="SHOPIFY_STORE_DOMAIN_MISMATCH|SHOPIFY_STORE_ALREADY_CONNECTED"):
        claim_install(sandbox, secret=code, membership=member, store=store)
    sandbox.rollback()
    assert connection.status == "error"
    assert connection.access_token_encrypted == "old-encrypted-synthetic"


def test_error_connection_cannot_bypass_store_billing_check_with_unbound_grant(sandbox):
    # Only the verified Shopify-managed grant from an authenticated Admin
    # session can bypass new-install billing eligibility for the same shop.
    code = _stage(sandbox)["claim_code"]
    _, member, store, connection = _fixture(sandbox)
    grant = sandbox.query(__import__("app.models", fromlist=["ShopifyPendingInstall"]).ShopifyPendingInstall).one()
    grant.grant_method = "oauth"
    sandbox.commit()
    with pytest.raises(ShopifyConnectionError, match="SHOPIFY_BILLING_ORGANIZATION_REQUIRED"):
        claim_install(sandbox, secret=code, membership=member, store=store)
    sandbox.rollback()
    assert connection.status == "error"


def test_revoked_connection_not_automatically_resurrected_for_paddle_tenant(sandbox):
    code = _stage(sandbox)["claim_code"]
    _, member, store, connection = _fixture(sandbox, status="revoked")
    with pytest.raises(ShopifyConnectionError, match="SHOPIFY_BILLING_ORGANIZATION_REQUIRED"):
        claim_install(sandbox, secret=code, membership=member, store=store)
    sandbox.rollback()
    assert connection.status == "revoked"
