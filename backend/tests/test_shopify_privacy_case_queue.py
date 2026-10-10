"""Internal Shopify privacy case queue: authenticated, bounded, PII-free."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ShopifyPrivacyRequest
from app.services.shopify_privacy_case_queue import list_shopify_privacy_cases
from app.api.shopify_privacy_backlog import get_shopify_privacy_cases


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _receipt(db, *, index, days=1, topic="customers/redact",
             org=5, store=8):
    db.add(ShopifyPrivacyRequest(
        request_id=f"{index:064x}",
        topic=topic,
        shop_id="PRIVATE_SHOP_ID",
        shop_domain="private-store.myshopify.com",
        organization_id=org,
        store_id=store,
        selector_encrypted="ENCRYPTED_SECRET_CUSTOMER@example.com",
        status="completed" if index == 1 else "pending_policy_review",
        created_at=(NOW - timedelta(days=days)).replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
    ))


def test_case_queue_is_pii_free_and_never_claims_fulfillment(sandbox):
    _receipt(sandbox, index=1, days=30)
    _receipt(sandbox, index=2, days=25, org=None)
    _receipt(sandbox, index=3, days=2, topic="future/private@example.com")
    sandbox.commit()

    result = list_shopify_privacy_cases(sandbox, now=NOW, limit=10)
    assert result["read_only"] is True
    assert result["fulfillment_authorized"] is False
    assert result["has_more"] is False
    assert [x["priority"] for x in result["cases"]] == [
        "critical", "high", "high"
    ]
    assert result["cases"][0]["reasons"] == ["OPERATIONAL_THRESHOLD_EXCEEDED"]
    assert "TENANT_UNRESOLVED" in result["cases"][1]["reasons"]
    assert result["cases"][2]["topic"] == "unknown"
    assert all(x["fulfillment_authorized"] is False for x in result["cases"])
    assert all(x["requires_manual_review"] is True for x in result["cases"])
    assert "ENCRYPTED_SECRET" not in str(result)
    assert "private-store" not in str(result)
    assert "PRIVATE_SHOP_ID" not in str(result)
    assert "private@example.com" not in str(result)
    assert "completed" not in str(result)


def test_case_queue_is_bounded_and_paginates_deterministically(sandbox):
    for index, days in [(1, 9), (2, 9), (3, 3)]:
        _receipt(sandbox, index=index, days=days)
    sandbox.commit()
    first = list_shopify_privacy_cases(sandbox, now=NOW, limit=2, offset=0)
    second = list_shopify_privacy_cases(sandbox, now=NOW, limit=2, offset=2)
    assert [x["request_id"] for x in first["cases"]] == [
        f"{1:064x}", f"{2:064x}"
    ]
    assert first["next_offset"] == 2
    assert first["has_more"] is True
    assert [x["request_id"] for x in second["cases"]] == [f"{3:064x}"]
    assert second["next_offset"] is None
    assert second["has_more"] is False


@pytest.mark.parametrize("limit,offset", [
    (0, 0), (101, 0), (True, 0), ("2", 0),
    (1, -1), (1, 100001), (1, False),
])
def test_case_queue_invalid_pagination_fails_closed(sandbox, limit, offset):
    with pytest.raises(ValueError, match="INVALID_CASE_PAGINATION"):
        list_shopify_privacy_cases(
            sandbox, now=NOW, limit=limit, offset=offset
        )


def test_internal_api_rejects_missing_secret_before_query(sandbox, monkeypatch):
    monkeypatch.delenv("DIAGLOB_INTERNAL_SECRET", raising=False)
    with patch("app.api.shopify_privacy_backlog.list_shopify_privacy_cases") as service:
        with pytest.raises(HTTPException) as exc:
            get_shopify_privacy_cases(
                limit=20, offset=0, x_internal_secret="guess", db=sandbox
            )
    assert exc.value.status_code == 401
    service.assert_not_called()


def test_internal_api_rejects_invalid_secret_before_query(sandbox, monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "verified-test-secret")
    with patch("app.api.shopify_privacy_backlog.list_shopify_privacy_cases") as service:
        with pytest.raises(HTTPException) as exc:
            get_shopify_privacy_cases(
                limit=20, offset=0, x_internal_secret="wrong", db=sandbox
            )
    assert exc.value.status_code == 401
    service.assert_not_called()


def test_internal_api_returns_only_sanitized_cases(sandbox, monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "verified-test-secret")
    _receipt(sandbox, index=4, days=23)
    sandbox.commit()
    result = get_shopify_privacy_cases(
        limit=10, offset=0, x_internal_secret="verified-test-secret",
        db=sandbox,
    )
    assert result["cases"][0]["priority"] == "high"
    assert result["cases"][0]["topic"] == "customers/redact"
    assert "PRIVATE_SHOP_ID" not in str(result)
    assert "ENCRYPTED_SECRET" not in str(result)
