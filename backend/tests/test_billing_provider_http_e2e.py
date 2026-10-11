"""HTTP journey tests: signup -> billing -> signed Shopify OAuth -> replay.

These are provider-SIMULATED API E2E tests. They run actual FastAPI routing,
persistence and HMAC verification without a paid Paddle checkout or live
Shopify Admin/Partner calls. They do NOT certify external merchant E2E.
"""
from datetime import datetime
import hashlib
import hmac
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    CommerceConnection, Organization, OrganizationMembership,
    ShopifyOAuthState, Store, User,
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


def signed_callback(state: str, *, shop: str = SHOP) -> dict:
    params = {
        "code": "fake-oauth-exchange-code",
        "shop": shop,
        "state": state,
        "timestamp": "1474933560",
    }
    message = "&".join(f"{key}={params[key]}" for key in sorted(params))
    params["hmac"] = hmac.new(
        SECRET.encode(), message.encode(), hashlib.sha256,
    ).hexdigest()
    return params


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


def test_pending_shopify_signup_blocks_paddle_before_and_after_oauth(scenario):
    client, db = scenario
    registration = signup(client, "shopify_install")
    org = db.get(Organization, registration["organization"]["id"])
    assert org.billing_provider is None
    assert org.plan == "trial"

    handoff = client.get("/api/shopify/install", params={"shop": SHOP})
    assert handoff.status_code == 303
    assert handoff.headers["location"] == (
        f"https://diaglob.tech/shopify/install?shop={SHOP}"
    )
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

    start = client.post(
        f"/api/stores/{store.id}/shopify/connect",
        json={"shop_domain": SHOP},
    )
    assert start.status_code == 200, start.text
    destination = urlsplit(start.json()["authorization_url"])
    assert destination.hostname == SHOP
    assert destination.path == "/admin/oauth/authorize"
    oauth_state = parse_qs(destination.query)["state"][0]
    assert db.query(ShopifyOAuthState).filter_by(state=oauth_state).one().used is False
    db.refresh(org)
    assert org.billing_provider is None

    with patch(
        "app.services.shopify_service.exchange_access_token",
        return_value="fake-provider-token",
    ) as exchange, patch(
        "app.services.shopify_service.encrypt_shopify_secret",
        return_value="fake-encrypted-token",
    ), patch(
        "app.services.shopify_service.ensure_shopify_order_webhooks",
        return_value={"ok": True},
    ), patch(
        "app.services.product_analytics.track_shopify_connected"
    ), patch(
        "app.services.shopify_service.record_lifecycle_conversion"
    ):
        rejected = signed_callback(oauth_state)
        rejected["hmac"] = "0" * 64
        bad = client.get("/api/shopify/callback", params=rejected)
        assert bad.status_code == 403
        assert db.query(ShopifyOAuthState).filter_by(state=oauth_state).one().used is False
        exchange.assert_not_called()

        valid = signed_callback(oauth_state)
        callback = client.get("/api/shopify/callback", params=valid)
        assert callback.status_code in {302, 307}, callback.text
        assert callback.headers["location"].startswith("https://diaglob.tech")
        exchange.assert_called_once_with(SHOP, "fake-oauth-exchange-code")

        replay = client.get("/api/shopify/callback", params=valid)
        assert replay.status_code == 400
        exchange.assert_called_once()

    db.expire_all()
    connection = db.query(CommerceConnection).one()
    assert connection.external_store_url == SHOP
    assert connection.status == "connected"
    assert connection.access_token_encrypted == "fake-encrypted-token"
    assert db.query(ShopifyOAuthState).filter_by(state=oauth_state).one().used is True
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


def test_direct_paddle_customer_can_connect_shopify_for_commerce_only(scenario):
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

    start = client.post(
        f"/api/stores/{store.id}/shopify/connect",
        json={"shop_domain": SHOP},
    )
    assert start.status_code == 200
    state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
    with patch(
        "app.services.shopify_service.exchange_access_token",
        return_value="synthetic",
    ), patch(
        "app.services.shopify_service.encrypt_shopify_secret",
        return_value="encrypted-synthetic",
    ), patch(
        "app.services.shopify_service.ensure_shopify_order_webhooks",
        return_value={"ok": True},
    ), patch(
        "app.services.product_analytics.track_shopify_connected"
    ), patch(
        "app.services.shopify_service.record_lifecycle_conversion"
    ):
        callback = client.get(
            "/api/shopify/callback", params=signed_callback(state),
        )
    assert callback.status_code in {302, 307}, callback.text
    db.expire_all()
    assert db.get(Organization, org.id).billing_provider == "paddle"
    assert db.query(CommerceConnection).one().status == "connected"
