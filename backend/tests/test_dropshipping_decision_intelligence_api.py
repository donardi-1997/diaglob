"""API contract coverage for Dropshipping Decision Intelligence."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dropshipping_analytics import _parse_date
from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    Organization,
    OrganizationMembership,
    Store,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_decision_intelligence_api.db"

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
def account(db):
    org = Organization(
        name="Decision API Org",
        slug="decision-api-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    user = User(
        email="decision-api@test.com",
        name="Decision API Tester",
        external_auth_id="decision-api-cognito-sub",
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role="manager",
    )
    db.add(membership)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Decision API Store",
        slug="decision-api-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    return org, user, membership, store


@pytest.fixture()
def client(db, account):
    _, user, membership, _ = account
    original_overrides = dict(app.dependency_overrides)

    def override_db():
        yield db

    def override_user():
        return user

    def override_membership():
        return membership

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_membership] = override_membership

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_date_only_end_boundary_matches_existing_analytics_contract():
    assert _parse_date("2026-09-11", inclusive_end=True) == datetime(2026, 9, 12)


def test_endpoint_returns_structured_empty_response(client, account):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "COP"
    assert payload["insights"] == []
    assert payload["summary"]["products_evaluated"] == 0


def test_endpoint_uses_inclusive_date_only_end(client, account):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights"
        "?date_from=2026-09-01&date_to=2026-09-11"
    )
    assert response.status_code == 200
    assert response.json()["date_from"] == "2026-09-01T00:00:00"
    assert response.json()["date_to"] == "2026-09-12T00:00:00"


@pytest.mark.parametrize("limit", [1, 50])
def test_endpoint_accepts_limit_boundaries(client, account, limit):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights?limit={limit}"
    )
    assert response.status_code == 200


@pytest.mark.parametrize("limit", [0, 51])
def test_endpoint_rejects_limit_outside_contract(client, account, limit):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights?limit={limit}"
    )
    assert response.status_code == 422


def test_endpoint_rejects_foreign_store(client, db, account):
    _, _, _, _ = account
    other_org = Organization(
        name="Foreign Decision Org",
        slug="foreign-decision-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(other_org)
    db.flush()
    foreign_store = Store(
        organization_id=other_org.id,
        name="Foreign Decision Store",
        slug="foreign-decision-store",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
    )
    db.add(foreign_store)
    db.commit()

    response = client.get(
        f"/api/stores/{foreign_store.id}/analytics/dropshipping/insights"
    )
    assert response.status_code == 404


def test_endpoint_rejects_inactive_store(client, db, account):
    _, _, _, store = account
    store.active = False
    db.commit()

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights"
    )
    assert response.status_code == 404


def test_endpoint_requires_analytics_read(client, db, account):
    _, _, membership, store = account
    membership.role = "operator"
    db.commit()

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights"
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
