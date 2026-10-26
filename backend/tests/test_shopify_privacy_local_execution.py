"""Real local mutations/delivery, with independent test-only signed permits.

No production DB, Shopify call, external erasure or compliance claim.
"""
import base64
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.api.deps import get_current_membership
from app.models import (
    Conversation, Customer, CustomerStoreProfile, MembershipStore, Message, Order,
    OrderItem, Organization, OrganizationMembership, ShopifyPrivacyAuditEvent,
    ShopifyPrivacyDeliveryArtifact, ShopifyPrivacyRequest, ShopifyPrivacySuppression,
    Store, User,
)
from app.services.shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, policy_snapshot,
)
from app.services.shopify_privacy_local_execution import (
    execute_local_privacy_redaction, preview_local_privacy_execution,
)
from app.services.shopify_privacy_live_delivery import (
    issue_local_privacy_delivery, purge_expired_local_privacy_deliveries,
    redeem_local_privacy_delivery,
)
from app.services.shopify_privacy_suppression import evaluate_shopify_privacy_suppression
from app.shopify_security import encrypt_shopify_secret

ACCESS = "a" * 64
ERASE = "b" * 64


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SHOPIFY_PRIVACY_DELIVERY_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SHOPIFY_PRIVACY_SUPPRESSION_KEY", "test-only-suppression-key-" * 3)
    monkeypatch.setenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", policy_snapshot()[1])
    monkeypatch.delenv("SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", raising=False)
    monkeypatch.delenv("SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS", raising=False)
    private = Ed25519PrivateKey.generate()
    monkeypatch.setenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", b64(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )))
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic privacy", slug="local-privacy", active=True)
        user = User(name="Owner", email="owner@example.invalid", active=True)
        db.add_all([org, user])
        db.flush()
        member = OrganizationMembership(organization_id=org.id, user_id=user.id,
                                        role="owner", all_stores=True, active=True)
        stores = [Store(organization_id=org.id, name=f"Store {i}", slug=f"store-{i}",
                    shopify_domain=f"privacy-{i}.myshopify.com", country_code="CO", currency="COP",
                    timezone="UTC", active=True, deleted=False) for i in (1, 2)]
        customer = Customer(organization_id=org.id, name="PRIVATE_SHARED", phone="573001234567", email="private@example.invalid")
        db.add_all([member, customer, *stores])
        db.flush()
        for index, store in enumerate(stores):
            db.add(CustomerStoreProfile(organization_id=org.id, store_id=store.id,
                customer_id=customer.id, external_customer_id="700", currency="COP"))
            order = Order(organization_id=org.id, store_id=store.id, customer_id=customer.id,
                shopify_order_id=str(101 + index), order_number=f"PRIVATE_ORDER_{index}",
                note=f"PRIVATE_NOTE_{index}", shipping_address={"address1": f"PRIVATE_ADDRESS_{index}"},
                total_amount=100, currency="COP", source="shopify")
            convo = Conversation(organization_id=org.id, store_id=store.id, customer_id=customer.id,
                                  preview=f"PRIVATE_PREVIEW_{index}")
            db.add_all([order, convo])
            db.flush()
            db.add(OrderItem(organization_id=org.id, store_id=store.id, order_id=order.id,
                              title=f"PRIVATE_ITEM_{index}", quantity=1, unit_price=100, currency="COP"))
            db.add(Message(conversation_id=convo.id, sender="customer", text=f"PRIVATE_MESSAGE_{index}"))
        for request_id, topic, field in ((ACCESS, "customers/data_request", "orders_requested"), (ERASE, "customers/redact", "orders_to_redact")):
            db.add(ShopifyPrivacyRequest(request_id=request_id, topic=topic, shop_id="901",
                shop_domain=stores[0].shopify_domain, organization_id=org.id, store_id=stores[0].id,
                selector_encrypted=encrypt_shopify_secret(json.dumps({
                    "customer": {"id": 700, "email": "private@example.invalid"}, field: [101],
                })), status="pending_policy_review"))
            db.add(ShopifyPrivacyAuditEvent(request_id=request_id, event_type="received",
                to_status="pending_policy_review", reason_code="tenant_bound", actor_type="shopify_hmac_verified"))
        db.commit()
        yield db, {"organization_id": org.id, "store_id": stores[0].id, "user_id": user.id}, private, member, stores, customer
    engine.dispose()


def signed_permit(sandbox, request_id=ACCESS, operation="local_export", changes=None):
    db, owner, private, *_ = sandbox
    preview = preview_local_privacy_execution(db, request_id=request_id, **owner)
    data = dict(version=1, operation=operation, request_id=request_id,
        organization_id=owner["organization_id"], store_id=owner["store_id"],
        policy_sha256=policy_snapshot()[1], scope_sha256=preview["scope_sha256"],
        expires_at=int(time.time()) + 600, legal_hold=False)
    if operation == "local_redaction":
        checkpoint = preview["planned_restore_checkpoint"]
        data.update(restore_checkpoint_hmac=checkpoint["checkpoint_hmac"], restore_min_records=checkpoint["total_records"])
    data.update(changes or {})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    signature = private.sign(b"diaglob.shopify.privacy.execution.v1\0" + payload)
    return b64(payload) + "." + b64(signature)


