"""No real Shopify API calls: complete paid tenant scan and alert failures."""
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Organization
from app.shopify_billing_recheck import recheck_all


def test_shopify_recheck_scans_all_pages_and_ignores_paddle(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        db.add_all([
            Organization(name=f"Shopify {i}", slug=f"shopify-page-{i}",
                         billing_provider="shopify", plan="starter")
            for i in range(7)
        ])
        db.add(Organization(name="Paddle", slug="paddle-skip",
                            billing_provider="paddle", plan="growth"))
        db.commit()
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    seen = []
    with patch("app.shopify_billing_recheck.SessionLocal", sessions), patch(
        "app.shopify_billing_recheck.refresh_shopify_billing_status",
        side_effect=lambda db, *, organization_id: seen.append(organization_id),
    ):
        result = recheck_all(page_size=3)
    assert len(seen) == len(set(seen)) == 7
    assert result == {
        "enabled": True, "complete": True,
        "checked": 7, "succeeded": 7, "failed": 0, "pages": 3,
    }
    engine.dispose()


def test_shopify_recheck_reports_partial_and_per_tenant_failure(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        db.add_all([
            Organization(name=f"Merchant {i}", slug=f"billing-fail-{i}",
                         billing_provider="shopify", plan="growth")
            for i in range(5)
        ])
        db.commit()
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    count = [0]

    def check(db, *, organization_id):
        count[0] += 1
        if count[0] == 2:
            raise RuntimeError("synthetic token must not appear in logs")

    with patch("app.shopify_billing_recheck.SessionLocal", sessions), patch(
        "app.shopify_billing_recheck.refresh_shopify_billing_status",
        side_effect=check,
    ):
        partial = recheck_all(page_size=2, max_pages=1)
    assert partial["complete"] is False
    assert partial["checked"] == 2
    assert partial["failed"] == 1
    engine.dispose()


def test_shopify_recheck_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", raising=False)
    assert recheck_all()["enabled"] is False
