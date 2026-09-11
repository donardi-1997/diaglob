"""Regression coverage for platform customer-risk moderation analytics."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.customer_risk import (
    CustomerRiskDispute,
    CustomerRiskReport,
    CustomerRiskReportEvent,
)
from app.models import Organization
from app.services.customer_risk_moderation_analytics_service import (
    get_customer_risk_moderation_analytics,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
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


def test_moderation_analytics_tracks_volume_outcomes_backlog_and_response_time(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization = Organization(
        name="Analytics Org",
        slug="risk-analytics-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()

    confirmed = CustomerRiskReport(
        reporter_organization_id=organization.id,
        phone_fingerprint="a" * 64,
        reason="payment_abuse",
        status="confirmed",
        evidence_reference="ORDER-1",
        created_at=datetime(2026, 9, 8, 12, 0, 0),
        updated_at=datetime(2026, 9, 9, 12, 0, 0),
    )
    dismissed = CustomerRiskReport(
        reporter_organization_id=organization.id,
        phone_fingerprint="b" * 64,
        reason="delivery_claim",
        status="dismissed",
        created_at=datetime(2026, 9, 9, 12, 0, 0),
        updated_at=datetime(2026, 9, 10, 0, 0, 0),
    )
    stale_pending = CustomerRiskReport(
        reporter_organization_id=organization.id,
        phone_fingerprint="c" * 64,
        reason="other",
        status="pending",
        created_at=datetime(2026, 8, 1, 12, 0, 0),
        updated_at=datetime(2026, 8, 1, 12, 0, 0),
    )
    db.add_all([confirmed, dismissed, stale_pending])
    db.flush()

    db.add_all(
        [
            CustomerRiskReportEvent(
                report_id=confirmed.id,
                organization_id=organization.id,
                actor_role="platform_admin",
                action="moderation_confirmed",
                from_status="pending",
                to_status="confirmed",
                created_at=datetime(2026, 9, 9, 12, 0, 0),
            ),
            CustomerRiskReportEvent(
                report_id=dismissed.id,
                organization_id=organization.id,
                actor_role="platform_admin",
                action="moderation_dismissed",
                from_status="pending",
                to_status="dismissed",
                created_at=datetime(2026, 9, 10, 0, 0, 0),
            ),
        ]
    )

    dispute = CustomerRiskDispute(
        requester_organization_id=organization.id,
        phone_fingerprint="d" * 64,
        statement="The signal should be reviewed against the delivery record.",
        status="accepted",
        resolution_note="Documents support the appeal.",
        created_at=datetime(2026, 9, 8, 12, 0, 0),
        updated_at=now,
        resolved_at=now,
    )
    db.add(dispute)
    db.commit()

    analytics = get_customer_risk_moderation_analytics(db, days=7, now=now)

    assert analytics["window"]["days"] == 7
    assert analytics["summary"]["reports_created"] == 2
    assert analytics["summary"]["moderated_reports"] == 2
    assert analytics["summary"]["moderation_actions"] == 2
    assert analytics["summary"]["disputes_created"] == 1
    assert analytics["summary"]["disputes_resolved"] == 1
    assert analytics["summary"]["average_report_resolution_hours"] == 18.0
    assert analytics["summary"]["average_dispute_resolution_hours"] == 48.0
    assert analytics["summary"]["confirmation_rate"] == 50.0
    assert analytics["summary"]["appeal_acceptance_rate"] == 100.0

    assert analytics["backlog"]["pending_reports"] == 1
    assert analytics["backlog"]["pending_reports_over_24h"] == 1
    assert analytics["outcomes"]["reports"] == {
        "confirmed": 1,
        "dismissed": 1,
        "disputed": 0,
        "reset_pending": 0,
    }
    assert analytics["outcomes"]["disputes"] == {
        "accepted": 1,
        "rejected": 0,
    }

    assert analytics["reason_breakdown"][0]["count"] == 1
    assert {item["reason"] for item in analytics["reason_breakdown"]} == {
        "payment_abuse",
        "delivery_claim",
    }
    assert analytics["reporting_organizations"][0]["organization_id"] == organization.id
    assert analytics["reporting_organizations"][0]["report_count"] == 2
    assert analytics["reporting_organizations"][0]["evidence_rate"] == 50.0
    assert analytics["reporting_organizations"][0]["dismissal_rate"] == 50.0

    daily = {row["date"]: row for row in analytics["daily"]}
    assert daily["2026-09-09"]["reports_created"] == 1
    assert daily["2026-09-09"]["reports_moderated"] == 1
    assert daily["2026-09-10"]["reports_moderated"] == 1
    assert daily["2026-09-10"]["disputes_resolved"] == 1


def test_moderation_analytics_bounds_requested_window(db):
    now = datetime(2026, 9, 10, 12, 0, 0)

    assert get_customer_risk_moderation_analytics(db, days=1, now=now)["window"]["days"] == 7
    assert get_customer_risk_moderation_analytics(db, days=365, now=now)["window"]["days"] == 90
