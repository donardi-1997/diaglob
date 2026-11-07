"""Evidence requirements for the no-data-attributable terminal determination."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShopifyPendingInstall,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacyWorkItem,
)
from app.services.shopify_privacy_identity_repair import (
    ShopifyPrivacyIdentityRepairError,
    repair_signed_shopify_privacy_receipt_identity,
)
from app.services.shopify_privacy_no_data import (
    NO_DATA_EVENT,
    NO_DATA_STATUS,
    ShopifyPrivacyNoDataError,
    assess_no_data_attributable,
    close_shopify_privacy_case_as_no_data,
)
from app.services.shopify_privacy_processing import (
    ShopifyPrivacyProcessingError,
    get_shopify_privacy_processing_case,
    prepare_shopify_privacy_processing_case,
    stage_shopify_privacy_receipt_work_items,
)

NOW = datetime(2026, 11, 7, 12, 0, 0)
DOMAIN = "hidden-no-data.myshopify.com"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_receipt(
    db: Session,
    *,
    organization_id: int | None = None,
    store_id: int | None = None,
    signed: bool = True,
    work_items: int = 10,
) -> str:
    rid = secrets.token_hex(32)
    created = NOW - timedelta(days=22)
    db.add(ShopifyPrivacyRequest(
        request_id=rid,
        topic="shop/redact",
        shop_id="90179239958",
        shop_domain=DOMAIN,
        organization_id=organization_id,
        store_id=store_id,
        selector_encrypted="synthetic-encrypted-selector",
        status="pending_policy_review",
        created_at=created,
        updated_at=created,
    ))
    if signed:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=rid,
            event_type="received",
            from_status=None,
            to_status="pending_policy_review",
            reason_code="signed",
            actor_type="shopify_hmac_verified",
            created_at=created,
        ))
    for index in range(work_items):
        db.add(ShopifyPrivacyWorkItem(
            request_id=rid,
            area=f"area_{index}",
            action="redact",
            status="blocked",
            blocker_code="SHOP_SCOPE_NOT_VERIFIED",
            created_at=created,
            updated_at=created,
        ))
    db.commit()
    return rid


def add_pending(db: Session) -> None:
    db.add(ShopifyPendingInstall(
        state=secrets.token_urlsafe(24),
        shop_domain=DOMAIN,
        expires_at=NOW - timedelta(hours=2),
        state_used=True,
        token_encrypted="synthetic-encrypted-access",
        refresh_token_encrypted="synthetic-encrypted-refresh",
        created_at=NOW - timedelta(hours=3),
    ))
    db.commit()


def test_close_requires_clean_sweep_and_records_pii_free_evidence(db):
    rid = add_receipt(db)

    assessment = assess_no_data_attributable(db, request_id=rid)
    assert assessment is not None
    assert assessment["eligible"] is True
    assert assessment["blocking_codes"] == []
    assert "shop_domain" not in assessment
    assert assessment["direct_reference_counts"] == {}

    result = close_shopify_privacy_case_as_no_data(
        db, request_id=rid, now=NOW, commit=True,
    )

    assert result["determined_now"] is True
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    assert receipt.status == NO_DATA_STATUS
    assert receipt.completed_at is None
    items = db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == rid,
    ).all()
    assert {item.status for item in items} == {"not_applicable"}
    assert {item.blocker_code for item in items} == {None}
    audit = db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.request_id == rid,
        ShopifyPrivacyAuditEvent.event_type == NO_DATA_EVENT,
    ).all()
    assert len(audit) == 1
    assert audit[0].reason_code == "NO_TENANT_DATA_ATTRIBUTABLE"


def test_pending_install_blocks_the_determination(db):
    rid = add_receipt(db)
    add_pending(db)

    assessment = assess_no_data_attributable(db, request_id=rid)
    assert assessment["eligible"] is False
    assert "SHOP_DATA_PRESENT" in assessment["blocking_codes"]
    assert assessment["direct_reference_counts"] == {
        "shopify_pending_installs.shop_domain": 1,
    }

    with pytest.raises(ShopifyPrivacyNoDataError, match="SHOP_DATA_PRESENT"):
        close_shopify_privacy_case_as_no_data(db, request_id=rid, now=NOW)


def test_historical_completion_blocks_the_determination(db):
    rid = add_receipt(db)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    receipt.status = "completed"
    db.commit()
    assessment = assess_no_data_attributable(db, request_id=rid)
    assert "HISTORICAL_COMPLETION_REQUIRES_REVIEW" in assessment["blocking_codes"]


def test_resolved_tenant_blocks_the_determination(db):
    rid = add_receipt(db, organization_id=5, store_id=8)
    assessment = assess_no_data_attributable(db, request_id=rid)
    assert "TENANT_ALREADY_RESOLVED" in assessment["blocking_codes"]


def test_missing_signed_intake_blocks_the_determination(db):
    rid = add_receipt(db, signed=False)
    assessment = assess_no_data_attributable(db, request_id=rid)
    assert "SIGNED_INTAKE_EVIDENCE_MISSING" in assessment["blocking_codes"]


def test_incomplete_work_item_set_blocks_the_determination(db):
    rid = add_receipt(db, work_items=9)
    assessment = assess_no_data_attributable(db, request_id=rid)
    assert "INCOMPLETE_PRIVACY_WORK_ITEM_SET" in assessment["blocking_codes"]


def test_second_close_is_idempotent(db):
    rid = add_receipt(db)
    close_shopify_privacy_case_as_no_data(db, request_id=rid, now=NOW, commit=True)
    second = close_shopify_privacy_case_as_no_data(
        db, request_id=rid, now=NOW, commit=True,
    )
    assert second["determined_now"] is False
    audit = db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.request_id == rid,
        ShopifyPrivacyAuditEvent.event_type == NO_DATA_EVENT,
    ).all()
    assert len(audit) == 1


def _determined_receipt(db: Session) -> str:
    """Close a receipt whose queue was staged by the real intake path."""
    rid = add_receipt(db, work_items=0)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    stage_shopify_privacy_receipt_work_items(db, receipt)
    db.commit()
    close_shopify_privacy_case_as_no_data(db, request_id=rid, now=NOW, commit=True)
    return rid


def test_signed_retry_after_determination_is_not_a_new_fulfillment(db):
    rid = _determined_receipt(db)

    result = prepare_shopify_privacy_processing_case(db, request_id=rid)
    assert result is not None
    assert result["created"] is False
    assert result["receipt_status"] == NO_DATA_STATUS
    assert result["terminal_determination"] is True
    assert result["requires_manual_review"] is False
    assert result["fulfillment_authorized"] is False
    assert result["fulfillment_complete"] is False
    assert len(result["work_items"]) == 10
    assert {item["status"] for item in result["work_items"]} == {
        "not_applicable"
    }

    retry = get_shopify_privacy_processing_case(db, request_id=rid)
    assert retry is not None
    assert retry["terminal_determination"] is True
    assert retry["receipt_status"] == NO_DATA_STATUS
    assert retry["work_items"] == result["work_items"]


def test_retry_rejects_terminal_state_without_audit_evidence(db):
    rid = _determined_receipt(db)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.request_id == rid,
        ShopifyPrivacyAuditEvent.event_type == NO_DATA_EVENT,
    ).delete()
    db.commit()

    with pytest.raises(
        ShopifyPrivacyProcessingError,
        match="NO_DATA_DETERMINATION_EVIDENCE_MISSING",
    ):
        prepare_shopify_privacy_processing_case(db, request_id=rid)
    with pytest.raises(
        ShopifyPrivacyProcessingError,
        match="NO_DATA_DETERMINATION_EVIDENCE_MISSING",
    ):
        get_shopify_privacy_processing_case(db, request_id=rid)


def test_retry_rejects_terminal_state_with_resolved_tenant(db):
    rid = _determined_receipt(db)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    receipt.organization_id = 5
    db.commit()

    with pytest.raises(
        ShopifyPrivacyProcessingError,
        match="NO_DATA_DETERMINATION_TENANT_CONFLICT",
    ):
        prepare_shopify_privacy_processing_case(db, request_id=rid)


def test_identity_repair_cannot_undo_the_determination(db):
    rid = _determined_receipt(db)

    for dry_run in (True, False):
        with pytest.raises(
            ShopifyPrivacyIdentityRepairError,
            match="TERMINAL_DETERMINATION_REQUIRES_REVIEW",
        ):
            repair_signed_shopify_privacy_receipt_identity(
                db, request_id=rid, dry_run=dry_run,
            )
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == rid,
    ).one()
    assert receipt.status == NO_DATA_STATUS
    assert receipt.organization_id is None
    assert receipt.store_id is None
