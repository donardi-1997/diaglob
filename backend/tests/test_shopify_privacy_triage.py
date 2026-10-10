"""Shopify privacy triage regression tests: no PII and no state changes."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.shopify_privacy_triage import triage_privacy_receipt


REQUEST_ID = "a" * 64
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def triage(**overrides):
    kwargs = {
        "request_id": REQUEST_ID,
        "topic": "customers/redact",
        "received_at": NOW - timedelta(days=1),
        "now": NOW,
        "organization_id": 1,
        "store_id": 2,
    }
    kwargs.update(overrides)
    return triage_privacy_receipt(**kwargs)


def test_valid_case_still_requires_manual_review():
    result = triage()
    assert result.priority == "normal"
    assert result.reasons == ()
    assert result.requires_manual_review is True
    assert result.fulfillment_authorized is False


@pytest.mark.parametrize("days,priority,reason", [
    (22, "normal", None),
    (23, "high", "APPROACHING_OPERATIONAL_THRESHOLD"),
    (29, "high", "APPROACHING_OPERATIONAL_THRESHOLD"),
    (30, "critical", "OPERATIONAL_THRESHOLD_EXCEEDED"),
    (31, "critical", "OPERATIONAL_THRESHOLD_EXCEEDED"),
])
def test_threshold_boundaries(days, priority, reason):
    result = triage(received_at=NOW - timedelta(days=days))
    assert result.priority == priority
    assert (reason in result.reasons) if reason else (result.reasons == ())


def test_unknown_topic_and_missing_tenant_fail_closed():
    result = triage(topic="unknown", store_id=None)
    assert result.priority == "high"
    assert result.reasons == ("UNKNOWN_TOPIC", "TENANT_UNRESOLVED")
    assert result.fulfillment_authorized is False


def test_future_timestamp_requires_investigation():
    result = triage(received_at=NOW + timedelta(seconds=1))
    assert result.reasons == ("FUTURE_RECEIPT_TIMESTAMP",)


@pytest.mark.parametrize("field,value", [
    ("organization_id", True), ("store_id", 0),
    ("organization_id", "1"),
])
def test_untrusted_tenant_identifiers(field, value):
    assert "TENANT_UNRESOLVED" in triage(**{field: value}).reasons


def test_timezone_offsets_are_compared_in_utc():
    other_tz = timezone(timedelta(hours=-5))
    result = triage(
        received_at=(NOW - timedelta(days=30)).astimezone(other_tz),
    )
    assert result.priority == "critical"


@pytest.mark.parametrize("field,value,error", [
    ("request_id", "not-a-hash", "INVALID_REQUEST_ID"),
    ("received_at", datetime(2026, 10, 9), "TIMEZONE_REQUIRED"),
    ("now", datetime(2026, 10, 10), "TIMEZONE_REQUIRED"),
    ("warning_after_days", True, "INVALID_THRESHOLDS"),
    ("overdue_after_days", 22, "INVALID_THRESHOLDS"),
])
def test_invalid_inputs_are_rejected(field, value, error):
    with pytest.raises(ValueError, match=error):
        triage(**{field: value})


def test_result_contains_no_customer_or_shop_data():
    result = triage()
    assert set(result.__dict__) == {
        "request_id", "reasons", "priority",
        "requires_manual_review", "fulfillment_authorized",
    }
