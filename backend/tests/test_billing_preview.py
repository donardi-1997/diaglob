"""
Tests for POST /api/billing/upgrade/preview endpoint.

Covers:
- Starter -> Growth, Pro, Scale
- Growth -> Pro, Scale
- Pro -> Scale
- Local fallback when Paddle unavailable
- Local fallback when external subscription missing
- current period missing (uses computed)
- Same plan -> 400
- Invalid plan -> 400
- Subscription not active -> 409
- No subscription_id -> falls through to local
- Paddle unavailable -> fallback local
- Response schema validation
"""

import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import (
    app,
    get_current_membership,
    get_current_user,
    _rate_limit_store,
)
from app.models import (
    Organization,
    OrganizationMembership,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_billing_preview.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(autouse=True)
def setup_db():
    _rate_limit_store.clear()
    Base.metadata.create_all(bind=engine)
    yield
    _rate_limit_store.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_org(
    db,
    plan="starter",
    subscription_status="active",
    billing_subscription_id=None,
    billing_period_months=1,
):
    o = Organization(
        name="Test Org",
        slug="test-org",
        plan=plan,
        subscription_status=subscription_status,
        billing_subscription_id=billing_subscription_id,
        billing_period_months=billing_period_months,
    )
    db.add(o)
    db.flush()
    return o


def _make_user(db, org, role="owner"):
    u = User(
        email="user@test.com",
        name="Test User",
        external_auth_id="test-cognito-sub",
    )
    db.add(u)
    db.flush()

    m = OrganizationMembership(
        user_id=u.id,
        organization_id=org.id,
        role=role,
    )
    db.add(m)
    db.flush()
    return u, m


@pytest.fixture()
def client_factory(db):
    clients = []

    def _create(org):
        user, membership = _make_user(db, org)

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_db():
            try:
                yield db
            finally:
                pass

        def _override_user():
            return membership.user

        def _override_membership():
            return membership

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = (
            _override_user
        )
        app.dependency_overrides[
            get_current_membership
        ] = _override_membership

        c = TestClient(app, raise_server_exceptions=False)
        clients.append(
            (c, original_overrides)
        )
        return c

    yield _create

    for c, orig in clients:
        c.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(orig)


class TestPreviewUpgradePlanPaths:
    """Test all upgrade paths with local fallback."""

    def test_starter_to_growth(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "starter"
        assert data["target_plan"] == "growth"
        assert data["currency_code"] == "USD"
        assert "amount_due" in data
        assert "update_summary" in data
        assert "_source" in data
        assert data["_source"] == "local"

        amount = int(data["amount_due"])
        assert amount > 0

    def test_starter_to_pro(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "starter"
        assert data["target_plan"] == "pro"
        assert "_source" in data

        amount = int(data["amount_due"])
        assert amount > 0

    def test_starter_to_scale(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "scale"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "starter"
        assert data["target_plan"] == "scale"
        assert "_source" in data

        amount = int(data["amount_due"])
        assert amount > 0

    def test_growth_to_pro(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="growth",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "growth"
        assert data["target_plan"] == "pro"
        assert "_source" in data

    def test_growth_to_scale(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="growth",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "scale"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "growth"
        assert data["target_plan"] == "scale"
        assert "_source" in data

    def test_pro_to_scale(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="pro",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "scale"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_plan"] == "pro"
        assert data["target_plan"] == "scale"
        assert "_source" in data


class TestPreviewFallbackBehavior:
    """Test local fallback when Paddle is unavailable."""

    def test_paddle_unavailable_uses_local(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_subscription_id="sub_123",
            billing_period_months=1,
        )
        client = client_factory(org)

        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": "test_key"},
            clear=False,
        ):
            with patch(
                "app.api.billing.httpx"
            ) as mock_httpx:
                mock_httpx.RequestError = (
                    ConnectionError
                )
                mock_httpx.patch.side_effect = (
                    ConnectionError("timeout")
                )

                resp = client.post(
                    "/api/billing/upgrade/preview",
                    json={"plan": "pro"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["_source"] == "local"

    def test_no_paddle_key_uses_local(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": ""},
            clear=False,
        ):
            resp = client.post(
                "/api/billing/upgrade/preview",
                json={"plan": "growth"},
            )

        assert resp.status_code == 200
        assert resp.json()["_source"] == "local"

    def test_no_subscription_id_uses_local(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_subscription_id=None,
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["_source"] == "local"
        assert data["amount_due"] is not None

    def test_paddle_price_not_configured_uses_local(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_subscription_id="sub_123",
            billing_period_months=1,
        )
        client = client_factory(org)

        with patch.dict(
            os.environ,
            {
                "PADDLE_API_KEY": "test_key",
                "PADDLE_PRICE_PRO_1M": "",
            },
            clear=False,
        ):
            resp = client.post(
                "/api/billing/upgrade/preview",
                json={"plan": "pro"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["_source"] == "local"


class TestPreviewValidation:
    """Test legitimate 400/409 rejection cases."""

    def test_same_plan_returns_409(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "starter"},
        )

        assert resp.status_code == 409

    def test_invalid_plan_returns_400(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "enterprise"},
        )

        assert resp.status_code == 400
        assert "Invalid target plan" in resp.json()[
            "detail"
        ]

    def test_downgrade_returns_409(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="pro",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "starter"},
        )

        assert resp.status_code == 409

    def test_subscription_not_active_returns_409(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            subscription_status="canceled",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        assert resp.status_code == 409

    def test_plan_none_returns_409(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="none",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "starter"},
        )

        assert resp.status_code == 409


class TestPreviewResponseSchema:
    """Validate response schema matches frontend expectations."""

    def test_response_has_all_fields(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        data = resp.json()

        required = {
            "current_plan",
            "target_plan",
            "subscription_id",
            "next_billed_at",
            "currency_code",
            "amount_due",
            "subtotal",
            "tax",
            "update_summary",
            "immediate_transaction",
            "next_transaction",
        }

        for field in required:
            assert field in data, (
                f"Missing field: {field}"
            )

    def test_update_summary_structure(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        summary = resp.json()["update_summary"]

        assert "charge" in summary
        assert "credit" in summary
        assert "result" in summary

        for key in ["charge", "credit", "result"]:
            assert "amount" in summary[key]
            assert "currency_code" in summary[key]

    def test_amount_due_is_string_cents(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "pro"},
        )

        assert resp.status_code == 200
        data = resp.json()

        amount = int(data["amount_due"])
        assert amount >= 0


class TestPreviewEdgeCases:
    """Test edge cases and billing period variations."""

    def test_3_month_billing_period(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=3,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["_source"] == "local"

        amount = int(data["amount_due"])
        assert amount > 0

    def test_12_month_billing_period(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=12,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "scale"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["_source"] == "local"

        amount = int(data["amount_due"])
        assert amount > 0

    def test_subscription_status_trialing(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            subscription_status="trialing",
            billing_period_months=1,
        )
        client = client_factory(org)

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        assert resp.status_code == 200
        assert resp.json()["_source"] == "local"

    def test_manager_role_allowed(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )
        u, m = _make_user(db, org, role="manager")

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_db():
            try:
                yield db
            finally:
                pass

        def _override_user():
            return u

        def _override_membership():
            return m

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = (
            _override_user
        )
        app.dependency_overrides[
            get_current_membership
        ] = _override_membership

        client = TestClient(
            app, raise_server_exceptions=False
        )

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            original_overrides
        )

        assert resp.status_code == 200

    def test_operator_role_denied(
        self, client_factory, db
    ):
        org = _make_org(
            db,
            plan="starter",
            billing_period_months=1,
        )

        original_overrides = dict(
            app.dependency_overrides
        )

        u, m = _make_user(db, org, role="operator")

        def _override_db():
            try:
                yield db
            finally:
                pass

        def _override_user():
            return u

        def _override_membership():
            return m

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = (
            _override_user
        )
        app.dependency_overrides[
            get_current_membership
        ] = _override_membership

        client = TestClient(
            app, raise_server_exceptions=False
        )

        resp = client.post(
            "/api/billing/upgrade/preview",
            json={"plan": "growth"},
        )

        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            original_overrides
        )

        assert resp.status_code == 403
