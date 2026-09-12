"""Currency-change contract for Unit Economics fixed monetary assumptions."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import Organization, OrganizationMembership, Store, User


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit_economics_currency_change.db"
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
        os.remove("./test_unit_economics_currency_change.db")
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
        name="Currency Change Org",
        slug="currency-change-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    user = User(
        email="currency-change@test.com",
        name="Currency Change Tester",
        external_auth_id="currency-change-sub",
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
        name="Panama Store",
        slug="panama-store",
        country_code="PA",
        currency="PAB",
        timezone="America/Panama",
        default_language="es",
    )
    db.add(store)
    db.commit()
    return user, membership, store


@pytest.fixture()
def client(db, account):
    user, membership, _ = account
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


def _seed_cost_config(client: TestClient, store_id: int):
    response = client.put(
        f"/api/stores/{store_id}/unit-economics/config",
        json={
            "outbound_shipping_cost": 7.5,
            "return_logistics_cost": 9.25,
            "default_payment_fee_percent": 3.5,
            "default_payment_fee_fixed": 0.75,
            "default_cod_fee_percent": 4.0,
            "payment_methods": [
                {
                    "payment_method": "cash_on_delivery",
                    "fee_percent": 2.9,
                    "fee_fixed": 0.5,
                    "is_cod": True,
                    "cod_fee_percent": 4.25,
                }
            ],
        },
    )
    assert response.status_code == 200


def test_currency_change_clears_fixed_amounts_but_preserves_percentages(client, account):
    _, _, store = account
    _seed_cost_config(client, store.id)

    changed = client.patch(f"/api/stores/{store.id}", json={"currency": "USD"})
    assert changed.status_code == 200
    assert changed.json()["currency"] == "USD"

    config_response = client.get(f"/api/stores/{store.id}/unit-economics/config")
    assert config_response.status_code == 200
    config = config_response.json()

    assert config["currency"] == "USD"
    assert config["outbound_shipping_cost"] is None
    assert config["return_logistics_cost"] is None
    assert config["default_payment_fee_fixed"] is None
    assert config["default_payment_fee_percent"] == 3.5
    assert config["default_cod_fee_percent"] == 4.0

    method = config["payment_methods"][0]
    assert method["payment_method"] == "cash_on_delivery"
    assert method["fee_fixed"] is None
    assert method["fee_percent"] == 2.9
    assert method["is_cod"] is True
    assert method["cod_fee_percent"] == 4.25


def test_same_currency_does_not_clear_fixed_amounts(client, account):
    _, _, store = account
    _seed_cost_config(client, store.id)

    unchanged = client.patch(f"/api/stores/{store.id}", json={"currency": "PAB"})
    assert unchanged.status_code == 200

    config = client.get(f"/api/stores/{store.id}/unit-economics/config").json()
    assert config["outbound_shipping_cost"] == 7.5
    assert config["return_logistics_cost"] == 9.25
    assert config["default_payment_fee_fixed"] == 0.75
    assert config["payment_methods"][0]["fee_fixed"] == 0.5
