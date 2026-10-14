"""Shopify GDPR work items: signed provenance, tenant isolation, safe retries."""
import json
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Customer,
    CustomerStoreProfile,
    Order,
    Organization,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacyWorkItem,
    Store,
)
from app.api.shopify_privacy_backlog import (
    get_shopify_privacy_case_processing,
    prepare_shopify_privacy_case,
    prepare_pending_shopify_privacy_cases,
)
from app.services.shopify_privacy_processing import (
    ShopifyPrivacyProcessingError,
    get_shopify_privacy_processing_case,
    prepare_shopify_privacy_processing_case,
    prepare_pending_shopify_privacy_processing_cases,
)
from app.shopify_security import encrypt_shopify_secret

REQUEST_ID = "f" * 64


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic privacy work", slug="synthetic-privacy-work",
                           plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for num in (1, 2):
            store = Store(
                organization_id=org.id, name=f"Synthetic{num}", slug=f"synthetic-{num}",
                country_code="CO", currency="COP", timezone="UTC",
                shopify_domain=f"synthetic-privacy-{num}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        buyer = Customer(organization_id=org.id, name="SENSITIVE_CUSTOMER", phone="555")
        db.add(buyer)
        db.flush()
        for store in stores:
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=store.id, customer_id=buyer.id,
                external_customer_id="700", currency="COP",
            ))
            db.add(Order(
                organization_id=org.id, store_id=store.id, customer_id=buyer.id,
                order_number=f"SENSITIVE_ORDER_{store.id}", total_amount=2,
                currency="COP", note=f"SENSITIVE_NOTE_{store.id}",
            ))
        receipt = ShopifyPrivacyRequest(
            request_id=REQUEST_ID, topic="customers/data_request",
            shop_id="private-shop-id", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(json.dumps({
                "customer": {"id": 700, "email": "buyer_private@example.com"},
                "orders_requested": [12345],
            })),
            status="pending_policy_review",
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(receipt)
        db.add(ShopifyPrivacyAuditEvent(
            request_id=REQUEST_ID, event_type="received",
            from_status=None, to_status="pending_policy_review",
            reason_code="tenant_bound", actor_type="shopify_hmac_verified",
            created_at=datetime.utcnow(),
        ))
        db.commit()
        yield db, receipt
    engine.dispose()


@pytest.mark.parametrize("topic", [
    "customers/data_request", "customers/redact", "shop/redact",
])
def test_signed_intake_creates_durable_tasks_without_fulfillment(sandbox, topic):
    db, receipt = sandbox
    receipt.topic = topic
    db.commit()

    result = prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    assert result["created"] is True
    assert result["topic"] == topic
    assert result["fulfillment_complete"] is False
    assert result["fulfillment_authorized"] is False
    assert result["requires_manual_review"] is True
    assert len(result["work_items"]) == 10
    tasks = {item["area"]: item for item in result["work_items"]}
    assert tasks["signed_receipt"]["status"] == "verified"
    assert tasks["shop_identity"]["status"] == "verified"
    assert tasks["local_structured_records"]["status"] == "blocked"
    if topic == "customers/data_request":
        assert "merchant_delivery" in tasks
        assert "reimport_suppression" not in tasks
        assert tasks["merchant_delivery"]["status"] == "blocked"
    else:
        assert "merchant_delivery" not in tasks
        assert "reimport_suppression" in tasks
        assert tasks["reimport_suppression"]["status"] == "blocked"

    assert receipt.status == "pending_policy_review"
    assert receipt.completed_at is None
    assert db.query(Order).count() == 2
    assert db.query(CustomerStoreProfile).count() == 2
    assert db.query(Customer).one().name == "SENSITIVE_CUSTOMER"
    assert db.query(ShopifyPrivacyWorkItem).count() == 10
    serialized = str(result)
    for secret in ("SENSITIVE", "buyer_private", "private-shop-id",
                   "synthetic-privacy-1.myshopify.com"):
        assert secret not in serialized


def test_idempotent_retry_has_single_audit_and_no_new_tasks(sandbox):
    db, receipt = sandbox
    first = prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    second = prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    assert first["created"] is True
    assert second["created"] is False
    assert first["work_items"] == second["work_items"]
    assert db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.event_type == "processing_prepared",
    ).count() == 1
    assert db.query(ShopifyPrivacyWorkItem).count() == 10
    assert receipt.status == "pending_policy_review"


