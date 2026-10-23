"""HTTP journey tests: signup -> billing -> verified Shopify-managed claim.

These are provider-SIMULATED API E2E tests. They run actual FastAPI routing,
persistence and HMAC verification without a paid Paddle checkout or live
Shopify Admin/Partner calls. They do NOT certify external merchant E2E.
"""
from datetime import datetime, timedelta
import hashlib
import secrets
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    CommerceConnection, Organization, OrganizationMembership,
    ShopifyOAuthState, ShopifyPendingInstall, Store, User,
)

SHOP = "diaglob-poc.myshopify.com"
SECRET = "synthetic-app-secret-not-for-production"


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "diaglob_signup_e2e.sqlite3")
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setenv(
        "SHOPIFY_REDIRECT_URI", "https://api.diaglob.tech/api/shopify/callback"
    )
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    with Session(engine) as db:
        original = dict(app.dependency_overrides)

        def current_membership():
            return db.query(OrganizationMembership).one()

        def current_user():
            return db.query(User).one()

        def use_db():
            yield db

        app.dependency_overrides[get_db] = use_db
        app.dependency_overrides[get_current_membership] = current_membership
        app.dependency_overrides[get_current_user] = current_user
        try:
            with TestClient(app, follow_redirects=False) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)
    engine.dispose()


