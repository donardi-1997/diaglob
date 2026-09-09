from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    CommerceConnection,
    GoogleConnection,
    Organization,
    PaymentConnection,
    Store,
    User,
)
from app.services.operations_integrations import (
    get_dynamic_operations_summary,
    get_operations_integrations,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_org_store(
    db,
    *,
    org_id: int,
    store_id: int,
    country: str,
    currency: str,
):
    db.add(
        Organization(
            id=org_id,
            name=f"Org {org_id}",
            slug=f"org-{org_id}",
            plan="growth",
        )
    )
    db.add(
        Store(
            id=store_id,
            organization_id=org_id,
            name=f"Store {store_id}",
            slug=f"store-{store_id}",
            country_code=country,
            currency=currency,
            timezone="UTC",
            active=True,
        )
    )
    db.commit()


def test_brazil_exposes_mercado_pago_pix_not_nequi():
    db = _session()
    try:
        _seed_org_store(
            db,
            org_id=1,
            store_id=1,
            country="BR",
            currency="BRL",
        )

        integrations = get_operations_integrations(db, 1, 1)
        payments = {
            item["provider"]: item
            for item in integrations
            if item["category"] == "payments"
        }

        assert "mercado_pago" in payments
        assert payments["mercado_pago"]["payment_methods"] == ["pix"]
        assert payments["mercado_pago"]["connected"] is False
        assert "nequi" not in payments
    finally:
        db.close()


def test_colombia_exposes_nequi_not_mercado_pago():
    db = _session()
    try:
        _seed_org_store(
            db,
            org_id=1,
            store_id=1,
            country="CO",
            currency="COP",
        )

        integrations = get_operations_integrations(db, 1, 1)
        payment_providers = {
            item["provider"]
            for item in integrations
            if item["category"] == "payments"
        }

        assert "nequi" in payment_providers
        assert "mercado_pago" not in payment_providers
    finally:
        db.close()


def test_nuvemshop_is_dynamic_commerce_and_removes_shopify_alert():
    db = _session()
    try:
        _seed_org_store(
            db,
            org_id=1,
            store_id=1,
            country="BR",
            currency="BRL",
        )
        db.add(
            CommerceConnection(
                organization_id=1,
                store_id=1,
                provider="nuvemshop",
                external_store_url="https://example.lojavirtualnuvem.com.br",
                status="connected",
            )
        )
        db.commit()

        summary = get_dynamic_operations_summary(db, 1, 1)
        commerce = [
            item
            for item in summary["integrations"]
            if item["category"] == "commerce"
        ]
        alert_types = {alert["type"] for alert in summary["alerts"]}

        assert len(commerce) == 1
        assert commerce[0]["provider"] == "nuvemshop"
        assert commerce[0]["name"] == "Nuvemshop"
        assert commerce[0]["connected"] is True
        assert "no_shopify" not in alert_types
        assert "no_commerce" not in alert_types
    finally:
        db.close()


def test_google_is_organization_scoped_and_payment_connection_is_real():
    db = _session()
    try:
        _seed_org_store(
            db,
            org_id=1,
            store_id=1,
            country="BR",
            currency="BRL",
        )
        db.add(
            User(
                id=1,
                email="owner@example.com",
                name="Owner",
            )
        )
        db.add(
            GoogleConnection(
                organization_id=1,
                user_id=1,
                email="owner@example.com",
                access_token_encrypted="encrypted",
                status="connected",
            )
        )
        db.add(
            PaymentConnection(
                organization_id=1,
                store_id=1,
                provider="mercado_pago",
                status="connected",
                environment="sandbox",
            )
        )
        db.commit()

        integrations = get_operations_integrations(db, 1, 1)
        by_key = {item["key"]: item for item in integrations}

        assert by_key["google"]["scope"] == "organization"
        assert by_key["google"]["connected"] is True
        assert by_key["payment:mercado_pago"]["connected"] is True
    finally:
        db.close()


def test_other_tenant_integrations_are_not_exposed():
    db = _session()
    try:
        _seed_org_store(
            db,
            org_id=1,
            store_id=1,
            country="US",
            currency="USD",
        )
        _seed_org_store(
            db,
            org_id=2,
            store_id=2,
            country="BR",
            currency="BRL",
        )
        db.add(
            CommerceConnection(
                organization_id=2,
                store_id=2,
                provider="nuvemshop",
                external_store_url="https://other.lojavirtualnuvem.com.br",
                status="connected",
            )
        )
        db.commit()

        integrations = get_operations_integrations(db, 1, 1)

        assert all(item["provider"] != "nuvemshop" for item in integrations)
    finally:
        db.close()