def allow_redaction_checkpoint(sandbox, monkeypatch):
    db, owner, *_ = sandbox
    checkpoint = preview_local_privacy_execution(db, request_id=ERASE, **owner)["planned_restore_checkpoint"]
    # Simulates independently persisted/test-signer-approved recovery settings.
    monkeypatch.setenv("SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", checkpoint["checkpoint_hmac"])
    monkeypatch.setenv("SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS", str(checkpoint["total_records"]))


def test_preview_does_not_mutate_or_read_other_store_content(sandbox):
    db, owner, *_ = sandbox
    result = preview_local_privacy_execution(db, request_id=ERASE, **owner)
    assert result["source_counts"]["orders"] == 1
    assert "PRIVATE" not in str(result)
    assert db.query(ShopifyPrivacySuppression).count() == 0
    assert db.query(Order).filter(Order.shopify_order_id == "101").one().note == "PRIVATE_NOTE_0"
    assert result["fulfillment_complete"] is False


def test_live_delivery_is_encrypted_bound_and_one_time(sandbox):
    db, owner, *_ = sandbox
    result = issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=signed_permit(sandbox), **owner)
    row = db.query(ShopifyPrivacyDeliveryArtifact).one()
    assert row.synthetic_only is False
    assert result["delivery_token"] not in row.token_digest
    assert "PRIVATE" not in row.ciphertext_encrypted
    data = redeem_local_privacy_delivery(db, request_id=ACCESS, token=result["delivery_token"], **owner)
    payload = json.loads(data)
    assert payload["orders"][0]["note"] == "PRIVATE_NOTE_0"
    assert payload["conversations"][0]["messages"][0]["text"] == "PRIVATE_MESSAGE_0"
    assert payload["complete"] is False
    assert b"PRIVATE_NOTE_1" not in data and b"PRIVATE_SHARED" not in data
    db.refresh(row)
    assert row.ciphertext_encrypted is None and row.redeemed_at is not None
    with pytest.raises(ShopifyPrivacyExecutionError):
        redeem_local_privacy_delivery(db, request_id=ACCESS, token=result["delivery_token"], **owner)
    assert db.query(ShopifyPrivacyRequest).filter_by(request_id=ACCESS).one().completed_at is None


def test_reissuing_revokes_old_ticket_and_expiry_purges_ciphertext(sandbox):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox)
    old = issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)
    new = issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)
    with pytest.raises(ShopifyPrivacyExecutionError):
        redeem_local_privacy_delivery(db, request_id=ACCESS, token=old["delivery_token"], **owner)
    row = db.query(ShopifyPrivacyDeliveryArtifact).order_by(ShopifyPrivacyDeliveryArtifact.id.desc()).first()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError):
        redeem_local_privacy_delivery(db, request_id=ACCESS, token=new["delivery_token"], **owner)
    assert purge_expired_local_privacy_deliveries(db) == 1
    db.refresh(row)
    assert row.ciphertext_encrypted is None


@pytest.mark.parametrize("changes", [
    {"operation": "local_redaction"}, {"request_id": "c" * 64}, {"store_id": 999},
    {"organization_id": 999}, {"policy_sha256": "0" * 64}, {"scope_sha256": "0" * 64},
    {"expires_at": 1}, {"expires_at": 9999999999}, {"legal_hold": True}, {"legal_hold": 0},
])
def test_even_valid_signature_cannot_bypass_permit_scope(sandbox, changes):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox, changes=changes)
    with pytest.raises(ShopifyPrivacyExecutionError):
        issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)
    assert db.query(ShopifyPrivacyDeliveryArtifact).count() == 0


def test_tampered_or_unsigned_permit_never_extracts_pii(sandbox):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox)
    with patch("app.services.shopify_privacy_live_delivery.build_encrypted_local_customer_export") as extract:
        with pytest.raises(ShopifyPrivacyExecutionError):
            issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit[:-3], **owner)
        extract.assert_not_called()


def test_processing_disabled_by_default_and_policy_changes_revoke_authorization(sandbox, monkeypatch):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox)
    monkeypatch.delenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED")
    with pytest.raises(ShopifyPrivacyExecutionError, match="DISABLED"):
        issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)
    monkeypatch.setenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", "wrong")
    with pytest.raises(ShopifyPrivacyExecutionError, match="POLICY_REQUIRED"):
        issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)


