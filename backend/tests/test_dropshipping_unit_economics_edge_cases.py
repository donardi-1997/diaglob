"""Edge-case contracts for deterministic Unit Economics."""

import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Order, Organization, Store
from app.services.unit_economics_config_service import replace_unit_economics_config
import app.services.dropshipping_unit_economics as unit_engine
from app.services.dropshipping_unit_economics import get_store_unit_economics


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_unit_economics_edge.db"
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
        os.remove("./test_dropshipping_unit_economics_edge.db")
    except FileNotFoundError:
        pass


def test_delivered_order_without_items_blocks_final_contribution(monkeypatch):
    db = TestingSessionLocal()
    try:
        organization = Organization(
            name="Unit Edge Org",
            slug="unit-edge-org",
            plan="growth",
            subscription_status="active",
        )
        db.add(organization)
        db.flush()
        store = Store(
            organization_id=organization.id,
            name="Unit Edge Store",
            slug="unit-edge-store",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            default_language="es",
        )
        db.add(store)
        db.flush()
        replace_unit_economics_config(
            db,
            organization.id,
            store.id,
            {
                "outbound_shipping_cost": 0,
                "return_logistics_cost": 0,
                "default_payment_fee_percent": 0,
                "default_payment_fee_fixed": 0,
                "default_cod_fee_percent": 0,
                "payment_methods": [],
            },
        )
        order = Order(
            organization_id=organization.id,
            store_id=store.id,
            order_number="NO-ITEMS",
            total_amount=Decimal("100000"),
            currency="COP",
            lifecycle_status="delivered",
            payment_method="card",
            created_at=datetime(2026, 9, 5, 12, 0, 0),
        )
        db.add(order)
        db.commit()

        monkeypatch.setattr(
            unit_engine,
            "resolve_meta_ad_spend",
            lambda *_args, **_kwargs: {
                "amount": Decimal("0"),
                "source": "meta_ads",
                "status": "actual",
                "reason": None,
                "metadata": {},
            },
        )

        result = get_store_unit_economics(
            db,
            organization.id,
            store,
            datetime(2026, 9, 1),
            datetime(2026, 9, 12),
        )

        cogs = result["components"]["cogs"]
        assert cogs["status"] == "missing"
        assert cogs["reason"] == "cogs_incomplete"
        assert cogs["amount"] == 0.0
        assert cogs["metadata"]["cost_completeness_pct"] == 0.0
        assert result["data_quality"]["status"] == "incomplete"
        assert result["contribution_profit"] is None
        assert result["contribution_margin"] is None
    finally:
        db.rollback()
        db.close()
