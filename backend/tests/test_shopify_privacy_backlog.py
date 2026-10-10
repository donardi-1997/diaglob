"""PII-free Shopify privacy backlog SLA accounting and internal access."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.shopify_privacy_backlog import get_shopify_privacy_backlog
from app.db import Base
from app.models import ShopifyPrivacyRequest
from app.services.shopify_privacy_backlog import summarize_shopify_privacy_backlog


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _receipt(db, *, n, topic, age_days, now, status="pending_policy_review",
             organization_id=12, store_id=34):
    db.add(ShopifyPrivacyRequest(
        request_id=f"{n:064x}",
        topic=topic,
        shop_id="synthetic_shop_99",
        shop_domain="synthetic-only.myshopify.com",
        organization_id=organization_id,
        store_id=store_id,
        selector_encrypted="encrypted-test-only",
        status=status,
        created_at=now - timedelta(days=age_days),
        updated_at=now - timedelta(days=age_days),
    ))


def test_empty_backlog_returns_zero_metrics_and_no_ready_claim(sandbox):
    summary = summarize_shopify_privacy_backlog(sandbox)
    assert summary.outstanding_total == 0
    assert summary.overdue_total == 0
    assert summary.oldest_outstanding_days is None
    assert summary.live_processing_ready is False
    assert len(summary.topics) == 3


def test_overdue_soon_and_unmapped_are_grouped_without_identifiers(sandbox):
    now = datetime(2026, 10, 10, 12, 0)
    _receipt(sandbox, n=1, topic="customers/data_request", age_days=31, now=now)
    _receipt(sandbox, n=2, topic="customers/data_request", age_days=24, now=now,
             organization_id=None, store_id=None)
    _receipt(sandbox, n=3, topic="customers/redact", age_days=5, now=now,
             status="manual_review_required")
    _receipt(sandbox, n=4, topic="shop/redact", age_days=40, now=now,
             status="completed")
    sandbox.commit()
    result = summarize_shopify_privacy_backlog(sandbox, now=now).safe_dict()
    assert result["outstanding_total"] == 3
    assert result["overdue_total"] == 1
    assert result["due_within_7_days_total"] == 1
    assert result["tenant_unresolved_total"] == 1
    assert result["oldest_outstanding_days"] == 31
    assert result["fulfillment_target_days"] == 30
    assert result["live_processing_ready"] is False
    assert result["topics"] == [
        {"topic": "customers/data_request", "outstanding": 2, "overdue": 1,
         "due_within_7_days": 1, "tenant_unresolved": 1},
        {"topic": "customers/redact", "outstanding": 1, "overdue": 0,
         "due_within_7_days": 0, "tenant_unresolved": 0},
        {"topic": "shop/redact", "outstanding": 0, "overdue": 0,
         "due_within_7_days": 0, "tenant_unresolved": 0},
    ]
    output = str(result)
    assert "synthetic-only.myshopify.com" not in output
    assert "synthetic_shop_99" not in output
    assert "encrypted-test-only" not in output


def test_timezone_aware_now_is_normalized_to_utc(sandbox):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    _receipt(sandbox, n=1, topic="shop/redact", age_days=30, now=now.replace(tzinfo=None))
    sandbox.commit()
    result = summarize_shopify_privacy_backlog(sandbox, now=now)
    assert result.overdue_total == 0
    assert result.due_within_7_days_total == 1


def test_internal_auth_rejects_missing_secret_before_any_database_access(
    sandbox, monkeypatch
):
    monkeypatch.delenv("DIAGLOB_INTERNAL_SECRET", raising=False)
    query = Mock(side_effect=AssertionError("query must not be executed"))
    with patch(
        "app.api.shopify_privacy_backlog.summarize_shopify_privacy_backlog",
        query,
    ):
        with pytest.raises(HTTPException) as exc:
            get_shopify_privacy_backlog(x_internal_secret="anything", db=sandbox)
    assert exc.value.status_code == 401
    query.assert_not_called()


def test_internal_auth_rejects_wrong_secret_without_data_access(
    sandbox, monkeypatch
):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "expected-secret")
    with patch(
        "app.api.shopify_privacy_backlog.summarize_shopify_privacy_backlog"
    ) as backend:
        with pytest.raises(HTTPException) as exc:
            get_shopify_privacy_backlog(
                x_internal_secret="wrong-secret", db=sandbox
            )
    assert exc.value.status_code == 401
    backend.assert_not_called()


def test_internal_auth_returns_only_aggregates(sandbox, monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "expected-secret")
    _receipt(sandbox, n=5, topic="customers/redact", age_days=0,
             now=datetime.utcnow(), organization_id=None)
    sandbox.commit()
    snapshot = get_shopify_privacy_backlog(
        x_internal_secret="expected-secret", db=sandbox
    )
    assert snapshot["outstanding_total"] == 1
    assert snapshot["tenant_unresolved_total"] == 1
    assert snapshot["live_processing_ready"] is False
    assert "shop_id" not in str(snapshot)
    assert "shop_domain" not in str(snapshot)
    assert "selector_encrypted" not in str(snapshot)
