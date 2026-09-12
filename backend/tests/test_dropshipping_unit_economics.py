"""Deterministic store Unit Economics engine contract."""

import math
import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Order, OrderItem, Organization, Store
from app.services.unit_economics_config_service import replace_unit_economics_config
import app.services.dropshipping_unit_economics as unit_engine
from app.services.dropshipping_unit_economics import get_store_unit_economics


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_unit_economics.db"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
DATE_FROM = datetime(2026, 9, 1)
DATE_TO = datetime(2026, 9, 12)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("./test_dropshipping_unit_economics.db")
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
        name="Unit Engine Org",
        slug="unit-engine-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()
    store = Store(
        organization_id=organization.id,
        name="Unit Engine Store",
        slug="unit-engine-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@pytest.fixture(autouse=True)
def meta_actual_zero(monkeypatch):
    monkeypatch.setattr(
        unit_engine,
        "resolve_meta_ad_spend",
        lambda *_args, **_kwargs: {
            "amount": Decimal("0"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {"provider_currency": "COP", "store_currency": "COP"},
        },
    )


def _order(
    db,
    store,
    *,
    number,
    amount,
    lifecycle,
    payment_method="card",
    created_at=datetime(2026, 9, 5, 12, 0, 0),
    item_costs=(),
):
    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        order_number=number,
        total_amount=amount,
        currency=store.currency,
        lifecycle_status=lifecycle,
        payment_method=payment_method,
        created_at=created_at,
    )
    db.add(order)
    db.flush()
    for index, item in enumerate(item_costs, start=1):
        if len(item) == 2:
            quantity, unit_cost = item
            unit_price = Decimal(str(amount)) / max(quantity, 1)
        else:
            quantity, unit_cost, unit_price = item
        db.add(
            OrderItem(
                order_id=order.id,
                organization_id=store.organization_id,
                store_id=store.id,
                title=f"Item {number}-{index}",
                sku=f"SKU-{number}-{index}",
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                currency=store.currency,
            )
        )
    db.commit()
    return order


def _configure(db, store, **overrides):
    payload = {
        "outbound_shipping_cost": 0,
        "return_logistics_cost": 0,
        "default_payment_fee_percent": 0,
        "default_payment_fee_fixed": 0,
        "default_cod_fee_percent": 0,
        "payment_methods": [],
    }
    payload.update(overrides)
    return replace_unit_economics_config(
        db, store.organization_id, store.id, payload
    )


def _run(db, store):
    return get_store_unit_economics(
        db, store.organization_id, store, DATE_FROM, DATE_TO
    )


def test_mixed_cohort_calculates_complete_contribution(db, store, monkeypatch):
    _configure(
        db,
        store,
        outbound_shipping_cost=60000,
        return_logistics_cost=36000,
        default_payment_fee_percent=None,
        default_payment_fee_fixed=None,
        default_cod_fee_percent=None,
        payment_methods=[
            {
                "payment_method": "card",
                "fee_percent": 3,
                "fee_fixed": 1000,
                "is_cod": False,
            },
            {
                "payment_method": "cash",
                "fee_percent": 4,
                "fee_fixed": 6000,
                "is_cod": True,
                "cod_fee_percent": 2.1,
            },
        ],
    )
    _order(
        db,
        store,
        number="D1",
        amount=1500000,
        lifecycle="delivered",
        payment_method="card",
        item_costs=[(1, 800000)],
    )
    _order(
        db,
        store,
        number="D2",
        amount=1000000,
        lifecycle="delivered",
        payment_method="cash",
        item_costs=[(2, 400000)],
    )
    _order(
        db,
        store,
        number="R1",
        amount=700000,
        lifecycle="returned",
        payment_method="card",
        item_costs=[(1, 300000)],
    )
    _order(
        db,
        store,
        number="C1",
        amount=900000,
        lifecycle="cancelled",
        payment_method="cash",
        item_costs=[(1, 200000)],
    )
    monkeypatch.setattr(
        unit_engine,
        "resolve_meta_ad_spend",
        lambda *_args, **_kwargs: {
            "amount": Decimal("300000"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        },
    )

    result = _run(db, store)

    assert result["recognized_revenue"] == 2500000.0
    assert result["components"]["cogs"]["source"] == "actual"
    assert result["components"]["cogs"]["amount"] == 1600000.0
    assert result["components"]["outbound_shipping"]["source"] == "estimated"
    assert result["components"]["outbound_shipping"]["amount"] == 180000.0
    assert result["components"]["payment_fees"]["amount"] == 92000.0
    assert result["components"]["cod_fees"]["amount"] == 21000.0
    assert result["components"]["reverse_logistics"]["amount"] == 36000.0
    assert result["components"]["ad_spend"]["amount"] == 300000.0
    assert result["data_quality"]["status"] == "complete"
    assert result["contribution_profit"] == pytest.approx(
        2500000 - 1600000 - 180000 - 92000 - 21000 - 36000 - 300000
    )
    assert result["contribution_margin"] == pytest.approx(10.84)


def test_returned_order_has_no_revenue_or_cogs_but_has_logistics(db, store):
    _configure(
        db,
        store,
        outbound_shipping_cost=10000,
        return_logistics_cost=15000,
    )
    _order(
        db,
        store,
        number="R1",
        amount=500000,
        lifecycle="returned",
        item_costs=[(1, 200000)],
    )

    result = _run(db, store)

    assert result["recognized_revenue"] == 0.0
    assert result["components"]["cogs"]["status"] == "not_applicable"
    assert result["components"]["cogs"]["amount"] == 0.0
    assert result["components"]["outbound_shipping"]["amount"] == 10000.0
    assert result["components"]["reverse_logistics"]["amount"] == 15000.0
    assert result["components"]["payment_fees"]["status"] == "not_applicable"
    assert result["contribution_profit"] == -25000.0
    assert result["contribution_margin"] is None


def test_cancelled_order_has_no_invented_operating_costs(db, store):
    _configure(db, store)
    _order(
        db,
        store,
        number="C1",
        amount=800000,
        lifecycle="cancelled",
        item_costs=[(1, 250000)],
    )

    result = _run(db, store)

    assert result["recognized_revenue"] == 0.0
    for name in (
        "cogs",
        "outbound_shipping",
        "payment_fees",
        "cod_fees",
        "reverse_logistics",
    ):
        assert result["components"][name]["status"] == "not_applicable"
        assert result["components"][name]["amount"] == 0.0
    assert result["contribution_profit"] == 0.0


def test_incomplete_cogs_exposes_known_subtotal_but_withholds_contribution(db, store):
    _configure(db, store)
    _order(
        db,
        store,
        number="D1",
        amount=500,
        lifecycle="delivered",
        item_costs=[(1, 50, 250), (1, None, 250)],
    )

    result = _run(db, store)

    cogs = result["components"]["cogs"]
    assert cogs["status"] == "missing"
    assert cogs["source"] == "missing"
    assert cogs["reason"] == "cogs_incomplete"
    assert cogs["amount"] == 50.0
    assert cogs["metadata"]["cost_completeness_pct"] == 50.0
    assert result["known_cost_subtotal"] == 50.0
    assert result["data_quality"]["status"] == "incomplete"
    assert "cogs" in result["data_quality"]["missing_components"]
    assert result["contribution_profit"] is None
    assert result["contribution_margin"] is None


def test_missing_payment_method_is_missing_even_when_defaults_exist(db, store):
    _configure(
        db,
        store,
        default_payment_fee_percent=3,
        default_payment_fee_fixed=500,
    )
    _order(
        db,
        store,
        number="D1",
        amount=100000,
        lifecycle="delivered",
        payment_method=None,
        item_costs=[(1, 50000)],
    )

    result = _run(db, store)

    payment = result["components"]["payment_fees"]
    assert payment["status"] == "missing"
    assert payment["reason"] == "payment_fee_rule_missing"
    assert payment["metadata"]["unresolved_payment_methods"] == ["__missing__"]
    assert result["contribution_profit"] is None


def test_method_override_fields_fall_back_individually_to_defaults(db, store):
    _configure(
        db,
        store,
        default_payment_fee_percent=3,
        default_payment_fee_fixed=100,
        default_cod_fee_percent=4,
        payment_methods=[
            {
                "payment_method": "card",
                "fee_percent": 2,
                "fee_fixed": None,
                "is_cod": True,
                "cod_fee_percent": None,
            }
        ],
    )
    _order(
        db,
        store,
        number="D1",
        amount=10000,
        lifecycle="delivered",
        payment_method=" CARD ",
        item_costs=[(1, 2000)],
    )

    result = _run(db, store)

    assert result["components"]["payment_fees"]["amount"] == 300.0
    assert result["components"]["cod_fees"]["amount"] == 400.0
    assert result["data_quality"]["status"] == "complete"


def test_cod_is_not_guessed_from_payment_method_name(db, store):
    _configure(
        db,
        store,
        default_payment_fee_percent=2,
        payment_methods=[
            {
                "payment_method": "cash_on_delivery",
                "fee_percent": None,
                "fee_fixed": None,
                "is_cod": False,
                "cod_fee_percent": 9,
            }
        ],
    )
    _order(
        db,
        store,
        number="D1",
        amount=10000,
        lifecycle="delivered",
        payment_method="cash_on_delivery",
        item_costs=[(1, 1000)],
    )

    result = _run(db, store)

    assert result["components"]["payment_fees"]["amount"] == 200.0
    assert result["components"]["cod_fees"]["status"] == "not_applicable"
    assert result["components"]["cod_fees"]["amount"] == 0.0


def test_missing_return_cost_only_matters_when_returns_exist(db, store):
    _configure(db, store, return_logistics_cost=None)
    no_returns = _run(db, store)
    assert no_returns["components"]["reverse_logistics"]["status"] == "not_applicable"

    _order(
        db,
        store,
        number="R1",
        amount=10000,
        lifecycle="returned",
        item_costs=[(1, 3000)],
    )
    with_return = _run(db, store)
    assert with_return["components"]["reverse_logistics"]["status"] == "missing"
    assert with_return["components"]["reverse_logistics"]["reason"] == "return_cost_missing"
    assert with_return["contribution_profit"] is None


def test_complete_zero_revenue_period_can_have_negative_profit_and_null_margin(
    db, store, monkeypatch
):
    _configure(
        db,
        store,
        outbound_shipping_cost=10,
        return_logistics_cost=20,
    )
    _order(
        db,
        store,
        number="R1",
        amount=1000,
        lifecycle="returned",
        item_costs=[(1, 500)],
    )
    monkeypatch.setattr(
        unit_engine,
        "resolve_meta_ad_spend",
        lambda *_args, **_kwargs: {
            "amount": Decimal("100"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        },
    )

    result = _run(db, store)

    assert result["data_quality"]["status"] == "complete"
    assert result["contribution_profit"] == -130.0
    assert result["contribution_margin"] is None


def test_meta_missing_forces_final_contribution_missing(db, store, monkeypatch):
    _configure(db, store)
    monkeypatch.setattr(
        unit_engine,
        "resolve_meta_ad_spend",
        lambda *_args, **_kwargs: {
            "amount": None,
            "source": "meta_ads",
            "status": "missing",
            "reason": "meta_not_connected",
            "metadata": {},
        },
    )

    result = _run(db, store)

    assert result["components"]["ad_spend"]["source"] == "missing"
    assert result["components"]["ad_spend"]["reason"] == "meta_not_connected"
    assert result["contribution_profit"] is None
    assert result["contribution_margin"] is None


def test_numeric_outputs_never_emit_nan_or_infinity(db, store):
    _configure(db, store)
    _order(
        db,
        store,
        number="D1",
        amount=1000,
        lifecycle="delivered",
        item_costs=[(1, 200)],
    )

    result = _run(db, store)

    for value in (
        result["recognized_revenue"],
        result["gross_profit"],
        result["known_cost_subtotal"],
        result["contribution_profit"],
        result["contribution_margin"],
    ):
        if value is not None:
            assert math.isfinite(value)
