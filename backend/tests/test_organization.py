import os
from unittest.mock import patch, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import (
    app,
    get_current_membership,
    get_current_user,
)
from app.models import (
    Organization,
    OrganizationMembership,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_organization.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org(db):
    o = Organization(
        name="Test Org",
        slug="test-org",
        plan="starter",
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="org@test.com",
        name="Org Tester",
        external_auth_id="org-cognito-sub",
    )
    db.add(u)
    db.flush()

    m = OrganizationMembership(
        user_id=u.id,
        organization_id=org.id,
        role="owner",
    )
    db.add(m)
    db.flush()

    return u


@pytest.fixture()
def membership(db, user, org):
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id
            == user.id,
            OrganizationMembership.organization_id
            == org.id,
        )
        .first()
    )


@pytest.fixture()
def client(db, membership):
    original_overrides = dict(
        app.dependency_overrides
    )

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    def _override_user():
        return membership.user

    def _override_membership():
        return membership

    app.dependency_overrides[get_db] = (
        _override_get_db
    )
    app.dependency_overrides[
        get_current_user
    ] = _override_user
    app.dependency_overrides[
        get_current_membership
    ] = _override_membership

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        original_overrides
    )


class TestOrganizationEndpoint:
    def test_organization_ok_local_data(
        self, client, org, membership
    ):
        """GET /api/organization returns 200 with
        correct local data when no Paddle configured."""
        resp = client.get("/api/organization")
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] == org.id
        assert data["name"] == "Test Org"
        assert data["slug"] == "test-org"
        assert data["plan"] == "starter"
        assert data["role"] == "owner"
        assert "active_store_limit" in data
        assert "permissions" in data
        assert "next_billed_at" in data

    def test_paddle_not_configured_returns_200(
        self, client, org, membership
    ):
        """When PADDLE_API_KEY is not set, the endpoint
        returns 200 with local data and
        next_billed_at=None."""
        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": ""},
            clear=False,
        ):
            org.billing_subscription_id = (
                "sub_123"
            )
            client.app.dependency_overrides[
                get_current_membership
            ] = lambda: membership

            resp = client.get("/api/organization")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org.id
        assert data["next_billed_at"] is None

    def test_paddle_timeout_returns_200(
        self, client, org, membership
    ):
        """When Paddle times out, endpoint returns 200
        with local data and next_billed_at=None."""
        org.billing_subscription_id = "sub_123"
        client.app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": "test_key"},
            clear=False,
        ), patch(
            "app.api.billing.httpx.get",
            side_effect=httpx.ReadTimeout(
                "timeout"
            ),
        ):
            resp = client.get("/api/organization")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org.id
        assert data["next_billed_at"] is None

    def test_paddle_error_returns_200(
        self, client, org, membership
    ):
        """When Paddle returns an error, endpoint
        returns 200 with local data."""
        org.billing_subscription_id = "sub_123"
        client.app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": "test_key"},
            clear=False,
        ), patch(
            "app.api.billing.httpx.get",
            side_effect=httpx.ConnectError(
                "connection refused"
            ),
        ):
            resp = client.get("/api/organization")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org.id
        assert data["next_billed_at"] is None

    def test_cross_tenant_isolation(
        self, client, db, org
    ):
        """Endpoint only returns the authenticated
        user's organization, never another org."""
        other_org = Organization(
            name="Other Org",
            slug="other-org",
            plan="growth",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        resp = client.get("/api/organization")
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] == org.id
        assert data["slug"] == "test-org"
        assert data["name"] == "Test Org"
        assert "other-org" not in data["slug"]

    def test_no_membership_returns_403(self, client):
        """User with no membership at all gets 403."""
        app.dependency_overrides.pop(
            get_current_membership, None
        )

        def _no_membership():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail="Organization access denied",
            )

        app.dependency_overrides[
            get_current_membership
        ] = _no_membership

        resp = client.get("/api/organization")
        assert resp.status_code == 403

        app.dependency_overrides.pop(
            get_current_membership, None
        )

    def test_no_secrets_exposed(
        self, client, org, membership
    ):
        """Response must not contain PADDLE_API_KEY,
        access tokens, or other secrets."""
        resp = client.get("/api/organization")
        assert resp.status_code == 200

        data = resp.json()
        text = resp.text

        assert "PADDLE_API_KEY" not in text
        assert "test_key" not in text

        assert "access_token" not in data
        assert "api_key" not in data
        assert "secret" not in data

    def test_billing_fields_compatibility(
        self, client, org, membership
    ):
        """Response contains all fields the frontend
        expects."""
        org.billing_subscription_id = "sub_999"
        org.billing_period_months = 12
        org.auto_renew_enabled = True
        org.pending_plan = "growth"
        org.pending_billing_period_months = 6
        client.app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        resp = client.get("/api/organization")
        assert resp.status_code == 200

        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "slug" in data
        assert "active" in data
        assert "plan" in data
        assert "plan_name" in data
        assert "billing_period_months" in data
        assert "next_billed_at" in data
        assert "pending_plan" in data
        assert "pending_billing_period_months" in data
        assert "pending_plan_effective_at" in data
        assert "active_stores" in data
        assert "active_store_limit" in data
        assert "role" in data
        assert "all_stores" in data
        assert "permissions" in data
        assert "auto_renew_enabled" in data

        assert (
            data["billing_period_months"] == 12
        )
        assert data["auto_renew_enabled"] is True
        assert data["pending_plan"] == "growth"
        assert (
            data["pending_billing_period_months"]
            == 6
        )

    def test_paddle_success_populates_next_billed(
        self, client, org, membership
    ):
        """When Paddle responds successfully,
        next_billed_at is populated."""
        org.billing_subscription_id = "sub_123"
        client.app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "next_billed_at": "2026-09-01T00:00:00Z"
            }
        }

        with patch.dict(
            os.environ,
            {"PADDLE_API_KEY": "test_key"},
            clear=False,
        ), patch(
            "app.api.billing.httpx.get",
            return_value=mock_response,
        ):
            resp = client.get("/api/organization")

        assert resp.status_code == 200
        data = resp.json()
        assert (
            data["next_billed_at"]
            == "2026-09-01T00:00:00Z"
        )
