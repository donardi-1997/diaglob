from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    CommerceConnection,
    MetaAdsConnection,
    Organization,
    PaymentConnection,
    Store,
    WhatsAppConnection,
)
from app.services.operations_integrations import (
    get_dynamic_operations_summary,
    get_operations_integrations,
)


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    return engine, db


def _seed_store(db, *, country: str = "CO", currency: str = "COP") -> None:
    db.add(
        Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            plan="growth",
        )
    )
    db.add(
        Store(
            id=1,
            organization_id=1,
            name="Test Store",
            slug="test-store",
            country_code=country,
            currency=currency,
            timezone="UTC",
            active=True,
        )
    )
    db.commit()


def _alert_types(summary):
    return {alert["type"] for alert in summary["alerts"]}


def test_meta_ads_table_failure_does_not_break_dynamic_summary():
    engine, db = _database()
    try:
        _seed_store(db)
        MetaAdsConnection.__table__.drop(bind=engine)

        summary = get_dynamic_operations_summary(db, 1, 1)
        by_key = {item["key"]: item for item in summary["integrations"]}

        assert by_key["meta_ads"]["status"] == "degraded"
        assert by_key["meta_ads"]["connected"] is False
        assert by_key["meta_ads"]["degraded"] is True
        assert by_key["meta_ads"]["error_code"] == (
            "integration_status_unavailable"
        )
        assert by_key["payment:nequi"]["status"] == "disconnected"
        assert "integration_status_degraded" in _alert_types(summary)
    finally:
        db.close()
        engine.dispose()


def test_whatsapp_table_failure_keeps_summary_and_avoids_false_disconnect():
    engine, db = _database()
    try:
        _seed_store(db)
        WhatsAppConnection.__table__.drop(bind=engine)

        summary = get_dynamic_operations_summary(db, 1, 1)
        by_key = {item["key"]: item for item in summary["integrations"]}
        alert_types = _alert_types(summary)

        assert by_key["whatsapp"]["status"] == "degraded"
        assert by_key["whatsapp"]["connected"] is False
        assert by_key["payment:nequi"]["status"] == "disconnected"
        assert "integration_status_degraded" in alert_types
        assert "no_whatsapp" not in alert_types
    finally:
        db.close()
        engine.dispose()


def test_commerce_table_failure_does_not_claim_store_is_disconnected():
    engine, db = _database()
    try:
        _seed_store(db)
        CommerceConnection.__table__.drop(bind=engine)

        summary = get_dynamic_operations_summary(db, 1, 1)
        commerce = [
            item
            for item in summary["integrations"]
            if item["category"] == "commerce"
        ]
        alert_types = _alert_types(summary)

        assert len(commerce) == 1
        assert commerce[0]["status"] == "degraded"
        assert commerce[0]["degraded"] is True
        assert "integration_status_degraded" in alert_types
        assert "no_commerce" not in alert_types
    finally:
        db.close()
        engine.dispose()


def test_payment_table_failure_degrades_market_provider_only():
    engine, db = _database()
    try:
        _seed_store(db)
        PaymentConnection.__table__.drop(bind=engine)

        integrations = get_operations_integrations(db, 1, 1)
        by_key = {item["key"]: item for item in integrations}

        nequi = by_key["payment:nequi"]
        assert nequi["status"] == "degraded"
        assert nequi["connected"] is False
        assert nequi["degraded"] is True
        assert nequi["payment_methods"] == ["nequi_push"]
        assert by_key["whatsapp"]["status"] == "disconnected"
    finally:
        db.close()
        engine.dispose()
