"""Persistence contract for store Unit Economics configuration."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Organization,
    PaymentMethodCostRule,
    Store,
    StoreUnitEconomicsConfig,
)


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit_economics_models.db"
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
    engine.dispose()
    try:
        os.remove("./test_unit_economics_models.db")
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
    organization = Organization(
        name="Unit Economics Org",
        slug="unit-economics-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()

    store = Store(
        organization_id=organization.id,
        name="Unit Economics Store",
        slug="unit-economics-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def test_unit_economics_tables_registered():
    assert StoreUnitEconomicsConfig.__tablename__ == "store_unit_economics_configs"
    assert PaymentMethodCostRule.__tablename__ == "payment_method_cost_rules"
    assert "store_unit_economics_configs" in Base.metadata.tables
    assert "payment_method_cost_rules" in Base.metadata.tables


def test_payment_method_rule_has_composite_parent_scope_foreign_key():
    constraints = PaymentMethodCostRule.__table__.foreign_key_constraints
    scoped = [
        constraint
        for constraint in constraints
        if {column.name for column in constraint.columns}
        == {"unit_economics_config_id", "organization_id", "store_id"}
    ]

    assert len(scoped) == 1
    assert scoped[0].name == "fk_unit_economics_rule_parent_scope"
    assert {
        element.target_fullname for element in scoped[0].elements
    } == {
        "store_unit_economics_configs.id",
        "store_unit_economics_configs.organization_id",
        "store_unit_economics_configs.store_id",
    }


def test_store_config_is_unique_per_store(db, store):
    db.add(
        StoreUnitEconomicsConfig(
            organization_id=store.organization_id,
            store_id=store.id,
        )
    )
    db.commit()

    db.add(
        StoreUnitEconomicsConfig(
            organization_id=store.organization_id,
            store_id=store.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_payment_method_rule_is_unique_per_store_and_method(db, store):
    config = StoreUnitEconomicsConfig(
        organization_id=store.organization_id,
        store_id=store.id,
    )
    db.add(config)
    db.flush()

    db.add(
        PaymentMethodCostRule(
            organization_id=store.organization_id,
            store_id=store.id,
            unit_economics_config_id=config.id,
            payment_method="cash_on_delivery",
            is_cod=True,
        )
    )
    db.commit()

    db.add(
        PaymentMethodCostRule(
            organization_id=store.organization_id,
            store_id=store.id,
            unit_economics_config_id=config.id,
            payment_method="cash_on_delivery",
            is_cod=True,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