def test_local_redaction_is_real_atomic_scoped_and_idempotent(sandbox, monkeypatch):
    db, owner, _, _, stores, customer = sandbox
    permit = signed_permit(sandbox, request_id=ERASE, operation="local_redaction")
    allow_redaction_checkpoint(sandbox, monkeypatch)
    result = execute_local_privacy_redaction(db, request_id=ERASE, permit_token=permit, **owner)
    assert result["local_redaction_executed"] is True and result["fulfillment_complete"] is False
    erased = db.query(Order).filter(Order.store_id == stores[0].id).one()
    untouched = db.query(Order).filter(Order.store_id == stores[1].id).one()
    assert erased.note is None and erased.shipping_address is None and erased.customer_id is None
    assert erased.shopify_order_id is None
    assert untouched.note == "PRIVATE_NOTE_1" and untouched.shopify_order_id == "102"
    assert db.query(Message).join(Conversation).filter(Conversation.store_id == stores[0].id).one().text == "[redacted]"
    assert db.query(Message).join(Conversation).filter(Conversation.store_id == stores[1].id).one().text == "PRIVATE_MESSAGE_1"
    db.refresh(customer)
    assert customer.name == "PRIVATE_SHARED"
    assert db.query(CustomerStoreProfile).filter_by(store_id=stores[0].id).count() == 0
    assert db.query(CustomerStoreProfile).filter_by(store_id=stores[1].id).count() == 1
    assert all(row.status == "active" for row in db.query(ShopifyPrivacySuppression).all())
    assert evaluate_shopify_privacy_suppression(db, organization_id=owner["organization_id"],
        store_id=stores[0].id, shop_domain=stores[0].shopify_domain, customer_id="700", order_id="101")[0] is not None
    retry = execute_local_privacy_redaction(db, request_id=ERASE, permit_token=permit, **owner)
    assert retry["idempotent"] is True and retry["fulfillment_complete"] is False
    assert db.query(ShopifyPrivacyAuditEvent).filter_by(event_type="local_redaction_executed").count() == 1


def test_redaction_cannot_run_without_independently_anchored_restore_checkpoint(sandbox):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox, request_id=ERASE, operation="local_redaction")
    with pytest.raises(ShopifyPrivacyExecutionError, match="INDEPENDENT_RESTORE_CHECKPOINT_REQUIRED"):
        execute_local_privacy_redaction(db, request_id=ERASE, permit_token=permit, **owner)
    assert db.query(Order).filter_by(shopify_order_id="101").one().note == "PRIVATE_NOTE_0"
    assert db.query(ShopifyPrivacySuppression).count() == 0


def test_redaction_failure_rolls_back_records_and_tombstones(sandbox, monkeypatch):
    db, owner, *_ = sandbox
    permit = signed_permit(sandbox, request_id=ERASE, operation="local_redaction")
    allow_redaction_checkpoint(sandbox, monkeypatch)
    with patch("app.services.shopify_privacy_local_execution.create_shopify_suppression_checkpoint", side_effect=RuntimeError("test checkpoint failure")):
        with pytest.raises(RuntimeError):
            execute_local_privacy_redaction(db, request_id=ERASE, permit_token=permit, **owner)
    assert db.query(Order).filter_by(shopify_order_id="101").one().note == "PRIVATE_NOTE_0"
    assert db.query(ShopifyPrivacySuppression).count() == 0
    assert db.query(CustomerStoreProfile).count() == 2


def test_owner_role_store_assignment_and_recipient_are_revalidated(sandbox):
    db, owner, _, member, stores, _ = sandbox
    permit = signed_permit(sandbox)
    issued = issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)
    member.all_stores = False
    db.add(MembershipStore(membership_id=member.id, store_id=stores[1].id))
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="OWNER_ACCESS"):
        redeem_local_privacy_delivery(db, request_id=ACCESS, token=issued["delivery_token"], **owner)
    member.all_stores = True
    member.role = "manager"
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="OWNER_ACCESS"):
        issue_local_privacy_delivery(db, request_id=ACCESS, permit_token=permit, **owner)


def test_live_http_delivery_has_no_cache_and_cannot_bypass_authentication(sandbox):
    db, owner, _, member, *_ = sandbox
    path = f"/api/stores/{owner['store_id']}/shopify/privacy/cases/{ACCESS}/local-export"
    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        assert client.post(path).status_code in (401, 403)
        app.dependency_overrides[get_current_membership] = lambda: member
        assert client.post(path).status_code == 409
        prepared = client.post(path, headers={"X-Privacy-Execution-Permit": signed_permit(sandbox)})
        assert prepared.status_code == 200
        assert "no-store" in prepared.headers["cache-control"]
        downloaded = client.get(path, headers={"X-Privacy-Delivery-Token": prepared.json()["delivery_token"]})
        assert downloaded.status_code == 200
        assert downloaded.headers["x-partial-privacy-export"] == "true"
        assert "no-store" in downloaded.headers["cache-control"]
        assert downloaded.json()["complete"] is False
        assert "PRIVATE_NOTE_1" not in downloaded.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)
