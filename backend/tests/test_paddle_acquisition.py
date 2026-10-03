"""Tests for paid acquisition hooks in Paddle billing transitions."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Organization
from app.services.paddle_webhooks import process_transaction_event

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_paddle_acquisition.db"
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


def test_first_paid_transaction_emits_subscribe_once(db, monkeypatch):
    organization = Organization(
        name="Trial Merchant",
        slug="trial-merchant",
        plan="trial",
        subscription_status="trialing",
        billing_subscription_id="sub_123",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)

    conversions = []
    monkeypatch.setattr(
        "app.services.paddle_webhooks.record_lifecycle_conversion",
        lambda _db, **kwargs: conversions.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.product_analytics.track_checkout_completed",
        lambda **_kwargs: None,
    )

    occurred_at = datetime(2026, 10, 3, 18, 0, 0)
    process_transaction_event(
        organization,
        event_id="evt_first_paid",
        occurred_at=occurred_at,
        plan_key="starter",
        data={"id": "txn_first_paid"},
        db=db,
    )

    assert organization.plan == "starter"
    assert len(conversions) == 1
    assert conversions[0]["event_name"] == "Subscribe"
    assert conversions[0]["event_key"] == f"subscribe:{organization.id}"
    assert conversions[0]["provider_event_id"] == "txn_first_paid"

    process_transaction_event(
        organization,
        event_id="evt_renewal",
        occurred_at=datetime(2026, 11, 3, 18, 0, 0),
        plan_key="starter",
        data={"id": "txn_renewal"},
        db=db,
    )

    assert len(conversions) == 1
