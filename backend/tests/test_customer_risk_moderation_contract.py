"""Contract-level coverage for Customer Risk Moderation V2.

Keeps the second-stage governance behavior explicit: reporter writes are
rate-limited and audited, disputes do not disclose reporter identity to tenant
callers, and only a platform moderation decision changes shared report status.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.customer_risk import (
    CustomerRiskDispute,
    CustomerRiskDisputeEvent,
    CustomerRiskReport,
    CustomerRiskReportEvent,
)
from app.models import Customer, CustomerStoreProfile, Organization, Store, User
from app.services.customer_risk_moderation_service import resolve_customer_risk_dispute
from app.services.customer_risk_service import (
    get_customer_risk_summary,
    report_customer,
    submit_customer_risk_dispute,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv(
        "CUSTOMER_RISK_HMAC_SECRET",
        "test-risk-secret-that-is-not-production",
    )
    monkeypatch.setenv("CUSTOMER_RISK_REPORT_LIMIT_24H", "25")
    monkeypatch.setenv("CUSTOMER_RISK_DISPUTE_LIMIT_24H", "10")
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed(db, slug: str, email: str):
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
    admin = User(email=f"admin-{slug}@example.com", name=f"Admin {slug}")
    db.add_all([store, user, admin])
    db.flush()
    customer = Customer(
        organization_id=org.id,
        name=f"Customer {slug}",
        phone="3005550101",
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
    return org, store, user, admin, customer


def test_accepted_dispute_marks_external_signal_disputed_and_audits_both_sides(db):
    reporter_org, reporter_store, reporter_user, _, reporter_customer = _seed(
        db, "reporter", "same@example.com"
    )
    requester_org, requester_store, requester_user, admin_user, requester_customer = _seed(
        db, "requester", "same@example.com"
    )

    report_customer(
        db=db,
        organization_id=reporter_org.id,
        reporter_user_id=reporter_user.id,
        customer_id=reporter_customer.id,
        reporter_store_id=reporter_store.id,
        reason="payment_abuse",
        notes="Internal only",
        evidence_reference="ORDER-123",
    )

    disputed = submit_customer_risk_dispute(
        db=db,
        organization_id=requester_org.id,
        requester_user_id=requester_user.id,
        customer_id=requester_customer.id,
        requester_store_id=requester_store.id,
        statement="The shared signal appears to refer to a transaction that was resolved.",
        evidence_reference="CASE-456",
    )
    dispute_id = disputed["dispute"]["id"]

    # Tenant summary remains aggregate; reporter-private fields never leak.
    summary = get_customer_risk_summary(
        db=db,
        organization_id=requester_org.id,
        customer_id=requester_customer.id,
    )
    assert summary["alert"] is True
    assert summary["current_organization_report"] is None
    assert "reporter_organization_id" not in summary

    resolve_customer_risk_dispute(
        db,
        dispute_id=dispute_id,
        admin_user_id=admin_user.id,
        outcome="accepted",
        note="Evidence supports opening a formal dispute on the shared signal.",
    )

    report = db.query(CustomerRiskReport).one()
    dispute = db.query(CustomerRiskDispute).one()
    assert report.status == "disputed"
    assert dispute.status == "accepted"
    assert db.query(CustomerRiskReportEvent).filter_by(
        report_id=report.id,
        action="moderation_disputed",
    ).count() == 1
    assert db.query(CustomerRiskDisputeEvent).filter_by(
        dispute_id=dispute.id,
        action="dispute_accepted",
    ).count() == 1
