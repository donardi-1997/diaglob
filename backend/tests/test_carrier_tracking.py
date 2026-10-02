"""Multi-carrier tracking service tests."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.shipments import CarrierConnection, Shipment, TrackingEvent
from app.models import Organization, Store
from app.services.carrier_registry import (
    detect_carrier,
    normalize_carrier_status,
)
from app.services.carrier_tracking import (
    CarrierConnectionNotFound,
    connect_carrier,
    ingest_carrier_webhook,
    list_store_carriers,
    register_carrier_shipment,
    sync_registered_shipment,
)


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    return engine, session


def _seed(session):
    organization = Organization(
        name="Carrier Org",
        slug="carrier-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    session.add(organization)
    session.flush()
    store = Store(
        organization_id=organization.id,
        name="Carrier Store",
        slug="carrier-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    session.add(store)
    session.commit()
    return organization, store


def test_colombia_carrier_detection_is_conservative():
    result = detect_carrier(carrier_hint="Coordinadora Mercantil")
    assert result["carrier_key"] == "coordinadora"
    assert result["confidence"] == 1.0

    result = detect_carrier(carrier_hint="INTER RAPIDÍSIMO")
    assert result["carrier_key"] == "interrapidisimo"

    ambiguous = detect_carrier(tracking_number="12345678901")
    assert ambiguous["carrier_key"] is None
    assert ambiguous["source"] == "tracking_number_ambiguous"


def test_spanish_carrier_status_normalization():
    assert normalize_carrier_status(None, "En reparto") == "OUT_FOR_DELIVERY"
    assert normalize_carrier_status(None, "Entregado al destinatario") == "DELIVERED"
    assert normalize_carrier_status(None, "No entregado") == "FAILED"
    assert normalize_carrier_status(None, "Novedad de dirección incorrecta") == "EXCEPTION"
    assert normalize_carrier_status(None, "En tránsito a ciudad destino") == "IN_TRANSIT"
    assert normalize_carrier_status("RETURNED") == "RETURNED"


def test_connect_carrier_returns_one_time_webhook_token(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.diaglob.tech")
    engine, session = _db()
    try:
        org, store = _seed(session)
        result = connect_carrier(
            session,
            org.id,
            store.id,
            "coordinadora",
        )

        assert result["ok"] is True
        assert result["carrier"]["key"] == "coordinadora"
        assert result["webhook_token"]
        assert result["webhook_token"] in result["callback_url"]

        connection = session.query(CarrierConnection).one()
        assert connection.status == "connected"
        assert connection.webhook_secret_hash != result["webhook_token"]
        assert len(connection.webhook_secret_hash) == 64

        listed = list_store_carriers(session, org.id, store.id)
        by_key = {item["key"]: item for item in listed["items"]}
        assert by_key["coordinadora"]["connection"]["status"] == "connected"
        assert by_key["servientrega"]["connection"] is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_carrier_webhook_updates_shipment_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.diaglob.tech")
    engine, session = _db()
    try:
        org, store = _seed(session)
        connected = connect_carrier(
            session,
            org.id,
            store.id,
            "coordinadora",
        )
        registered = register_carrier_shipment(
            session,
            org.id,
            store.id,
            carrier_key="coordinadora",
            tracking_number="12345678901",
        )
        shipment_id = registered["shipment"]["id"]

        payload = {
            "tracking_number": "12345678901",
            "status_label": "En reparto",
            "source_event_id": "coord-event-1",
            "event_at": "2026-10-02T15:00:00Z",
            "location": "Medellín",
            "description": "En ruta para entrega",
            "destination_country_code": "CO",
        }
        first = ingest_carrier_webhook(
            session,
            "coordinadora",
            connected["webhook_token"],
            payload,
        )
        assert first["duplicate"] is False
        assert first["shipment_id"] == shipment_id
        assert first["status"] == "OUT_FOR_DELIVERY"

        shipment = session.get(Shipment, shipment_id)
        assert shipment.normalized_status == "OUT_FOR_DELIVERY"
        assert shipment.last_mile_carrier == "Coordinadora"
        assert shipment.destination_country_code == "CO"
        assert shipment.last_event_at is not None
        assert session.query(TrackingEvent).count() == 1

        duplicate = ingest_carrier_webhook(
            session,
            "coordinadora",
            connected["webhook_token"],
            payload,
        )
        assert duplicate["duplicate"] is True
        assert session.query(TrackingEvent).count() == 1

        delivered = ingest_carrier_webhook(
            session,
            "coordinadora",
            connected["webhook_token"],
            {
                **payload,
                "status_label": "Entregado al destinatario",
                "source_event_id": "coord-event-2",
                "event_at": "2026-10-02T17:30:00Z",
            },
        )
        assert delivered["status"] == "DELIVERED"
        session.refresh(shipment)
        assert shipment.delivered_at is not None
        assert session.query(TrackingEvent).count() == 2
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_webhook_token_cannot_update_another_carrier(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.diaglob.tech")
    engine, session = _db()
    try:
        org, store = _seed(session)
        connected = connect_carrier(
            session,
            org.id,
            store.id,
            "coordinadora",
        )
        register_carrier_shipment(
            session,
            org.id,
            store.id,
            carrier_key="servientrega",
            tracking_number="SERVI-1",
        )

        try:
            ingest_carrier_webhook(
                session,
                "servientrega",
                connected["webhook_token"],
                {
                    "tracking_number": "SERVI-1",
                    "status": "DELIVERED",
                },
            )
        except CarrierConnectionNotFound as exc:
            assert str(exc) == "CARRIER_WEBHOOK_UNAUTHORIZED"
        else:
            raise AssertionError("Cross-carrier webhook token must be rejected")
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_non_cj_registered_shipment_uses_push_updates(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.diaglob.tech")
    engine, session = _db()
    try:
        org, store = _seed(session)
        registered = register_carrier_shipment(
            session,
            org.id,
            store.id,
            carrier_key="tcc",
            tracking_number="TCC-100",
        )
        result = sync_registered_shipment(
            session,
            org.id,
            store.id,
            registered["shipment"]["id"],
        )
        assert result["available"] is True
        assert result["sync_mode"] == "webhook"
        assert result["direct_sync"] is False
        assert result["reason"] == "PUSH_UPDATES_REQUIRED"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
