"""Privacy escalation queue: urgency ahead of pagination, no PII or changes."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ShopifyPrivacyRequest
from app.services.shopify_privacy_escalations import list_shopify_privacy_escalations
from app.api.shopify_privacy_backlog import get_shopify_privacy_escalations

NOW = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)


@pytest.fixture()
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _record(db, index, *, days=1, seconds=0, topic="customers/redact",
            org=5, store=8, status="pending_policy_review"):
    db.add(ShopifyPrivacyRequest(
        request_id=f"{index:064x}", topic=topic,
        shop_id="PRIVATE_SHOP_ID", shop_domain="private.myshopify.com",
        organization_id=org, store_id=store,
        selector_encrypted="PRIVATE_CUSTOMER@example.com",
        status=status,
        created_at=(NOW - timedelta(days=days, seconds=seconds)).replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
    ))


def test_escalations_keep_even_falsely_completed_case_and_hide_normal_rows(sandbox):
    _record(sandbox, 1, days=31, status="completed")
    _record(sandbox, 2, days=30)
    _record(sandbox, 3, days=24)
    _record(sandbox, 4, days=2, org=None)
    _record(sandbox, 5, days=1, topic="private@example.com")
    _record(sandbox, 6, days=2)
    _record(sandbox, 7, days=-1)
    sandbox.commit()

    result = list_shopify_privacy_escalations(sandbox, now=NOW)
    cases = result["cases"]
    assert [c["request_id"] for c in cases] == [
        f"{i:064x}" for i in (1, 2, 3, 4, 5, 7)
    ]
    assert [c["priority"] for c in cases] == [
        "critical", "critical", "high", "high", "high", "high"
    ]
    assert "OPERATIONAL_THRESHOLD_EXCEEDED" in cases[0]["reasons"]
    assert "TENANT_UNRESOLVED" in cases[3]["reasons"]
    assert "UNKNOWN_TOPIC" in cases[4]["reasons"]
    assert "FUTURE_RECEIPT_TIMESTAMP" in cases[5]["reasons"]
    assert cases[0]["deadline_at_utc"] == "2026-10-14T14:00:00Z"
    assert cases[4]["topic"] == "unknown"
    assert all(c["requires_manual_review"] for c in cases)
    assert all(not c["fulfillment_complete"] for c in cases)
    assert result["read_only"] and not result["fulfillment_authorized"]
    for secret in ("private.myshopify.com", "PRIVATE_CUSTOMER", "PRIVATE_SHOP_ID", "private@example.com", "completed"):
        assert secret not in str(result)
    assert sandbox.query(ShopifyPrivacyRequest).count() == 7


def test_escalation_filter_before_pagination_and_priority_sorting(sandbox):
    # Create normal cases before escalating cases to catch a page-first bug.
    for index in range(1, 18):
        _record(sandbox, index, days=2)
    _record(sandbox, 19, days=23)
    _record(sandbox, 20, days=30)
    sandbox.commit()
    first = list_shopify_privacy_escalations(sandbox, now=NOW, limit=1)
    second = list_shopify_privacy_escalations(sandbox, now=NOW, limit=1, offset=1)
    assert [c["request_id"] for c in first["cases"]] == [f"{20:064x}"]
    assert [c["request_id"] for c in second["cases"]] == [f"{19:064x}"]
    assert first["has_more"] is True and first["next_offset"] == 1
    assert second["has_more"] is False and second["next_offset"] is None


def test_escalation_boundaries_are_exact_seconds(sandbox):
    _record(sandbox, 1, days=22, seconds=86399)
    _record(sandbox, 2, days=23)
    _record(sandbox, 3, days=29, seconds=86399)
    _record(sandbox, 4, days=30)
    sandbox.commit()
    cases = list_shopify_privacy_escalations(sandbox, now=NOW)["cases"]
    assert [x["request_id"] for x in cases] == [
        f"{4:064x}", f"{3:064x}", f"{2:064x}"
    ]
    assert cases[0]["priority"] == "critical"
    assert cases[1]["priority"] == cases[2]["priority"] == "high"


@pytest.mark.parametrize("limit,offset", [
    (0, 0), (101, 0), (True, 0), ("3", 0),
    (1, -1), (1, 100001), (1, False),
])
def test_escalation_pagination_fail_closed(sandbox, limit, offset):
    with pytest.raises(ValueError, match="INVALID_ESCALATION_PAGINATION"):
        list_shopify_privacy_escalations(sandbox, limit=limit, offset=offset, now=NOW)


def test_escalation_rejects_naive_timestamp(sandbox):
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        list_shopify_privacy_escalations(sandbox, now=datetime(2026, 10, 15))


def test_escalation_api_requires_internal_secret_before_db_query(sandbox, monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-operator-secret")
    with patch("app.api.shopify_privacy_backlog.list_shopify_privacy_escalations") as service:
        with pytest.raises(HTTPException) as exc:
            get_shopify_privacy_escalations(
                limit=20, offset=0, x_internal_secret="invalid", db=sandbox,
            )
    assert exc.value.status_code == 401
    service.assert_not_called()


def test_escalation_api_returns_sanitized_critical_case(sandbox, monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-operator-secret")
    _record(sandbox, 1, days=30)
    sandbox.commit()
    # A deterministic clock is injected through the pure service.
    with patch("app.api.shopify_privacy_backlog.list_shopify_privacy_escalations",
               return_value=list_shopify_privacy_escalations(sandbox, now=NOW)) as service:
        result = get_shopify_privacy_escalations(
            limit=5, offset=0,
            x_internal_secret="synthetic-operator-secret", db=sandbox,
        )
    service.assert_called_once_with(sandbox, limit=5, offset=0)
    assert result["cases"][0]["priority"] == "critical"
    assert "PRIVATE_CUSTOMER" not in str(result)
