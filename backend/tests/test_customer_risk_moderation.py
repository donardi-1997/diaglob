"""Phase-2 customer-risk governance regression tests."""
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
from app.services.customer_risk_governance_service import CustomerRiskRateLimitError
from app.services.customer_risk_moderation_service import (
    get_customer_risk_moderation_report,
    list_customer_risk_moderation_reports,
    moderate_customer_risk_report,
    resolve_customer_risk_dispute,
)
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
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv(
        "CUSTOMER_RISK_HMAC_SECRET",
        "phase-two-test-risk-secret-that-is-stable",
    )
    monkeypatch.delenv("CUSTOMER_RISK_REPORT_LIMIT_24H", raising=False)
    monkeypatch.delenv("CUSTOMER_RISK_DISPUTE_LIMIT_24H", raising=False)
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


def _seed_subject(db, *, slug: str, email: str = "shared@example.com"):
    organization = Organization(
        name=f"Org {slug}",
        slug=f"risk-v2-{slug}",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()

    store = Store(
        organization_id=organization.id,
        name=f"Store {slug}",
        slug=f"risk-v2-store-{slug}",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    user = User(email=f"{slug}@example.com", name=f"User {slug}")
    db.add_all([store, user])
    db.flush()

    customer = Customer(
        organization_id=organization.id,
        name=f"Customer {slug}",
        phone="3005550101",
        email=email,
        country_code="CO",
    )
    db.add(customer)
    db.flush()
    db.add(
        CustomerStoreProfile(
            organization_id=organization.id,
            customer_id=customer.id,
            store_id=store.id,
            orders_count=0,
            total_spent=0,
            currency="COP",
        )
    )
    db.commit()
    return organization, store, user, customer


def _report(db, organization, store, user, customer):
    return report_customer(
        db=db,
        organization_id=organization.id,
        reporter_user_id=user.id,
        customer_id=customer.id,
        reporter_store_id=store.id,
        reason="payment_abuse",
        notes="Customer disputed payment after delivery was documented.",
        evidence_reference="internal-order-123",
    )


def test_report_lifecycle_writes_immutable_audit_events(db):
    organization, store, user, customer = _seed_subject(db, slug="audit")

    _report(db, organization, store, user, customer)
    report_customer(
        db=db,
        organization_id=organization.id,
        reporter_user_id=user.id,
        customer_id=customer.id,
        reporter_store_id=store.id,
        reason="delivery_claim",
        notes="Updated facts after delivery review.",
    )

    report = db.query(CustomerRiskReport).one()
    events = (
        db.query(CustomerRiskReportEvent)
        .filter(CustomerRiskReportEvent.report_id == report.id)
        .order_by(CustomerRiskReportEvent.id.asc())
        .all()
    )

    assert report.status == "pending"
    assert [event.action for event in events] == [
        "report_submitted",
        "report_updated",
    ]
    assert events[0].actor_role == "reporter"
    assert events[1].from_status == "pending"
    assert events[1].to_status == "pending"


def test_platform_moderation_confirms_report_and_keeps_audit(db):
    organization, store, user, customer = _seed_subject(db, slug="moderate")
    _report(db, organization, store, user, customer)
    report = db.query(CustomerRiskReport).one()

    detail = moderate_customer_risk_report(
        db,
        report_id=report.id,
        admin_user_id=user.id,
        action="confirm",
        note="Evidence reference and delivery history were reviewed.",
    )

    assert detail["status"] == "confirmed"
    assert detail["reporter"]["reputation"]["confirmed_reports"] == 1
    assert detail["audit"][0]["action"] == "moderation_confirmed"
    assert detail["audit"][0]["actor_role"] == "platform_admin"
    assert detail["customer"]["phone_masked"].endswith("0101")
    assert "3005550101" not in detail["customer"]["phone_masked"]

    queue = list_customer_risk_moderation_reports(db, status="confirmed")
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == report.id
    assert queue["items"][0]["reporter_reputation"]["level"] == "new"


def test_external_organization_can_appeal_without_reporter_identity_leak(db):
    org_a, store_a, user_a, customer_a = _seed_subject(db, slug="source")
    org_b, store_b, user_b, customer_b = _seed_subject(db, slug="appeal")
    _report(db, org_a, store_a, user_a, customer_a)

    dispute_payload = submit_customer_risk_dispute(
        db=db,
        organization_id=org_b.id,
        requester_user_id=user_b.id,
        customer_id=customer_b.id,
        requester_store_id=store_b.id,
        statement=(
            "We reviewed the delivery documents and believe the shared signal "
            "requires a platform moderation review."
        ),
        evidence_reference="appeal-ticket-22",
    )

    assert dispute_payload["status"] == "open"
    assert "report_id" not in dispute_payload
    assert "reporter_organization_id" not in dispute_payload
    assert db.query(CustomerRiskDisputeEvent).one().action == "dispute_submitted"

    report = db.query(CustomerRiskReport).one()
    detail = get_customer_risk_moderation_report(db, report.id)
    assert len(detail["disputes"]) == 1
    assert detail["disputes"][0]["requester_organization_id"] == org_b.id


def test_accepted_appeal_moves_external_signal_to_disputed_not_dismissed(db):
    org_a, store_a, user_a, customer_a = _seed_subject(db, slug="accepted-source")
    org_b, store_b, user_b, customer_b = _seed_subject(db, slug="accepted-requester")
    _report(db, org_a, store_a, user_a, customer_a)

    dispute = submit_customer_risk_dispute(
        db=db,
        organization_id=org_b.id,
        requester_user_id=user_b.id,
        customer_id=customer_b.id,
        requester_store_id=store_b.id,
        statement="The customer supplied documents that conflict with the shared signal.",
    )

    resolved = resolve_customer_risk_dispute(
        db,
        dispute_id=dispute["id"],
        admin_user_id=user_b.id,
        outcome="accepted",
        note="Appeal evidence is sufficient to require the source report to be reviewed.",
    )

    report = db.query(CustomerRiskReport).one()
    stored_dispute = db.query(CustomerRiskDispute).one()
    assert report.status == "disputed"
    assert stored_dispute.status == "accepted"
    assert resolved["status"] == "accepted"

    report_actions = [
        row.action
        for row in db.query(CustomerRiskReportEvent)
        .filter(CustomerRiskReportEvent.report_id == report.id)
        .order_by(CustomerRiskReportEvent.id.asc())
        .all()
    ]
    assert report_actions == ["report_submitted", "moderation_disputed"]

    dispute_actions = [
        row.action
        for row in db.query(CustomerRiskDisputeEvent)
        .filter(CustomerRiskDisputeEvent.dispute_id == stored_dispute.id)
        .order_by(CustomerRiskDisputeEvent.id.asc())
        .all()
    ]
    assert dispute_actions == ["dispute_submitted", "dispute_accepted"]

    viewer_summary = get_customer_risk_summary(
        db=db,
        organization_id=org_b.id,
        customer_id=customer_b.id,
    )
    assert viewer_summary["alert"] is True
    assert viewer_summary["disputed_reports"] == 1
    assert viewer_summary["severity"] == "notice"


def test_report_write_rate_limit_prevents_repeated_updates(db, monkeypatch):
    organization, store, user, customer = _seed_subject(db, slug="rate")
    monkeypatch.setenv("CUSTOMER_RISK_REPORT_LIMIT_24H", "1")

    _report(db, organization, store, user, customer)

    with pytest.raises(CustomerRiskRateLimitError, match="limit reached"):
        report_customer(
            db=db,
            organization_id=organization.id,
            reporter_user_id=user.id,
            customer_id=customer.id,
            reporter_store_id=store.id,
            reason="other",
            notes="A second write inside the same rolling window.",
        )

    assert db.query(CustomerRiskReport).count() == 1
    assert db.query(CustomerRiskReportEvent).count() == 1
