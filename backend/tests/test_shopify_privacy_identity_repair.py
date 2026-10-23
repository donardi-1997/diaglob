"""Recover only HMAC-audited shop/redact bindings from exact signed history."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Organization, Store, ShopifyPrivacyRequest, ShopifyPrivacyShopIdentity,
    ShopifyPrivacyAuditEvent, ShopifyPrivacyWorkItem, Order, Customer,
)
from app.services.shopify_privacy_identity_repair import (
    ShopifyPrivacyIdentityRepairError,
    repair_signed_shopify_privacy_receipt_identity,
)
from app.api.shopify_privacy_backlog import repair_shopify_privacy_case_identity


SHOP = "history-only.myshopify.com"
RID = "e" * 64
NOW = datetime(2026, 10, 23, 14, 0)


@pytest.fixture()
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Shopify history owner", slug="history-owner", plan="starter")
        db.add(org)
        db.flush()
        store = Store(
            organization_id=org.id, name="History owner store",
            slug="history-store", country_code="CO", currency="COP",
            timezone="America/Bogota", shopify_domain=SHOP,
        )
        db.add(store)
        db.flush()
        history = ShopifyPrivacyShopIdentity(
            shop_id="321", shop_domain=SHOP,
            organization_id=org.id, store_id=store.id,
            provenance="hmac_uninstall",
            first_seen_at=NOW - timedelta(days=14),
            last_seen_at=NOW - timedelta(days=2),
            uninstalled_at=NOW - timedelta(days=2),
        )
        db.add(history)
        receipt = ShopifyPrivacyRequest(
            request_id=RID, topic="shop/redact",
            shop_id="321", shop_domain=SHOP,
            organization_id=None, store_id=None,
            selector_encrypted="synthetic-encrypted-selector",
            created_at=NOW, updated_at=NOW,
            status="pending_policy_review",
        )
        db.add(receipt)
        db.add(ShopifyPrivacyAuditEvent(
            request_id=RID, event_type="received",
            from_status=None, to_status="pending_policy_review",
            reason_code="tenant_unresolved",
            actor_type="shopify_hmac_verified",
            created_at=NOW,
        ))
        db.add(ShopifyPrivacyAuditEvent(
            request_id=RID, event_type="processing_prepared",
            from_status=None, to_status="pending_policy_review",
            reason_code="signed_receipt_tasks_staged_without_data_access",
            actor_type="internal_privacy_processor",
            created_at=NOW,
        ))
        for k in range(10):
            db.add(ShopifyPrivacyWorkItem(
                request_id=RID, area=f"review_area_{k}",
                action="review", status="blocked",
                created_at=NOW, updated_at=NOW,
            ))
        db.commit()
        yield db, org, store, history, receipt
    engine.dispose()


def test_exact_signed_history_can_recover_identity_idempotently(sandbox):
    db, org, store, history, receipt = sandbox
    before_audit = db.query(ShopifyPrivacyAuditEvent).count()
    first = repair_signed_shopify_privacy_receipt_identity(db, request_id=RID)
    assert first == {
        "scope_recovered": True, "repaired": True,
        "fulfillment_authorized": False, "fulfillment_complete": False,
    }
    db.refresh(receipt)
    assert (receipt.organization_id, receipt.store_id) == (org.id, store.id)
    assert db.query(ShopifyPrivacyAuditEvent).count() == before_audit + 1
    assert db.query(ShopifyPrivacyWorkItem).count() == 10
    assert db.query(Order).count() == 0
    assert db.query(Customer).count() == 0
    second = repair_signed_shopify_privacy_receipt_identity(db, request_id=RID)
    assert second["repaired"] is False
    assert second["fulfillment_authorized"] is False
    assert db.query(ShopifyPrivacyAuditEvent).count() == before_audit + 1


@pytest.mark.parametrize("change,reason", [
    ("wrong_signed_shop_id", "SIGNED_SHOP_HISTORY_UNVERIFIED"),
    ("missing_uninstall", "SIGNED_SHOP_HISTORY_UNVERIFIED"),
    ("future_history", "SIGNED_SHOP_HISTORY_UNVERIFIED"),
    ("wrong_domain", "SIGNED_SHOP_HISTORY_UNVERIFIED"),
    ("missing_queue", "PRIVACY_PROCESSING_QUEUE_UNVERIFIED"),
    ("unsigned", "SIGNED_INTAKE_EVIDENCE_MISSING"),
    ("historical_conflict", "SIGNED_SHOP_HISTORY_CONFLICT"),
])
def test_repair_refuses_uncorroborated_or_partial_history(sandbox, change, reason):
    db, org, store, history, receipt = sandbox
    if change == "wrong_signed_shop_id":
        receipt.shop_id = "999"
    elif change == "missing_uninstall":
        history.uninstalled_at = None
    elif change == "future_history":
        history.first_seen_at = NOW + timedelta(minutes=1)
    elif change == "wrong_domain":
        receipt.shop_domain = "attacker.myshopify.com"
    elif change == "missing_queue":
        db.query(ShopifyPrivacyWorkItem).filter(
            ShopifyPrivacyWorkItem.request_id == RID
        ).delete()
    elif change == "unsigned":
        db.query(ShopifyPrivacyAuditEvent).filter(
            ShopifyPrivacyAuditEvent.event_type == "received"
        ).delete()
    elif change == "historical_conflict":
        receipt.last_error_code = "SIGNED_SHOP_IDENTITY_CONFLICT"
        reason = "SIGNED_SHOP_HISTORY_CONFLICT"
    db.commit()
    with pytest.raises(ShopifyPrivacyIdentityRepairError, match=reason):
        repair_signed_shopify_privacy_receipt_identity(db, request_id=RID)
    db.refresh(receipt)
    assert (receipt.organization_id, receipt.store_id) == (None, None)
    assert db.query(Order).count() == 0
    assert db.query(Customer).count() == 0


def test_identity_repair_api_refuses_unauthenticated_operator(sandbox, monkeypatch):
    db, _, _, _, receipt = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-operator-secret")
    with pytest.raises(HTTPException) as exc:
        repair_shopify_privacy_case_identity(
            request_id=RID, x_internal_secret="incorrect-secret", db=db,
        )
    assert exc.value.status_code == 401
    db.refresh(receipt)
    assert receipt.organization_id is None
    assert receipt.store_id is None


def test_no_tenant_guess_when_history_missing(sandbox):
    db, _, _, history, receipt = sandbox
    db.delete(history)
    db.commit()
    with pytest.raises(
        ShopifyPrivacyIdentityRepairError, match="SIGNED_SHOP_HISTORY_MISSING",
    ):
        repair_signed_shopify_privacy_receipt_identity(db, request_id=RID)
    db.refresh(receipt)
    assert receipt.store_id is None
