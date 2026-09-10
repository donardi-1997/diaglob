from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.ai_usage import AiUsageCreditGrant
from app.models import Organization
from app.services import ai_usage_service
from app.services.ai_usage_packages import (
    fulfill_ai_usage_package_transaction,
    serialize_ai_usage_packages,
)
from app.services.ai_usage_service import (
    acquire_ai_capacity,
    get_ai_usage_window,
    refund_ai_capacity,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
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


def make_org(db, plan="starter"):
    organization = Organization(
        name="AI Packages Org",
        slug="ai-packages-org",
        plan=plan,
        subscription_status="active",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def test_current_usage_window_is_calendar_month():
    start, end = get_ai_usage_window(datetime(2026, 12, 18, 15, 40))
    assert start == datetime(2026, 12, 1)
    assert end == datetime(2027, 1, 1)


def test_package_catalog_exposes_configuration(monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    monkeypatch.delenv("PADDLE_PRICE_AI_5000", raising=False)
    monkeypatch.delenv("PADDLE_PRICE_AI_10000", raising=False)

    packages = {item["key"]: item for item in serialize_ai_usage_packages()}

    assert packages["ai_1000"]["responses"] == 1000
    assert packages["ai_1000"]["price_usd"] == "5.00"
    assert packages["ai_1000"]["configured"] is True
    assert packages["ai_5000"]["configured"] is False


def test_completed_transaction_grants_package_once(db, monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    organization = make_org(db)
    data = {
        "id": "txn_ai_123",
        "currency_code": "USD",
        "custom_data": {
            "purchase_type": "ai_usage_package",
            "organization_id": str(organization.id),
            "package_key": "ai_1000",
        },
        "items": [{"price": {"id": "pri_ai_1000"}, "quantity": 1}],
        "details": {"totals": {"grand_total": "500", "currency_code": "USD"}},
    }

    first = fulfill_ai_usage_package_transaction(
        db, organization.id, data, datetime(2026, 9, 10, 12)
    )
    second = fulfill_ai_usage_package_transaction(
        db, organization.id, data, datetime(2026, 9, 10, 12)
    )

    assert first["credited"] is True
    assert second["duplicate"] is True

    grants = db.query(AiUsageCreditGrant).all()
    assert len(grants) == 1
    assert grants[0].responses_total == 1000
    assert grants[0].responses_remaining == 1000
    assert grants[0].amount_minor == 500


def test_extra_capacity_is_reserved_and_can_be_refunded(db, monkeypatch):
    organization = make_org(db)
    grant = AiUsageCreditGrant(
        organization_id=organization.id,
        package_key="ai_1000",
        responses_total=2,
        responses_remaining=2,
        provider="paddle",
        provider_transaction_id="txn_ai_capacity",
        status="active",
    )
    db.add(grant)
    db.commit()

    monkeypatch.setattr(
        ai_usage_service,
        "_count_ai_responses",
        lambda *_args, **_kwargs: 1000,
    )

    reservation = acquire_ai_capacity(db, organization.id)
    db.refresh(grant)

    assert reservation["available"] is True
    assert reservation["source"] == "extra"
    assert grant.responses_remaining == 1

    refund_ai_capacity(db, reservation)
    db.refresh(grant)
    assert grant.responses_remaining == 2
    assert grant.status == "active"


def test_extra_capacity_stops_when_balance_is_empty(db, monkeypatch):
    organization = make_org(db)
    monkeypatch.setattr(
        ai_usage_service,
        "_count_ai_responses",
        lambda *_args, **_kwargs: 1000,
    )

    reservation = acquire_ai_capacity(db, organization.id)

    assert reservation["available"] is False
    assert reservation["reason"] == "ai_usage_exhausted"


def test_included_capacity_is_used_before_extra_balance(db, monkeypatch):
    organization = make_org(db)
    grant = AiUsageCreditGrant(
        organization_id=organization.id,
        package_key="ai_1000",
        responses_total=10,
        responses_remaining=10,
        provider="paddle",
        provider_transaction_id="txn_ai_included_first",
        status="active",
    )
    db.add(grant)
    db.commit()

    monkeypatch.setattr(
        ai_usage_service,
        "_count_ai_responses",
        lambda *_args, **_kwargs: 999,
    )

    reservation = acquire_ai_capacity(db, organization.id)
    db.refresh(grant)

    assert reservation["source"] == "included"
    assert grant.responses_remaining == 10


def test_completed_transaction_rejects_wrong_package_price(db, monkeypatch):
    organization = make_org(db)
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")

    result = fulfill_ai_usage_package_transaction(
        db,
        organization.id,
        {
            "id": "txn_ai_wrong_price",
            "custom_data": {"package_key": "ai_1000"},
            "items": [{"price": {"id": "pri_other"}, "quantity": 1}],
        },
    )

    assert result["ignored"] is True
    assert result["reason"] == "package_price_mismatch"
    assert db.query(AiUsageCreditGrant).count() == 0


def test_completed_transaction_rejects_noncanonical_item_shape(db, monkeypatch):
    organization = make_org(db)
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")

    malformed_transactions = [
        {
            "id": "txn_ai_qty_two",
            "custom_data": {"package_key": "ai_1000"},
            "items": [{"price": {"id": "pri_ai_1000"}, "quantity": 2}],
        },
        {
            "id": "txn_ai_extra_item",
            "custom_data": {"package_key": "ai_1000"},
            "items": [
                {"price": {"id": "pri_ai_1000"}, "quantity": 1},
                {"price": {"id": "pri_other"}, "quantity": 1},
            ],
        },
    ]

    for data in malformed_transactions:
        result = fulfill_ai_usage_package_transaction(db, organization.id, data)
        assert result["ignored"] is True
        assert result["reason"] == "package_price_mismatch"

    assert db.query(AiUsageCreditGrant).count() == 0
