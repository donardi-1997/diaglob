from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Automation,
    AutomationExecution,
    Conversation,
    Customer,
    Message,
    MetaAdsConnection,
    Organization,
    Store,
)
from app.operations import get_operations_summary
from app.services.operations_integrations import get_dynamic_operations_summary


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    return engine, db


def _seed_store(db) -> None:
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
            country_code="CO",
            currency="COP",
            timezone="UTC",
            active=True,
        )
    )
    db.commit()


def test_base_summary_uses_honest_ai_message_share_name():
    engine, db = _database()
    try:
        _seed_store(db)

        summary = get_operations_summary(db, 1, 1)

        assert "ai_message_share_pct" in summary["conversations"]
        assert "ai_resolved_pct" not in summary["conversations"]
    finally:
        db.close()
        engine.dispose()


def test_summary_exposes_operational_health_and_honest_ai_message_share():
    engine, db = _database()
    try:
        _seed_store(db)
        db.add(
            Customer(
                id=1,
                organization_id=1,
                name="Customer",
                phone="+573001234567",
            )
        )
        db.add(
            Conversation(
                id=1,
                organization_id=1,
                store_id=1,
                customer_id=1,
                channel="whatsapp",
                mode="ai",
            )
        )
        db.flush()
        db.add_all(
            [
                Message(
                    conversation_id=1,
                    sender="user",
                    text="Hello",
                ),
                Message(
                    conversation_id=1,
                    sender="ai",
                    text="Hi",
                ),
            ]
        )
        db.commit()

        summary = get_dynamic_operations_summary(db, 1, 1)

        assert summary["conversations"]["ai_message_share_pct"] == 50.0
        assert "ai_resolved_pct" not in summary["conversations"]
        assert summary["health"] == {
            "status": "operational",
            "issues": 0,
            "critical_issues": 0,
        }
    finally:
        db.close()
        engine.dispose()


def test_failed_automation_marks_health_as_attention():
    engine, db = _database()
    try:
        _seed_store(db)
        db.add(
            Automation(
                id=1,
                organization_id=1,
                store_id=1,
                name="Failing automation",
                trigger_type="manual",
                active=True,
            )
        )
        db.add(
            AutomationExecution(
                id=1,
                automation_id=1,
                organization_id=1,
                store_id=1,
                event_type="manual",
                status="failed",
                started_at=datetime.utcnow(),
            )
        )
        db.commit()

        summary = get_dynamic_operations_summary(db, 1, 1)

        assert summary["health"]["status"] == "attention"
        assert summary["health"]["issues"] == 1
        assert summary["health"]["critical_issues"] == 0
    finally:
        db.close()
        engine.dispose()


def test_integration_status_failure_marks_health_as_degraded():
    engine, db = _database()
    try:
        _seed_store(db)
        MetaAdsConnection.__table__.drop(bind=engine)

        summary = get_dynamic_operations_summary(db, 1, 1)

        assert summary["health"]["status"] == "degraded"
        assert summary["health"]["issues"] >= 1
        assert summary["health"]["critical_issues"] >= 1
    finally:
        db.close()
        engine.dispose()
