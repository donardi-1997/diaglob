"""Service contract for Unit Economics configuration."""

import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Organization, PaymentMethodCostRule, Store, StoreUnitEconomicsConfig
from app.services.unit_economics_config_service import (
    get_unit_economics_config,
    normalize_payment_method,
    replace_unit_economics_config,
)


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit_economics_config_service.db"
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
        os.remove("./test_unit_economics_config_service.db")
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
def store(db):
    org = Organization(
        name="Unit Config Org",
        slug="unit-config-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Unit Config Store",
        slug="unit-config-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def test_normalize_payment_method():
    assert normalize_payment_method("  Cash On Delivery  ") == "cash on delivery"
    assert normalize_payment_method(None) == ""


def test_get_empty_config_does_not_persist(db, store):
    result = get_unit_economics_config(db, store.organization_id, store.id)

    assert result["store_id"] == store.id
    assert result["currency"] == "COP"
    assert result["outbound_shipping_cost"] is None
    assert result["payment_methods"] == []
    assert db.query(StoreUnitEconomicsConfig).count() == 0


def test_replace_rejects_duplicate_normalized_methods(db, store):
    with pytest.raises(ValueError, match="duplicate_payment_method"):
        replace_unit_economics_config(
            db,
            store.organization_id,
            store.id,
            {
                "payment_methods": [
                    {"payment_method": "COD", "is_cod": True},
                    {"payment_method": " cod ", "is_cod": True},
                ]
            },
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("outbound_shipping_cost", -1),
        ("return_logistics_cost", -1),
        ("default_payment_fee_fixed", -1),
        ("default_payment_fee_percent", -0.1),
        ("default_payment_fee_percent", 100.1),
        ("default_cod_fee_percent", -0.1),
        ("default_cod_fee_percent", 100.1),
    ],
)
def test_replace_rejects_invalid_default_values(db, store, field, value):
    with pytest.raises(ValueError, match="invalid_unit_economics_value"):
        replace_unit_economics_config(
            db,
            store.organization_id,
            store.id,
            {field: value, "payment_methods": []},
        )


def test_replace_rejects_empty_payment_method(db, store):
    with pytest.raises(ValueError, match="payment_method_required"):
        replace_unit_economics_config(
            db,
            store.organization_id,
            store.id,
            {"payment_methods": [{"payment_method": "   "}]},
        )


def test_replace_rejects_invalid_method_values(db, store):
    with pytest.raises(ValueError, match="invalid_unit_economics_value"):
        replace_unit_economics_config(
            db,
            store.organization_id,
            store.id,
            {
                "payment_methods": [
                    {
                        "payment_method": "card",
                        "fee_percent": 101,
                        "fee_fixed": 100,
                    }
                ]
            },
        )


def test_replace_upserts_defaults_and_replaces_stale_methods(db, store):
    first = replace_unit_economics_config(
        db,
        store.organization_id,
        store.id,
        {
            "outbound_shipping_cost": 15000,
            "return_logistics_cost": 18000,
            "default_payment_fee_percent": 3.5,
            "default_payment_fee_fixed": 900,
            "default_cod_fee_percent": 4,
            "payment_methods": [
                {
                    "payment_method": " Cash On Delivery ",
                    "fee_percent": 2.9,
                    "fee_fixed": 500,
                    "is_cod": True,
                    "cod_fee_percent": 4,
                },
                {
                    "payment_method": "card",
                    "fee_percent": 3.2,
                    "fee_fixed": 700,
                    "is_cod": False,
                },
            ],
        },
    )

    assert first["outbound_shipping_cost"] == 15000.0
    assert first["payment_methods"][0]["payment_method"] == "cash on delivery"
    assert db.query(StoreUnitEconomicsConfig).count() == 1
    assert db.query(PaymentMethodCostRule).count() == 2

    second = replace_unit_economics_config(
        db,
        store.organization_id,
        store.id,
        {
            "outbound_shipping_cost": 17000,
            "payment_methods": [
                {
                    "payment_method": "card",
                    "fee_percent": 3.0,
                    "fee_fixed": 600,
                    "is_cod": False,
                }
            ],
        },
    )

    assert second["outbound_shipping_cost"] == 17000.0
    assert second["return_logistics_cost"] is None
    assert [rule["payment_method"] for rule in second["payment_methods"]] == ["card"]
    assert db.query(StoreUnitEconomicsConfig).count() == 1
    assert db.query(PaymentMethodCostRule).count() == 1

    persisted = db.query(StoreUnitEconomicsConfig).one()
    assert persisted.default_payment_fee_percent is None
    rule = db.query(PaymentMethodCostRule).one()
    assert rule.fee_percent == Decimal("3.0000")


def test_service_rejects_foreign_or_deleted_store(db, store):
    with pytest.raises(ValueError, match="store_not_found"):
        get_unit_economics_config(db, store.organization_id + 999, store.id)

    store.deleted = True
    db.commit()
    with pytest.raises(ValueError, match="store_not_found"):
        get_unit_economics_config(db, store.organization_id, store.id)
