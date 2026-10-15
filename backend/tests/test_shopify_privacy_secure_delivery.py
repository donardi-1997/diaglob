"""Synthetic-only authenticated privacy delivery contract.

All test data is fabricated. Even an environment flag cannot activate this
transport against a production database or authorize real Shopify fulfillment.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from dataclasses import replace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    MembershipStore, Organization, OrganizationMembership, ShopifyPrivacyAuditEvent,
    ShopifyPrivacyDeliveryArtifact, ShopifyPrivacyDeliveryAudit,
    ShopifyPrivacyRequest, Store, User, Customer, CustomerStoreProfile, Order,
)
from app.services.shopify_privacy_secure_delivery import (
    ShopifyPrivacySecureDeliveryError, issue_synthetic_secure_delivery,
    purge_expired_synthetic_deliveries, redeem_synthetic_secure_delivery,
    revoke_synthetic_secure_delivery,
)
from app.services.shopify_privacy_synthetic_export import (
    EncryptedSyntheticExport, build_encrypted_synthetic_export,
)
from app.services.shopify_privacy_case_assessment import prepare_shopify_privacy_export_manifest
from app.shopify_security import encrypt_shopify_secret

REQUEST = "b" * 64
SHOP = "synthetic-only.myshopify.com"
SYNTHETIC_CONTENT = b"SYNTHETIC_ENCRYPTED_CUSTOMER_DATA_ONLY"


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PRIVACY_SYNTHETIC_HTTP_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_DELIVERY_KEY", Fernet.generate_key().decode())
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(id=101, name="Fixture merchant", slug="merchant-fixture",
                           plan="starter", active=True, subscription_status="active")
        db.add(org)
        db.flush()
        store = Store(id=201, organization_id=org.id, name="Original",
                      slug="original", country_code="CO", currency="COP",
                      timezone="America/Bogota", shopify_domain=SHOP,
                      active=True, deleted=False)
        db.add(store)
        user = User(id=301, name="Synthetic Owner", email="owner@synthetic.test",
                    external_auth_id="synthetic-merchant-sub", active=True)
        db.add(user)
        db.flush()
        member = OrganizationMembership(
            user_id=user.id, organization_id=org.id, role="owner",
            active=True, all_stores=True,
        )
        db.add(member)
        db.add(ShopifyPrivacyRequest(
            request_id=REQUEST, shop_id="321", shop_domain=SHOP,
            organization_id=org.id, store_id=store.id,
            topic="customers/data_request", selector_encrypted="SYNTHETIC_ONLY",
            status="pending_policy_review", attempts=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        db.add(ShopifyPrivacyAuditEvent(
            request_id=REQUEST, event_type="received",
            actor_type="shopify_hmac_verified", reason_code="tenant_bound",
            from_status=None, to_status="pending_policy_review",
            created_at=datetime.utcnow(),
        ))
        db.commit()
        yield db, org, store, user, member
    engine.dispose()


def artifact():
    """Create only a request-bound fabricated fixture, never a live export."""
    return build_encrypted_synthetic_export(
        manifest={
            "request_id": REQUEST, "topic": "customers/data_request",
            "scope_status": "scope_preview_only", "export_generated": False,
            "delivery_authorized": False, "fulfillment_complete": False,
            "sources": [
                {"name": name, "matching_records": int(name == "orders"),
                 "status": "review_required"}
                for name in (
                    "customer_store_profiles", "orders", "conversations",
                    "conversational_checkouts",
                )
            ],
        },
        records=[{
            "source": "orders", "record": "SYNTHETIC",
            "fields": {"order_number": SYNTHETIC_CONTENT.decode()},
        }],
        encryption_key=os.environ["SHOPIFY_PRIVACY_DELIVERY_KEY"].encode("ascii"),
    )


def context(db, org, store, user):
    return dict(db=db, request_id=REQUEST, organization_id=org.id,
                store_id=store.id, recipient_user_id=user.id)


def issue(sandbox):
    db, org, store, user, _ = sandbox
    params = context(db, org, store, user)
    ticket = issue_synthetic_secure_delivery(
        artifact=artifact(), fixture_authorized=True, **params,
    )
    return ticket, params


def test_single_use_encrypted_storage_and_minimal_audit(sandbox):
    ticket, params = issue(sandbox)
    db = params["db"]
    row = db.query(ShopifyPrivacyDeliveryArtifact).one()
    assert "SYNTHETIC_ENCRYPTED" not in row.ciphertext_encrypted
    assert ticket.token not in row.ciphertext_encrypted
    assert ticket.token not in repr(ticket)
    assert row.token_digest == hashlib.sha256(ticket.token.encode()).hexdigest()
    received = redeem_synthetic_secure_delivery(token=ticket.token, **params)
    assert hashlib.sha256(received.ciphertext).hexdigest() == received.sha256
    assert received.synthetic_only is True
    assert received.fulfillment_complete is False
    assert db.query(ShopifyPrivacyDeliveryArtifact).one().ciphertext_encrypted is None
    assert [event.event_type for event in db.query(ShopifyPrivacyDeliveryAudit).all()] == [
        "issued", "redeemed",
    ]
    for item in db.query(ShopifyPrivacyDeliveryAudit):
        assert "SYNTHETIC_ENCRYPTED" not in str(item.__dict__)
        assert ticket.token not in str(item.__dict__)
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNAVAILABLE"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)


def test_wrong_user_store_or_organization_cannot_consume_token(sandbox):
    ticket, params = issue(sandbox)
    db, org, store, user, member = sandbox
    another = User(name="Wrong recipient", email="other@synthetic.test",
                   external_auth_id="second-sub", active=True)
    db.add(another)
    db.add(OrganizationMembership(
        user=another, organization_id=org.id, role="owner",
        active=True, all_stores=True,
    ))
    db.commit()
    for bad in [
        {**params, "recipient_user_id": another.id},
        {**params, "organization_id": 999},
        {**params, "store_id": 999},
    ]:
        with pytest.raises(ShopifyPrivacySecureDeliveryError):
            redeem_synthetic_secure_delivery(token=ticket.token, **bad)
    assert redeem_synthetic_secure_delivery(
        token=ticket.token, **params,
    ).synthetic_only is True


def test_store_restriction_and_role_change_prevent_redemption(sandbox):
    ticket, params = issue(sandbox)
    db, org, store, user, member = sandbox
    member.role = "operator"
    db.commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNAUTHORIZED"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)
    member.role = "owner"
    member.all_stores = False
    db.commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNAUTHORIZED"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)
    db.add(MembershipStore(membership_id=member.id, store_id=store.id))
    db.commit()
    assert redeem_synthetic_secure_delivery(
        token=ticket.token, **params,
    ).synthetic_only is True


def test_expired_ticket_cannot_redeem_and_is_purged(sandbox):
    ticket, params = issue(sandbox)
    row = params["db"].query(ShopifyPrivacyDeliveryArtifact).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    params["db"].commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNAVAILABLE"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)
    assert purge_expired_synthetic_deliveries(params["db"]) == 1
    assert row.ciphertext_encrypted is None
    assert purge_expired_synthetic_deliveries(params["db"]) == 0


def test_revoke_purges_ciphertext_and_cannot_replay(sandbox):
    ticket, params = issue(sandbox)
    assert revoke_synthetic_secure_delivery(
        token=ticket.token, **params,
    ) is True
    assert revoke_synthetic_secure_delivery(
        token=ticket.token, **params,
    ) is False
    assert params["db"].query(ShopifyPrivacyDeliveryArtifact).one().ciphertext_encrypted is None
    with pytest.raises(ShopifyPrivacySecureDeliveryError):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)


def test_missing_signed_intake_or_wrong_topic_cannot_issue(sandbox):
    db, org, store, user, _ = sandbox
    params = context(db, org, store, user)
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="SIGNED_DELIVERY"):
        issue_synthetic_secure_delivery(
            artifact=artifact(), fixture_authorized=True, **params,
        )
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST, event_type="received",
        actor_type="shopify_hmac_verified", reason_code="tenant_bound",
        from_status=None, to_status="pending_policy_review",
        created_at=datetime.utcnow(),
    ))
    db.query(ShopifyPrivacyRequest).one().topic = "customers/redact"
    db.commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="SIGNED_DELIVERY"):
        issue_synthetic_secure_delivery(
            artifact=artifact(), fixture_authorized=True, **params,
        )


@pytest.mark.parametrize("change", [
    {"synthetic_only": False},
    {"delivery_authorized": True},
    {"fulfillment_complete": True},
    {"sha256": "f" * 64},
    {"request_id": "c" * 64},
])
def test_non_synthetic_or_tampered_artifacts_rejected(sandbox, change):
    db, org, store, user, _ = sandbox
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNTRUSTED"):
        issue_synthetic_secure_delivery(
            artifact=replace(artifact(), **change), fixture_authorized=True,
            **context(db, org, store, user),
        )
    assert db.query(ShopifyPrivacyDeliveryArtifact).count() == 0


@pytest.mark.parametrize("ttl", [0, 59, 901, True, "300"])
def test_expiration_bounds(sandbox, ttl):
    db, org, store, user, _ = sandbox
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="TTL_INVALID"):
        issue_synthetic_secure_delivery(
            artifact=artifact(), ttl_seconds=ttl, fixture_authorized=True,
            **context(db, org, store, user),
        )


def test_unset_feature_gate_blocks_even_synthetic_ticket(sandbox, monkeypatch):
    ticket, params = issue(sandbox)
    monkeypatch.delenv("SHOPIFY_PRIVACY_SYNTHETIC_HTTP_ENABLED")
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="LIVE_PRIVACY_DELIVERY_DISABLED"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)


def test_key_mismatch_does_not_consume_token(sandbox, monkeypatch):
    ticket, params = issue(sandbox)
    monkeypatch.setenv("SHOPIFY_PRIVACY_DELIVERY_KEY", Fernet.generate_key().decode())
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="ARTIFACT_INVALID"):
        redeem_synthetic_secure_delivery(token=ticket.token, **params)
    assert params["db"].query(ShopifyPrivacyDeliveryArtifact).one().redeemed_at is None


def test_http_requires_cognito_bearer_and_exact_ticket_and_no_cache(sandbox):
    db, org, store, user, _ = sandbox
    ticket, params = issue(sandbox)
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    url = f"/api/stores/{store.id}/shopify/privacy/cases/{REQUEST}/delivery"
    try:
        with TestClient(app) as client:
            assert client.get(url, headers={
                "X-Privacy-Delivery-Token": ticket.token,
            }).status_code == 401
            with patch(
                "app.api.deps.verify_cognito_access_token",
                return_value={"sub": user.external_auth_id},
            ):
                assert client.get(url, headers={
                    "Authorization": "Bearer synthetic-cognito-token",
                    "X-Privacy-Delivery-Token": "wrong",
                }).status_code == 404
                response = client.get(url, headers={
                    "Authorization": "Bearer synthetic-cognito-token",
                    "X-Privacy-Delivery-Token": ticket.token,
                })
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store, private"
                assert response.headers["x-synthetic-privacy-artifact"] == "true"
                assert response.headers["content-type"] == "application/octet-stream"
                assert response.content.startswith(b"gAAAA")
                assert client.get(url, headers={
                    "Authorization": "Bearer synthetic-cognito-token",
                    "X-Privacy-Delivery-Token": ticket.token,
                }).status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_wrong_request_even_same_store_and_recipient_cannot_redeem_fixture(sandbox):
    db, org, store, user, _ = sandbox
    other = "c" * 64
    db.add(ShopifyPrivacyRequest(
        request_id=other, shop_id="321", shop_domain=SHOP,
        organization_id=org.id, store_id=store.id,
        topic="customers/data_request", selector_encrypted="SYNTHETIC_ONLY",
        status="pending_policy_review", created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    db.add(ShopifyPrivacyAuditEvent(
        request_id=other, event_type="received",
        actor_type="shopify_hmac_verified", reason_code="tenant_bound",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNTRUSTED"):
        issue_synthetic_secure_delivery(
            artifact=artifact(), fixture_authorized=True,
            **{**context(db, org, store, user), "request_id": other},
        )
    # No ticket, no stored fixture and no misleading delivery audit.
    assert db.query(ShopifyPrivacyDeliveryArtifact).count() == 0
    assert db.query(ShopifyPrivacyDeliveryAudit).count() == 0


def test_forged_ciphertext_with_real_data_is_rejected_by_delivery(sandbox):
    db, org, store, user, _ = sandbox
    key = os.environ["SHOPIFY_PRIVACY_DELIVERY_KEY"].encode("ascii")
    valid = artifact()
    plaintext = json.loads(Fernet(key).decrypt(valid.ciphertext))
    plaintext["records"][0]["fields"]["order_number"] = "buyer@example.com"
    ciphertext = Fernet(key).encrypt(json.dumps(plaintext).encode("utf-8"))
    forged = replace(
        valid, ciphertext=ciphertext,
        sha256=hashlib.sha256(ciphertext).hexdigest(),
    )
    with pytest.raises(ShopifyPrivacySecureDeliveryError, match="UNTRUSTED"):
        issue_synthetic_secure_delivery(
            artifact=forged, fixture_authorized=True,
            **context(db, org, store, user),
        )
    assert db.query(ShopifyPrivacyDeliveryArtifact).count() == 0


def test_signed_scope_to_encrypted_fixture_to_single_use_delivery_e2e(
    sandbox, monkeypatch,
):
    """An isolated, entirely synthetic E2E — NEVER live Shopify fulfillment."""
    db, org, store, user, _ = sandbox
    monkeypatch.setenv(
        "SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"),
    )
    customer = Customer(
        organization_id=org.id, name="SYNTHETIC_TEST_BUYER",
        phone="SYNTHETIC_555555",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=org.id, store_id=store.id,
        customer_id=customer.id, external_customer_id="700",
        currency="COP",
    ))
    db.add(Order(
        organization_id=org.id, store_id=store.id,
        customer_id=customer.id, order_number="SYNTHETIC_1001",
        total_amount=100, currency="COP",
    ))
    db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == REQUEST,
    ).update({
        ShopifyPrivacyRequest.selector_encrypted: encrypt_shopify_secret(
            json.dumps({"customer": {"id": 700}})
        ),
    })
    db.commit()
    manifest = prepare_shopify_privacy_export_manifest(db, request_id=REQUEST)
    assert manifest["scope_status"] == "scope_preview_only"
    assert manifest["export_generated"] is False
    assert manifest["delivery_authorized"] is False
    assert manifest["fulfillment_complete"] is False
    by_source = {x["name"]: x["matching_records"] for x in manifest["sources"]}
    assert by_source == {
        "customer_store_profiles": 1, "orders": 1,
        "conversations": 0, "conversational_checkouts": 0,
    }
    records = [
        {"source": "customer_store_profiles", "record": "SYNTHETIC",
         "fields": {"external_customer_id": "SYNTHETIC_700"}},
        {"source": "orders", "record": "SYNTHETIC",
         "fields": {"order_number": "SYNTHETIC_1001"}},
    ]
    key = os.environ["SHOPIFY_PRIVACY_DELIVERY_KEY"].encode("ascii")
    exported = build_encrypted_synthetic_export(
        manifest=manifest, records=records, encryption_key=key,
    )
    ticket = issue_synthetic_secure_delivery(
        artifact=exported, fixture_authorized=True,
        **context(db, org, store, user),
    )
    assert ticket.synthetic_only and ticket.fulfillment_complete is False
    delivery = redeem_synthetic_secure_delivery(
        token=ticket.token, **context(db, org, store, user),
    )
    payload = json.loads(Fernet(key).decrypt(delivery.ciphertext))
    assert payload["request_id"] == REQUEST
    assert payload["records"] == records
    assert payload["synthetic_only"] is True
    assert delivery.fulfillment_complete is False
    with pytest.raises(ShopifyPrivacySecureDeliveryError):
        redeem_synthetic_secure_delivery(
            token=ticket.token, **context(db, org, store, user),
        )
    assert db.query(ShopifyPrivacyRequest).one().status == "pending_policy_review"
    assert db.query(Customer).one().name == "SYNTHETIC_TEST_BUYER"
