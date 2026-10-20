"""Retention drafts provide diagnostics, never authorization or PII echoes."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.shopify_privacy_backlog import router
from app.services.shopify_privacy_controls import RETENTION_CONTROLS
from app.services.shopify_privacy_inventory_report import build_shopify_retention_review_template
from app.services.shopify_privacy_retention_assessment import (
    RetentionDecisionDraft,
    RetentionPolicyDraft,
    RetentionReviewError,
    assess_shopify_retention_policy_draft,
)

_DIGEST = "a" * 64


def _complete_category(category: str, *, hold: str = "none") -> RetentionDecisionDraft:
    return RetentionDecisionDraft(
        category=category,
        jurisdiction="CO",
        purpose_evidence_sha256=_DIGEST,
        legal_basis_evidence_sha256=_DIGEST,
        retention_days=365,
        retention_start_event="collection",
        statutory_exception="none",
        legal_hold=hold,
        legal_hold_evidence_sha256=_DIGEST if hold == "active" else None,
        disposition="anonymize",
        minimum_data_evidence_sha256=_DIGEST,
        processors_evidence_sha256=_DIGEST,
        backups_evidence_sha256=_DIGEST,
        independent_signoff_sha256=_DIGEST,
    )


def _client(monkeypatch):
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-expected-secret")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_missing_categories_are_explicit_and_never_authorized():
    result = assess_shopify_retention_policy_draft(RetentionPolicyDraft())
    assert result["submitted_category_count"] == 0
    assert result["category_count"] == len(RETENTION_CONTROLS)
    assert all(item["gap_codes"] == ["RETENTION_CATEGORY_DRAFT_MISSING"] for item in result["categories"])
    assert result["policy_approved"] is False
    assert result["live_erasure_authorized"] is False
    assert result["live_export_authorized"] is False


def test_complete_draft_with_all_evidence_hashes_remains_unapproved():
    decisions = [_complete_category(category) for category, _, _ in RETENTION_CONTROLS]
    result = assess_shopify_retention_policy_draft(
        RetentionPolicyDraft(categories=decisions)
    )
    assert result["submitted_category_count"] == 6
    for category in result["categories"]:
        assert category["gap_codes"] == [
            "INDEPENDENT_LEGAL_APPROVAL_NOT_VERIFIED",
            "LIVE_ERASURE_WORKFLOW_NOT_AUTHORIZED",
        ]
        assert category["destruction_authorized"] is False
    assert result["evidence_independently_verified"] is False
    assert result["policy_approved"] is False
    assert _DIGEST not in json.dumps(result)


def test_active_legal_hold_blocks_even_complete_draft():
    draft = RetentionPolicyDraft(categories=[_complete_category("financial_orders", hold="active")])
    result = assess_shopify_retention_policy_draft(draft)
    category = next(item for item in result["categories"] if item["category"] == "financial_orders")
    assert "LEGAL_HOLD_ACTIVE_NO_ERASURE_AUTHORIZATION" in category["gap_codes"]
    assert category["destruction_authorized"] is False
    assert result["fulfillment_complete"] is False


def test_undocumented_custom_event_and_exception_flagged():
    draft = RetentionPolicyDraft(categories=[RetentionDecisionDraft(
        category="customer_contact",
        retention_start_event="other_documented",
        statutory_exception="documented",
    )])
    result = assess_shopify_retention_policy_draft(draft)
    gaps = result["categories"][0]["gap_codes"]
    assert "CUSTOM_START_EVENT_EVIDENCE_MISSING" in gaps
    assert "STATUTORY_EXCEPTION_EVIDENCE_MISSING" in gaps
    assert "LEGAL_HOLD_NOT_REVIEWED" in gaps


def test_unknown_and_duplicate_categories_are_rejected_without_echoing_values():
    with pytest.raises(RetentionReviewError, match="UNKNOWN_RETENTION_CATEGORY"):
        assess_shopify_retention_policy_draft(RetentionPolicyDraft(categories=[
            RetentionDecisionDraft(category="something_unknown"),
        ]))
    with pytest.raises(RetentionReviewError, match="DUPLICATE_RETENTION_CATEGORY"):
        assess_shopify_retention_policy_draft(RetentionPolicyDraft(categories=[
            RetentionDecisionDraft(category="customer_contact"),
            RetentionDecisionDraft(category="customer_contact"),
        ]))


def test_http_auth_runs_before_parsing_body_and_no_pii_leaks(monkeypatch):
    client = _client(monkeypatch)
    path = "/api/internal/shopify/privacy/retention/assess"
    hostile = '{"categories":[{"category":"customer_contact","email":"private@example.com"}]}'
    assert client.post(path, content=hostile, headers={"Content-Type": "application/json"}).status_code == 401
    response = client.post(
        path, content=hostile,
        headers={"X-Internal-Secret": "synthetic-expected-secret", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_RETENTION_DRAFT"
    assert "private@example.com" not in response.text
    assert "private@example.com" not in json.dumps(response.json())


def test_http_rejects_invalid_types_and_excessive_periods_without_echo(monkeypatch):
    client = _client(monkeypatch)
    headers = {"X-Internal-Secret": "synthetic-expected-secret"}
    path = "/api/internal/shopify/privacy/retention/assess"
    for payload in (
        {"categories": [{"category": "financial_orders", "retention_days": "365"}]},
        {"categories": [{"category": "financial_orders", "retention_days": 36501}]},
        {"categories": [{"category": "financial_orders", "independent_signoff_sha256": "not-a-digest"}]},
    ):
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"] == "INVALID_RETENTION_DRAFT"
    assert client.post(path, data="{}", headers={"X-Internal-Secret": "synthetic-expected-secret"}).status_code == 415
    assert client.post(
        path, content=b"x" * 16385,
        headers={**headers, "Content-Type": "application/json"},
    ).status_code == 413


def test_http_valid_draft_is_read_only_and_fail_closed(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/internal/shopify/privacy/retention/assess",
        json={"categories": [{"category": "customer_contact", "legal_hold": "active"}]},
        headers={"X-Internal-Secret": "synthetic-expected-secret"},
    )
    assert response.status_code == 200
    assert response.json()["submitted_category_count"] == 1
    assert response.json()["live_erasure_authorized"] is False
    assert response.json()["policy_approved"] is False
    assert response.json()["categories"][0]["destruction_authorized"] is False


def test_no_secret_configuration_rejects_even_well_formed_draft(monkeypatch):
    monkeypatch.delenv("DIAGLOB_INTERNAL_SECRET", raising=False)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/internal/shopify/privacy/retention/assess",
        json={"categories": []},
        headers={"X-Internal-Secret": "some-user-controlled-value"},
    )
    assert response.status_code == 401


def test_template_supplies_complete_shape_for_non_approved_draft():
    template = build_shopify_retention_review_template()
    draft = RetentionPolicyDraft.model_validate(template["assessment_draft"])
    assert template["assessment_endpoint"] == "/api/internal/shopify/privacy/retention/assess"
    assert len(draft.categories) == len(RETENTION_CONTROLS)
    assert all(item.retention_days is None for item in draft.categories)
    assert all(item.legal_hold == "not_reviewed" for item in draft.categories)
    result = assess_shopify_retention_policy_draft(draft)
    assert result["live_erasure_authorized"] is False
    assert result["policy_approved"] is False