def test_missing_signed_audit_rejected_without_creating_tasks(sandbox):
    db, _ = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyPrivacyProcessingError,
                       match="SIGNED_INTAKE_EVIDENCE_MISSING"):
        prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    assert db.query(ShopifyPrivacyWorkItem).count() == 0


def test_unresolved_subject_becomes_blocked_not_guessed(sandbox):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 99999999}})
    )
    db.commit()
    result = prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    tasks = {x["area"]: x for x in result["work_items"]}
    assert tasks["signed_receipt"]["status"] == "verified"
    assert tasks["shop_identity"]["status"] == "blocked"
    assert tasks["subject_linkage"]["blocker_code"] == "SUBJECT_OR_STORE_UNRESOLVED"
    assert receipt.completed_at is None


def test_shop_domain_mismatch_stops_verified_identity(sandbox):
    db, receipt = sandbox
    receipt.shop_domain = "other.myshopify.com"
    db.commit()
    result = prepare_shopify_privacy_processing_case(db, request_id=REQUEST_ID)
    tasks = {x["area"]: x for x in result["work_items"]}
    assert tasks["shop_identity"]["status"] == "blocked"
    assert db.query(Order).count() == 2


@pytest.mark.parametrize("request_id", ["", "x", "F" * 64, "a" * 63])
def test_invalid_id_fails_closed(sandbox, request_id):
    db, _ = sandbox
    with pytest.raises(ShopifyPrivacyProcessingError,
                       match="INVALID_PRIVACY_REQUEST_ID"):
        prepare_shopify_privacy_processing_case(db, request_id=request_id)
    with pytest.raises(ShopifyPrivacyProcessingError,
                       match="INVALID_PRIVACY_REQUEST_ID"):
        get_shopify_privacy_processing_case(db, request_id=request_id)


def test_unknown_case_not_created(sandbox):
    db, _ = sandbox
    assert prepare_shopify_privacy_processing_case(
        db, request_id="a" * 64,
    ) is None
    assert get_shopify_privacy_processing_case(
        db, request_id="a" * 64,
    ) is None


def test_internal_api_auth_before_db_operation(sandbox, monkeypatch):
    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "strong-internal-test-secret")
    with pytest.raises(HTTPException) as err:
        prepare_shopify_privacy_case(
            request_id=REQUEST_ID, x_internal_secret="invalid", db=db,
        )
    assert err.value.status_code == 401
    assert db.query(ShopifyPrivacyWorkItem).count() == 0

    response = prepare_shopify_privacy_case(
        request_id=REQUEST_ID,
        x_internal_secret="strong-internal-test-secret", db=db,
    )
    assert response["created"] is True
    got = get_shopify_privacy_case_processing(
        request_id=REQUEST_ID,
        x_internal_secret="strong-internal-test-secret", db=db,
    )
    assert got["created"] is False
    assert got["work_items"] == response["work_items"]


def test_work_items_keep_no_customer_or_store_foreign_keys(sandbox):
    db, _ = sandbox
    model = ShopifyPrivacyWorkItem.__table__
    assert not model.foreign_keys
    assert "selector_encrypted" not in model.columns
    assert "payload" not in model.columns


def test_bulk_preparation_skips_already_prepared_cases(sandbox):
    db, _ = sandbox
    first = prepare_pending_shopify_privacy_processing_cases(db, limit=10)
    assert first["examined"] == 1
    assert first["created"] == 1
    assert first["errors"] == []
    second = prepare_pending_shopify_privacy_processing_cases(db, limit=10)
    assert second["examined"] == 0
    assert second["created"] == 0
    assert db.query(ShopifyPrivacyWorkItem).count() == 10


@pytest.mark.parametrize("limit", [0, 51, True, "10"])
def test_batch_limit_must_be_bounded_integer(sandbox, limit):
    db, _ = sandbox
    with pytest.raises(ShopifyPrivacyProcessingError,
                       match="INVALID_PRIVACY_BATCH_LIMIT"):
        prepare_pending_shopify_privacy_processing_cases(db, limit=limit)


def test_bulk_endpoint_requires_internal_authentication(sandbox, monkeypatch):
    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "strong-internal-test-secret")
    with pytest.raises(HTTPException) as error:
        prepare_pending_shopify_privacy_cases(
            limit=10, x_internal_secret="no", db=db,
        )
    assert error.value.status_code == 401
    assert db.query(ShopifyPrivacyWorkItem).count() == 0
    outcome = prepare_pending_shopify_privacy_cases(
        limit=10, x_internal_secret="strong-internal-test-secret", db=db,
    )
    assert outcome["created"] == 1
    assert outcome["fulfillment_complete"] is False
