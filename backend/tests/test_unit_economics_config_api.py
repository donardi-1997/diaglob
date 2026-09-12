"""API contract for store Unit Economics configuration."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    Organization,
    OrganizationMembership,
    Store,
    StoreUnitEconomicsConfig,
    User,
)


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit_economics_config_api.db"
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
    engine.dispose()
    try:
        os.remove("./test_unit_economics_config_api.db")
    except FileNotFoundError:
        pass


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
        name="Unit API Org",
        slug="unit-api-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    user = User(
        email="unit-api@test.com",
        name="Unit API Tester",
        external_auth_id="unit-api-cognito-sub",
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
        name="Unit API Store",
        slug="unit-api-store",
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


def test_get_empty_config_is_read_only(client, db, account):
    _, _, _, store = account
    response = client.get(f"/api/stores/{store.id}/unit-economics/config")

    assert response.status_code == 200
    assert response.json() == {
        "store_id": store.id,
        "currency": "COP",
        "outbound_shipping_cost": None,
        "return_logistics_cost": None,
        "default_payment_fee_percent": None,
        "default_payment_fee_fixed": None,
        "default_cod_fee_percent": None,
        "payment_methods": [],
    }
    assert db.query(StoreUnitEconomicsConfig).count() == 0


def test_put_replaces_config_and_normalizes_methods(client, account):
    _, _, _, store = account
    response = client.put(
        f"/api/stores/{store.id}/unit-economics/config",
        json={
            "outbound_shipping_cost": 15000,
            "return_logistics_cost": 18000,
            "default_payment_fee_percent": 3.5,
            "default_payment_fee_fixed": 900,
            "default_cod_fee_percent": 4,
            "payment_methods": [
                {
                    "payment_method": " Cash On Delivery ",
                    "is_cod": True,
                    "cod_fee_percent": 4,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "COP"
    assert payload["outbound_shipping_cost"] == 15000.0
    assert payload["payment_methods"][0]["payment_method"] == "cash on delivery"


def test_put_requires_stores_write(client, db, account):
    _, _, membership, store = account
    membership.role = "operator"
    db.commit()

    response = client.put(
        f"/api/stores/{store.id}/unit-economics/config",
        json={"payment_methods": []},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_get_requires_stores_read(client, db, account):
    _, _, membership, store = account
    membership.role = "no_permissions"
    db.commit()

    response = client.get(f"/api/stores/{store.id}/unit-economics/config")
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


def test_suspended_store_remains_configurable(client, db, account):
    _, _, _, store = account
    store.active = False
    db.commit()

    get_response = client.get(f"/api/stores/{store.id}/unit-economics/config")
    put_response = client.put(
        f"/api/stores/{store.id}/unit-economics/config",
        json={"outbound_shipping_cost": 12000, "payment_methods": []},
    )

    assert get_response.status_code == 200
    assert put_response.status_code == 200
    assert put_response.json()["outbound_shipping_cost"] == 12000.0


def test_foreign_store_returns_404(client, db, account):
    other_org = Organization(
        name="Foreign Unit API Org",
        slug="foreign-unit-api-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(other_org)
    db.flush()
    foreign_store = Store(
        organization_id=other_org.id,
        name="Foreign Unit API Store",
        slug="foreign-unit-api-store",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
    )
    db.add(foreign_store)
    db.commit()

    response = client.get(f"/api/stores/{foreign_store.id}/unit-economics/config")
    assert response.status_code == 404


def test_deleted_store_returns_404(client, db, account):
    _, _, _, store = account
    store.deleted = True
    db.commit()

    response = client.get(f"/api/stores/{store.id}/unit-economics/config")
    assert response.status_code == 404


def test_duplicate_normalized_methods_returns_400(client, account):
    _, _, _, store = account
    response = client.put(
        f"/api/stores/{store.id}/unit-economics/config",
        json={
            "payment_methods": [
                {"payment_method": "COD", "is_cod": True},
                {"payment_method": " cod ", "is_cod": True},
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "duplicate_payment_method"


def test_invalid_cost_returns_validation_error(client, account):
    _, _, _, store = account
    response = client.put(
        f"/api/stores/{store.id}/unit-economics/config",
        json={"outbound_shipping_cost": -1, "payment_methods": []},
    )

    assert response.status_code in {400, 422}