def signup(client: TestClient, channel: str):
    # Cognito authenticates the caller and supplies verified email;
    # no AWS account, SMTP or real identity is ever touched.
    with patch(
        "app.api.auth.verify_cognito_access_token",
        return_value={"sub": "synthetic-e2e-owner"},
    ), patch("boto3.client") as cognito, patch(
        "app.services.product_analytics.track_signup_completed"
    ):
        cognito.return_value.get_user.return_value = {
            "UserAttributes": [
                {"Name": "email", "Value": "synthetic-owner@example.test"},
                {"Name": "email_verified", "Value": "true"},
            ]
        }
        response = client.post(
            "/api/register/provision",
            json={
                "name": "Merchant Owner",
                "organization_name": "E2E Synthetic Merchant",
                "registration_channel": channel,
            },
            headers={"Authorization": "Bearer synthetic-cognito-token"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    return response.json()


def stage_verified_managed_install(db: Session) -> str:
    """Synthetic stand-in for a Shopify-issued, verified offline grant.

    No Shopify network call or live token; the claim HTTP handler and
    actual DIAGLOB billing guard still run without mocks.
    """
    now = datetime.utcnow()
    code = secrets.token_urlsafe(32)
    db.add(ShopifyPendingInstall(
        state=secrets.token_urlsafe(32),
        shop_domain=SHOP,
        expires_at=now + timedelta(minutes=10),
        state_used=True,
        grant_method="managed",
        token_encrypted="encrypted-synthetic-access",
        refresh_token_encrypted="encrypted-synthetic-refresh",
        access_token_expires_at=now + timedelta(hours=1),
        refresh_token_expires_at=now + timedelta(days=10),
        claim_hash=hashlib.sha256(code.encode()).hexdigest(),
        claim_expires_at=now + timedelta(minutes=10),
        created_at=now,
    ))
    db.commit()
    return code


def test_direct_signup_to_paddle_checkout_with_no_network_or_charge(scenario):
    client, db = scenario
    registration = signup(client, "direct")
    org = db.get(Organization, registration["organization"]["id"])
    assert (org.billing_provider, org.billing_onboarding_channel) == (
        "paddle", "direct",
    )
    response = client.get("/api/organization")
    assert response.status_code == 200
    assert response.json()["billing_provider"] == "paddle"

    with patch(
        "app.api.billing.get_billing_price_id", return_value="pri_synthetic",
    ) as price, patch(
        "app.api.billing.create_checkout",
        return_value={"checkout_url": "https://sandbox-paddle.example.test/checkout"},
    ) as checkout:
        result = client.post(
            "/api/billing/checkout",
            json={"plan": "starter", "billing_period_months": 1},
        )
    assert result.status_code == 200, result.text
    assert result.json()["checkout_url"].startswith("https://sandbox-paddle.")
    price.assert_called_once_with("starter", 1, "paddle")
    checkout.assert_called_once()
    db.refresh(org)
    assert org.plan == "trial"
    assert org.billing_subscription_id is None


def test_pending_shopify_signup_blocks_paddle_before_and_after_managed_claim(scenario):
    client, db = scenario
    registration = signup(client, "shopify_install")
    org = db.get(Organization, registration["organization"]["id"])
    assert org.billing_provider is None
    assert org.plan == "trial"

    handoff = client.get("/api/shopify/install", params={"shop": SHOP})
    assert handoff.status_code == 503
    assert handoff.json()["detail"] == "SHOPIFY_PUBLIC_INSTALL_NOT_ENABLED"
    assert "location" not in handoff.headers
    assert db.query(ShopifyOAuthState).count() == 0

    with patch("app.api.billing.get_billing_price_id") as price, patch(
        "app.api.billing.create_checkout"
    ) as checkout:
        pending = client.post(
            "/api/billing/checkout",
            json={"plan": "starter", "billing_period_months": 1},
        )
    assert pending.status_code == 409
    assert pending.json()["detail"]["code"] == "SHOPIFY_INSTALL_BILLING_PENDING"
    price.assert_not_called()
    checkout.assert_not_called()

    store = Store(
        organization_id=org.id,
        name="Synthetic Authorized Store",
        slug="synthetic-authorized",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.commit()

    legacy = client.post(
        f"/api/stores/{store.id}/shopify/connect",
        json={"shop_domain": SHOP},
    )
    assert legacy.status_code == 410
    assert legacy.json()["detail"]["code"] == "SHOPIFY_MANAGED_INSTALL_REQUIRED"
    assert db.query(ShopifyOAuthState).count() == 0
    db.refresh(org)
    assert org.billing_provider is None

    code = stage_verified_managed_install(db)
    with patch(
        "app.services.shopify_public_install.ensure_shopify_order_webhooks",
        return_value={"ok": True},
    ) as webhooks:
        claimed = client.post(
            f"/api/stores/{store.id}/shopify/install/claim-code",
            json={"claim_code": code},
        )
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["connected"] is True
        assert claimed.json()["shop_domain"] == SHOP
        webhooks.assert_called_once()

        replay = client.post(
            f"/api/stores/{store.id}/shopify/install/claim-code",
            json={"claim_code": code},
        )
        assert replay.status_code == 404

    db.expire_all()
    connection = db.query(CommerceConnection).one()
    assert connection.external_store_url == SHOP
    assert connection.status == "connected"
    assert connection.access_token_encrypted == "encrypted-synthetic-access"
    assert db.get(Organization, org.id).billing_provider == "shopify"
    assert db.get(Organization, org.id).plan == "trial"

    with patch("app.api.billing.get_billing_price_id") as price, patch(
        "app.api.billing.create_checkout"
    ) as checkout:
        protected = client.post(
            "/api/billing/checkout",
            json={"plan": "growth", "billing_period_months": 1},
        )
    assert protected.status_code == 409
    assert protected.json()["detail"]["code"] == "SHOPIFY_MANAGED_BILLING"
    price.assert_not_called()
    checkout.assert_not_called()


def test_direct_paddle_customer_cannot_claim_new_shopify_public_install(scenario):
    client, db = scenario
    registration = signup(client, "direct")
    org = db.get(Organization, registration["organization"]["id"])
    store = Store(
        organization_id=org.id,
        name="Direct Commerce Store",
        slug="direct-commerce-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        active=True,
    )
    db.add(store)
    db.commit()

    legacy = client.post(
        f"/api/stores/{store.id}/shopify/connect",
        json={"shop_domain": SHOP},
    )
    assert legacy.status_code == 410
    assert legacy.json()["detail"]["code"] == "SHOPIFY_MANAGED_INSTALL_REQUIRED"

    code = stage_verified_managed_install(db)
    with patch("app.services.shopify_public_install.ensure_shopify_order_webhooks") as webhooks:
        claim = client.post(
            f"/api/stores/{store.id}/shopify/install/claim-code",
            json={"claim_code": code},
        )
    assert claim.status_code == 409
    assert claim.json()["detail"] == "SHOPIFY_BILLING_ORGANIZATION_REQUIRED"
    webhooks.assert_not_called()
    db.expire_all()
    assert db.get(Organization, org.id).billing_provider == "paddle"
    assert db.query(CommerceConnection).count() == 0
    assert db.query(ShopifyOAuthState).count() == 0
