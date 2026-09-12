"""Unit Economics Meta Ads spend resolution contract."""

import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.integrations.meta_ads.client import MetaAdsError
from app.models import MetaAdsConnection, Organization, Store
import app.services.unit_economics_meta as meta_service
from app.services.unit_economics_meta import resolve_meta_ad_spend


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit_economics_meta.db"
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
        os.remove("./test_unit_economics_meta.db")
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
        name="Unit Meta Org",
        slug="unit-meta-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()
    store = Store(
        organization_id=organization.id,
        name="Unit Meta Store",
        slug="unit-meta-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def _connect_meta(db, store, *, currency="COP", status="connected"):
    connection = MetaAdsConnection(
        organization_id=store.organization_id,
        store_id=store.id,
        external_account_id="act_123",
        external_account_name="Diaglob Ads",
        account_currency=currency,
        account_timezone="America/Bogota",
        access_token_encrypted="encrypted-token",
        status=status,
    )
    db.add(connection)
    db.commit()
    return connection


def _bounded_range():
    return datetime(2026, 9, 1), datetime(2026, 9, 12)


def test_not_connected_is_missing(db, store):
    date_from, date_to = _bounded_range()
    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["source"] == "meta_ads"
    assert result["reason"] == "meta_not_connected"
    assert result["amount"] is None


def test_unbounded_range_is_missing(db, store):
    _connect_meta(db, store)

    result = resolve_meta_ad_spend(
        db, store.organization_id, store, None, datetime(2026, 9, 12)
    )

    assert result["status"] == "missing"
    assert result["reason"] == "bounded_date_range_required"
    assert result["amount"] is None


def test_unknown_provider_currency_is_missing(db, store):
    _connect_meta(db, store, currency=None)
    date_from, date_to = _bounded_range()

    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["reason"] == "currency_unknown"
    assert result["amount"] is None


def test_currency_mismatch_is_missing(db, store):
    _connect_meta(db, store, currency="USD")
    date_from, date_to = _bounded_range()

    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["reason"] == "currency_mismatch"
    assert result["amount"] is None
    assert result["metadata"]["store_currency"] == "COP"
    assert result["metadata"]["provider_currency"] == "USD"


def test_decrypt_failure_is_missing(db, store, monkeypatch):
    _connect_meta(db, store)
    date_from, date_to = _bounded_range()

    def fail_decrypt(_value):
        raise ValueError("bad token")

    monkeypatch.setattr(meta_service, "decrypt_secret", fail_decrypt)
    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["reason"] == "credentials_unavailable"
    assert result["amount"] is None


def test_provider_error_is_missing(db, store, monkeypatch):
    _connect_meta(db, store)
    date_from, date_to = _bounded_range()
    monkeypatch.setattr(meta_service, "decrypt_secret", lambda _value: "token")

    def fail_provider(*_args, **_kwargs):
        raise MetaAdsError("provider failed", "META_TEMPORARY_ERROR")

    monkeypatch.setattr(meta_service, "get_insights", fail_provider)
    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["reason"] == "provider_error"
    assert result["amount"] is None
    assert result["metadata"]["provider_error_code"] == "META_TEMPORARY_ERROR"


def test_successful_no_spend_is_actual_zero(db, store, monkeypatch):
    _connect_meta(db, store)
    date_from, date_to = _bounded_range()
    monkeypatch.setattr(meta_service, "decrypt_secret", lambda _value: "token")
    monkeypatch.setattr(meta_service, "get_insights", lambda *_args, **_kwargs: [])

    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "actual"
    assert result["reason"] is None
    assert result["amount"] == Decimal("0")


def test_successful_spend_uses_exact_period_and_maps_exclusive_end(
    db, store, monkeypatch
):
    _connect_meta(db, store)
    date_from, date_to = _bounded_range()
    monkeypatch.setattr(meta_service, "decrypt_secret", lambda _value: "token")
    captured = {}

    def fake_get_insights(token, account_id, **kwargs):
        captured["token"] = token
        captured["account_id"] = account_id
        captured.update(kwargs)
        return [{"spend": "12345.67", "impressions": "9", "clicks": "2"}]

    monkeypatch.setattr(meta_service, "get_insights", fake_get_insights)
    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "actual"
    assert result["amount"] == Decimal("12345.67")
    assert result["metadata"]["provider_currency"] == "COP"
    assert captured["token"] == "token"
    assert captured["account_id"] == "act_123"
    assert captured["time_range"] == {
        "since": "2026-09-01",
        "until": "2026-09-11",
    }
    assert captured.get("date_preset") is None


def test_malformed_provider_spend_is_missing_not_actual_zero(db, store, monkeypatch):
    _connect_meta(db, store)
    date_from, date_to = _bounded_range()
    monkeypatch.setattr(meta_service, "decrypt_secret", lambda _value: "token")
    monkeypatch.setattr(
        meta_service,
        "get_insights",
        lambda *_args, **_kwargs: [{"spend": "not-a-number"}],
    )

    result = resolve_meta_ad_spend(
        db, store.organization_id, store, date_from, date_to
    )

    assert result["status"] == "missing"
    assert result["reason"] == "provider_error"
    assert result["amount"] is None
    assert result["metadata"]["invalid_spend_row"] == 0
