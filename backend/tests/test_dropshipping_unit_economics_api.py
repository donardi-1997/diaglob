"""API contract for Dropshipping Unit Economics V2.2."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Store,
    User,
)
import app.services.dropshipping_unit_economics as unit_engine


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_unit_economics_api.db"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
        session.rollback()
        session.close()


@pytest.fixture()
def account(db):
    org = Organization(
        name="Unit Economics API Org",
        slug="unit-economics-api-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    user = User(
        email="unit-economics-api@test.com",
        name="Unit Economics API Tester",
        external_auth_id="unit-economics-api-cognito-sub",
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role="manager",
        all_stores=True,
    )
    db.add(membership)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Unit Economics API Store",
        slug="unit-economics-api-store",
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


def test_empty_period_returns_200_with_provenance_shape(client, account):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["store_id"] == store.id
    assert payload["currency"] == "COP"
    assert payload["recognized_revenue"] == 0.0
    assert payload["components"]["cogs"]["source"] == "not_applicable"
    assert payload["components"]["ad_spend"]["source"] == "missing"
    assert payload["components"]["ad_spend"]["reason"] == "meta_not_connected"
    assert payload["data_quality"]["status"] == "incomplete"
    assert payload["contribution_profit"] is None


def test_date_only_end_is_inclusive_via_existing_parse_range(client, account):
    _, _, _, store = account
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
        "?date_from=2026-09-01&date_to=2026-09-11"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["date_from"] == "2026-09-01T00:00:00"
    assert payload["date_to"] == "2026-09-12T00:00:00"


def test_foreign_store_returns_404(client, db):
    other_org = Organization(
        name="Foreign Unit Economics Org",
        slug="foreign-unit-economics-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(other_org)
    db.flush()
    foreign_store = Store(
        organization_id=other_org.id,
        name="Foreign Unit Economics Store",
        slug="foreign-unit-economics-store",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
    )
    db.add(foreign_store)
    db.commit()

    response = client.get(
        f"/api/stores/{foreign_store.id}/analytics/dropshipping/unit-economics"
    )
    assert response.status_code == 404


def test_store_restricted_membership_cannot_read_unassigned_store(
    client, db, account
):
    org, _, membership, assigned_store = account
    unassigned_store = Store(
        organization_id=org.id,
        name="Unassigned Unit Economics Store",
        slug="unassigned-unit-economics-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(unassigned_store)
    db.flush()
    membership.all_stores = False
    membership.stores.append(assigned_store)
    db.commit()

    allowed = client.get(
        f"/api/stores/{assigned_store.id}/analytics/dropshipping/unit-economics"
    )
    denied = client.get(
        f"/api/stores/{unassigned_store.id}/analytics/dropshipping/unit-economics"
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Store access denied"


def test_inactive_store_returns_404(client, db, account):
    _, _, _, store = account
    store.active = False
    db.commit()

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
    )
    assert response.status_code == 404


def test_requires_analytics_read(client, db, account):
    _, _, membership, store = account
    membership.role = "operator"
    db.commit()

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_config_incompleteness_returns_200_not_5xx(client, db, account):
    _, _, _, store = account
    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        order_number="UE-1",
        total_amount=100000,
        currency="COP",
        lifecycle_status="delivered",
        payment_method="card",
        created_at=datetime(2026, 9, 5, 12, 0, 0),
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=store.organization_id,
            store_id=store.id,
            title="Unit economics item",
            sku="UE-SKU",
            quantity=1,
            unit_price=100000,
            unit_cost=40000,
            currency="COP",
        )
    )
    db.commit()

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
        "?date_from=2026-09-01&date_to=2026-09-11"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_quality"]["status"] == "incomplete"
    assert "outbound_shipping" in payload["data_quality"]["missing_components"]
    assert "payment_fees" in payload["data_quality"]["missing_components"]
    assert payload["contribution_profit"] is None


def test_meta_provider_error_is_component_state_not_endpoint_failure(
    client, account, monkeypatch
):
    _, _, _, store = account
    monkeypatch.setattr(
        unit_engine,
        "resolve_meta_ad_spend",
        lambda *_args, **_kwargs: {
            "amount": None,
            "source": "meta_ads",
            "status": "missing",
            "reason": "provider_error",
            "metadata": {"provider_error_code": "META_TEMPORARY_ERROR"},
        },
    )

    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/unit-economics"
        "?date_from=2026-09-01&date_to=2026-09-11"
    )

    assert response.status_code == 200
    ad_spend = response.json()["components"]["ad_spend"]
    assert ad_spend["status"] == "missing"
    assert ad_spend["reason"] == "provider_error"
    assert ad_spend["metadata"]["provider_error_code"] == "META_TEMPORARY_ERROR"
