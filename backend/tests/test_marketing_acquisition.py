"""Tests for Diaglob's customer-acquisition attribution service."""
import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.model_domains.marketing import MarketingRegistrationAttribution
from app.services.marketing_acquisition import (
    build_meta_conversion_event,
    record_registration_conversion,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_marketing_acquisition.db"
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
def setup_db(monkeypatch):
    monkeypatch.delenv("META_PIXEL_ID", raising=False)
    monkeypatch.delenv("META_CONVERSIONS_API_ACCESS_TOKEN", raising=False)
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


def test_build_meta_conversion_event_hashes_email_and_reuses_event_id():
    event = build_meta_conversion_event(
        event_id="complete_registration:test-1",
        email=" Merchant@Example.com ",
        user_id=42,
        event_source_url="https://diaglob.tech/register",
        first_touch=None,
        last_touch={
            "fbclid": "abc123",
            "captured_at": "2026-10-03T12:00:00Z",
        },
        fbp="fb.1.123.456",
        fbc=None,
        client_ip="203.0.113.10",
        client_user_agent="Diaglob Test",
        event_time=1234567890,
    )

    assert event["event_name"] == "CompleteRegistration"
    assert event["event_id"] == "complete_registration:test-1"
    assert event["event_time"] == 1234567890
    assert event["user_data"]["em"] == [
        hashlib.sha256(b"merchant@example.com").hexdigest()
    ]
    assert event["user_data"]["fbp"] == "fb.1.123.456"
    assert event["user_data"]["fbc"].endswith(".abc123")
    assert event["user_data"]["client_ip_address"] == "203.0.113.10"


def test_registration_attribution_requires_advertising_consent(db):
    result = record_registration_conversion(
        db,
        organization_id=1,
        user_id=1,
        email="merchant@example.com",
        marketing_context={
            "consented": False,
            "event_id": "complete_registration:no-consent",
        },
    )

    assert result == {
        "recorded": False,
        "reason": "advertising_consent_missing",
    }
    assert db.query(MarketingRegistrationAttribution).count() == 0


def test_registration_attribution_persists_campaign_and_deduplicates(db):
    context = {
        "consented": True,
        "event_id": "complete_registration:dedupe",
        "event_source_url": "https://diaglob.tech/register",
        "first_touch": {
            "source": "meta",
            "medium": "paid_social",
            "campaign": "launch_colombia",
            "content": "chaos_tools_v1",
            "fbclid": "click-123",
            "landing_path": "/?utm_source=meta",
            "captured_at": "2026-10-03T12:00:00Z",
        },
        "last_touch": {
            "source": "meta",
            "medium": "paid_social",
            "campaign": "launch_colombia",
            "content": "product_demo_v1",
            "fbclid": "click-123",
            "landing_path": "/register",
            "captured_at": "2026-10-03T12:05:00Z",
        },
    }

    first = record_registration_conversion(
        db,
        organization_id=7,
        user_id=9,
        email="merchant@example.com",
        marketing_context=context,
    )
    second = record_registration_conversion(
        db,
        organization_id=7,
        user_id=9,
        email="merchant@example.com",
        marketing_context=context,
    )

    assert first["recorded"] is True
    assert first["meta_delivery_status"] == "disabled"
    assert second["deduplicated"] is True

    row = db.query(MarketingRegistrationAttribution).one()
    assert row.source == "meta"
    assert row.medium == "paid_social"
    assert row.campaign == "launch_colombia"
    assert row.content == "product_demo_v1"
    assert row.fbclid == "click-123"
