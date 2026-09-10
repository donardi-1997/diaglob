"""Tests for privacy-preserving cross-organization customer risk signals."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.customer_risk import CustomerRiskReport
from app.models import Customer, CustomerStoreProfile, Order, Organization, Store, User
from app.services.customer_risk_service import (
    dismiss_current_organization_report,
    enrich_order_payloads,
    get_customer_risk_summary,
    normalize_phone,
    report_customer,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("CUSTOMER_RISK_HMAC_SECRET", "test-risk-secret-that-is-not-production")
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


def _seed_org(db, *, slug: str, email: str, phone: str = "+57 300 555 0101"):
    org = Organization(
        name=f"Org {slug}",
        slug=slug,
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name=f"Store {slug}",
        slug=f"store-{slug}",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    user = User(email=f"owner-{slug}@example.com", name=f"Owner {slug}")
    db.add_all([store, user])
    db.flush()
    customer = Customer(
        organization_id=org.id,
        name=f"Customer {slug}",
        phone=phone,
        email=email,
        country_code="CO",
    )
    db.add(customer)
    db.flush()
    db.add(
        CustomerStoreProfile(
            organization_id=org.id,
            customer_id=customer.id,
            store_id=store.id,
            orders_count=0,
            total_spent=0,
            currency="COP",
        )
    )
    db.commit()
    return org, store, user, customer


def test_report_is_visible_cross_organization_without_reporter_private_data(db):
    org_a, store_a, user_a, customer_a = _seed_org(
        db,
        slug="a",
        email="same.person@example.com",
    )
    org_b, _, _, customer_b = _seed_org(
        db,
        slug="b",
        email="SAME.PERSON@example.com",
        phone="3005550101",
    )

    own = report_customer(
        db=db,
        organization_id=org_a.id,
        reporter_user_id=user_a.id,
        customer_id=customer_a.id,
        reporter_store_id=store_a.id,
        reason="suspected_fraud",
        notes="Private internal notes",
        evidence_reference="private-evidence-123",
    )
    assert own["reported_by_current_organization"] is True
    assert own["current_organization_report"]["notes"] == "Private internal notes"

    shared = get_customer_risk_summary(
        db=db,
        organization_id=org_b.id,
        customer_id=customer_b.id,
    )
    assert shared["alert"] is True
    assert shared["severity"] == "elevated"
    assert shared["reporting_organizations"] == 1
    assert shared["external_reporting_organizations"] == 1
    assert shared["pending_reports"] == 1
    assert shared["reason_counts"] == {"suspected_fraud": 1}
    assert shared["current_organization_report"] is None
    assert "reporter_organization_id" not in shared
    assert "notes" not in shared
    assert "evidence_reference" not in shared


def test_same_organization_cannot_inflate_report_count(db):
    org, store, user, customer = _seed_org(
        db,
        slug="dedupe",
        email="dedupe@example.com",
    )

    report_customer(
        db=db,
        organization_id=org.id,
        reporter_user_id=user.id,
        customer_id=customer.id,
        reporter_store_id=store.id,
        reason="payment_abuse",
    )
    second = report_customer(
        db=db,
        organization_id=org.id,
        reporter_user_id=user.id,
        customer_id=customer.id,
        reporter_store_id=store.id,
        reason="delivery_claim",
        notes="Updated context",
    )

    assert db.query(CustomerRiskReport).count() == 1
    assert second["reporting_organizations"] == 1
    assert second["reason_counts"] == {"delivery_claim": 1}
    assert second["current_organization_report"]["notes"] == "Updated context"


def test_two_independent_organizations_raise_high_caution(db):
    org_a, store_a, user_a, customer_a = _seed_org(
        db,
        slug="risk-a",
        email="risk@example.com",
    )
    org_b, store_b, user_b, customer_b = _seed_org(
        db,
        slug="risk-b",
        email="risk@example.com",
    )
    org_c, _, _, customer_c = _seed_org(
        db,
        slug="risk-c",
        email="risk@example.com",
    )

    for org, store, user, customer, reason in (
        (org_a, store_a, user_a, customer_a, "suspected_fraud"),
        (org_b, store_b, user_b, customer_b, "payment_abuse"),
    ):
        report_customer(
            db=db,
            organization_id=org.id,
            reporter_user_id=user.id,
            customer_id=customer.id,
            reporter_store_id=store.id,
            reason=reason,
        )

    summary = get_customer_risk_summary(
        db=db,
        organization_id=org_c.id,
        customer_id=customer_c.id,
    )
    assert summary["severity"] == "high"
    assert summary["reporting_organizations"] == 2
    assert summary["external_reporting_organizations"] == 2


def test_dismissed_report_stops_shared_alert(db):
    org_a, store_a, user_a, customer_a = _seed_org(
        db,
        slug="dismiss-a",
        email="dismiss@example.com",
    )
    org_b, _, _, customer_b = _seed_org(
        db,
        slug="dismiss-b",
        email="dismiss@example.com",
    )
    report_customer(
        db=db,
        organization_id=org_a.id,
        reporter_user_id=user_a.id,
        customer_id=customer_a.id,
        reporter_store_id=store_a.id,
        reason="other",
    )

    dismissed = dismiss_current_organization_report(
        db=db,
        organization_id=org_a.id,
        reporter_user_id=user_a.id,
        customer_id=customer_a.id,
    )
    assert dismissed["alert"] is False

    shared = get_customer_risk_summary(
        db=db,
        organization_id=org_b.id,
        customer_id=customer_b.id,
    )
    assert shared["alert"] is False
    assert shared["reporting_organizations"] == 0


def test_phone_normalization_and_order_enrichment(db):
    assert normalize_phone("+57 300-555-0101", "CO") == "573005550101"
    assert normalize_phone("300 555 0101", "CO") == "573005550101"

    org_a, store_a, user_a, customer_a = _seed_org(
        db,
        slug="order-a",
        email="order-a@example.com",
    )
    org_b, store_b, _, customer_b = _seed_org(
        db,
        slug="order-b",
        email="different@example.com",
        phone="3005550101",
    )
    report_customer(
        db=db,
        organization_id=org_a.id,
        reporter_user_id=user_a.id,
        customer_id=customer_a.id,
        reporter_store_id=store_a.id,
        reason="identity_mismatch",
    )

    order = Order(
        organization_id=org_b.id,
        store_id=store_b.id,
        customer_id=customer_b.id,
        order_number="RISK-1",
        total_amount=100,
        currency="COP",
        source="shopify",
    )
    db.add(order)
    db.commit()

    enriched = enrich_order_payloads(
        db=db,
        organization_id=org_b.id,
        store_id=store_b.id,
        payloads=[{"id": order.id, "order_number": order.order_number}],
    )
    assert enriched[0]["customer_id"] == customer_b.id
    assert enriched[0]["customer_risk"]["alert"] is True
    assert enriched[0]["customer_risk"]["external_reporting_organizations"] == 1
