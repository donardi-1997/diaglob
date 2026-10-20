"""End-to-end managed Shopify install grant: synthetic API and SQLite only."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import httpx
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CommerceConnection, Organization, OrganizationMembership, ShopifyPendingInstall, Store,
    User,
)
from app.api.shopify_embedded import embedded_managed_installation_stage
from app.api.shopify import (
    ShopifyManagedClaimCode, managed_install_pending, managed_install_claim_code,
)
from app.services.shopify_managed_installation import (
    ManagedShopifyInstallationError, stage_managed_installation,
)

SHOP = "diaglob-poc.myshopify.com"
IDENTITY = {"shop": SHOP, "subject": "synthetic-shopify-merchant"}
ALL_SCOPES = "read_products,read_inventory,read_customers,read_orders,write_orders,write_draft_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders"


@pytest.fixture
def sandbox(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "fixture-secret")
    with Session(engine) as db:
        yield db
    engine.dispose()


def _stage(db, scope=ALL_SCOPES):
    with patch("app.services.shopify_managed_installation.httpx.Client") as client, patch(
        "app.services.shopify_managed_installation.ShopifyGraphQLClient"
    ) as graphql, patch(
        "app.services.shopify_managed_installation.encrypt_shopify_secret",
        side_effect=lambda x: "encrypted:" + x,
    ):
        client.return_value.__enter__.return_value.post.return_value.json.return_value = {
            "access_token": "fixture-online-exchanged-offline",
            "refresh_token": "fixture-rotating-refresh",
            "expires_in": 3600, "refresh_token_expires_in": 7776000,
            "scope": scope,
        }
        graphql.return_value.query.return_value = {"shop": {"myshopifyDomain": SHOP}}
        code = stage_managed_installation(db, identity=IDENTITY, id_token="fixture-jwt")
    return code


def test_managed_grant_expiring_encrypted_and_single_use(sandbox):
    grant = _stage(sandbox)
    assert grant["expires_in_seconds"] == 600
    row = sandbox.query(ShopifyPendingInstall).one()
    assert row.grant_method == "managed"
    assert row.state_used is True
    assert len(row.claim_hash) == 64
    assert grant["claim_code"] != row.claim_hash
    assert row.token_encrypted == "encrypted:fixture-online-exchanged-offline"
    assert row.refresh_token_encrypted == "encrypted:fixture-rotating-refresh"
    assert row.access_token_expires_at > datetime.utcnow() + timedelta(minutes=30)
    assert managed_install_pending(ShopifyManagedClaimCode(claim_code=grant["claim_code"]), membership=object(), db=sandbox) == {
        "pending": True, "shop_domain": SHOP,
    }
    assert managed_install_pending(ShopifyManagedClaimCode(claim_code="Z" * 45), membership=object(), db=sandbox)["pending"] is False


def test_missing_scopes_cannot_stage(sandbox):
    with pytest.raises(ManagedShopifyInstallationError, match="SCOPES_MISSING"):
        _stage(sandbox, scope="read_products")
    assert sandbox.query(ShopifyPendingInstall).count() == 0


def test_signed_session_required_before_staging(sandbox):
    with pytest.raises(HTTPException) as exc:
        embedded_managed_installation_stage(credentials=None, db=sandbox)
    assert exc.value.status_code == 401
    assert sandbox.query(ShopifyPendingInstall).count() == 0


def test_tenant_scoped_claim_replay_denied(sandbox):
    code = _stage(sandbox)["claim_code"]
    org = Organization(id=31, name="Synthetic", slug="managed-install-synthetic",
                       plan="trial", subscription_status="trial_pending",
                       billing_onboarding_channel="shopify_install")
    user = User(id=32, name="Fixture", email="synthetic-managed@example.invalid", active=True)
    member = OrganizationMembership(id=33, organization_id=31, user_id=32,
                                    role="admin", all_stores=True, active=True)
    store = Store(id=34, organization_id=31, name="Synthetic", slug="managed-install",
                  country_code="CO", currency="COP", timezone="America/Bogota",
                  active=True, deleted=False)
    sandbox.add_all([org, user, member, store])
    sandbox.commit()
    with patch("app.services.shopify_public_install.confirm_shopify_install_billing",
               return_value=False), patch(
        "app.services.shopify_public_install.ensure_shopify_order_webhooks",
        return_value={"ok": True},
    ):
        response = managed_install_claim_code(34, ShopifyManagedClaimCode(claim_code=code),
                                               membership=member, db=sandbox, store=store)
    assert response["connected"] is True
    connection = sandbox.query(CommerceConnection).one()
    assert connection.refresh_token_encrypted == "encrypted:fixture-rotating-refresh"
    assert connection.access_token_expires_at is not None
    grant = sandbox.query(ShopifyPendingInstall).one()
    assert grant.token_encrypted is None and grant.refresh_token_encrypted is None
    with pytest.raises(HTTPException):
        managed_install_claim_code(34, ShopifyManagedClaimCode(claim_code=code),
                                   membership=member, db=sandbox, store=store)


def test_expired_pending_code_fails_closed(sandbox):
    code = _stage(sandbox)["claim_code"]
    row = sandbox.query(ShopifyPendingInstall).one()
    row.claim_expires_at = datetime.utcnow() - timedelta(seconds=1)
    sandbox.commit()
    assert not managed_install_pending(ShopifyManagedClaimCode(claim_code=code),
                                       membership=object(), db=sandbox)["pending"]


@pytest.mark.parametrize("provider_error,expected", [
    ("invalid_client", "SHOPIFY_APP_CREDENTIALS_REJECTED"),
    ("invalid_subject_token", "SHOPIFY_SESSION_TOKEN_REJECTED"),
    ("invalid_grant", "SHOPIFY_TOKEN_GRANT_REJECTED"),
    ("invalid_scope", "SHOPIFY_REQUIRED_SCOPES_MISSING"),
    ("arbitrary-unrecognized-error", "SHOPIFY_TOKEN_EXCHANGE_REJECTED"),
])
def test_managed_stage_reports_only_sanitized_shopify_oauth_reason(
    sandbox, provider_error, expected,
):
    url = f"https://{SHOP}/admin/oauth/access_token"
    request = httpx.Request("POST", url)
    response = httpx.Response(
        400, json={
            "error": provider_error,
            "error_description": "SENSITIVE RESPONSE SHOULD NEVER BE RETURNED",
        }, request=request,
    )
    error = httpx.HTTPStatusError("sensitive response", request=request, response=response)
    with patch("app.services.shopify_managed_installation.httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value.raise_for_status.side_effect = error
        with pytest.raises(ManagedShopifyInstallationError, match=f"^{expected}$") as exc:
            stage_managed_installation(
                sandbox, identity=IDENTITY, id_token="synthetic-shopify-id-token",
            )
    assert "SENSITIVE" not in str(exc.value)
    assert sandbox.query(ShopifyPendingInstall).count() == 0


def test_managed_stage_api_exposes_safe_code_without_shopify_response_or_tokens(sandbox):
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="SYNTHETIC-SECRET")
    with patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY), patch(
        "app.api.shopify_embedded.stage_managed_installation",
        side_effect=ManagedShopifyInstallationError("SHOPIFY_APP_CREDENTIALS_REJECTED"),
    ):
        with pytest.raises(HTTPException) as exc:
            embedded_managed_installation_stage(credentials=bearer, db=sandbox)
    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "SHOPIFY_APP_CREDENTIALS_REJECTED"
    assert "SYNTHETIC-SECRET" not in str(exc.value.detail)


def test_managed_stage_api_unknown_error_does_not_leak_text(sandbox):
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="SYNTHETIC-SECRET")
    with patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY), patch(
        "app.api.shopify_embedded.stage_managed_installation",
        side_effect=ManagedShopifyInstallationError("danger: secret token from provider"),
    ):
        with pytest.raises(HTTPException) as exc:
            embedded_managed_installation_stage(credentials=bearer, db=sandbox)
    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "SHOPIFY_MANAGED_INSTALL_GRANT_FAILED"
    assert "secret token" not in str(exc.value.detail)
