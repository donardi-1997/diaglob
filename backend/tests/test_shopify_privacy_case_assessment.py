"""Privacy case assessment: signed receipt, scoped counts, no unsafe fulfillment."""
import json
from datetime import datetime
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Customer, CustomerStoreProfile, Order, Organization,
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, Store,
)
from app.shopify_security import encrypt_shopify_secret
from app.api.shopify_privacy_backlog import get_shopify_privacy_case_assessment
from app.services.shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError, assess_shopify_privacy_case,
)


REQUEST_ID = "a" * 64


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic assessment", slug="synthetic-assessment",
                           plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for n in (1, 2):
            store = Store(
                organization_id=org.id, name=f"Test{n}", slug=f"test-{n}",
                country_code="CO", currency="COP", timezone="UTC",
                shopify_domain=f"synthetic-{n}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        customer = Customer(
            organization_id=org.id, name="SENSITIVE_BUYER_NAME", phone="555"
        )
        db.add(customer)
        db.flush()
        for store in stores:
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, external_customer_id="700", currency="COP",
            ))
            db.add(Order(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, order_number=f"SENSITIVE_{store.id}",
                total_amount=1, currency="COP",
            ))
        receipt = ShopifyPrivacyRequest(
            request_id=REQUEST_ID, topic="customers/data_request",
            shop_id="PRIVATE_SHOP_ID", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700, "email": "private@example.com"}})
            ),
            status="pending_policy_review",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
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


def test_signed_scope_assessment_is_store_scoped_and_pii_free(sandbox):
    db, receipt = sandbox
    result = assess_shopify_privacy_case(db, request_id=REQUEST_ID)
    assert result is not None
    assert result.verified_signed_intake is True
    assert result.verified_shop_scope is True
    assert result.matched_customer_profiles == 1
    assert result.matched_store_orders == 1
    assert result.shared_customers_protected == 1
    assert result.fulfillment_authorized is False
    assert result.requires_manual_review is True
    assert "LIVE_FULFILLMENT_NOT_IMPLEMENTED" in result.blockers
    assert "DATA_SURFACE_COVERAGE_INCOMPLETE" in result.blockers
    result_dict = result.safe_dict()
    serialized = str(result_dict)
    assert "SENSITIVE" not in serialized
    assert "PRIVATE_SHOP_ID" not in serialized
    assert "private@example.com" not in serialized
    assert "synthetic-1.myshopify.com" not in serialized
    assert "selector_encrypted" not in serialized
    assert db.query(Order).count() == 2
    assert receipt.status == "pending_policy_review"


def test_missing_signed_audit_does_not_decrypt_or_probe_customer(sandbox):
    db, _ = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with patch(
        "app.services.shopify_privacy_case_assessment.preview_shopify_privacy_scope"
    ) as preview:
        result = assess_shopify_privacy_case(db, request_id=REQUEST_ID)
    preview.assert_not_called()
    assert result.verified_signed_intake is False
    assert result.verified_shop_scope is False
    assert result.matched_store_orders == 0
    assert "SIGNED_INTAKE_EVIDENCE_MISSING" in result.blockers


def test_shop_domain_mismatch_fails_closed_without_personal_data(sandbox):
    db, receipt = sandbox
    receipt.shop_domain = "different.myshopify.com"
    db.commit()
    result = assess_shopify_privacy_case(db, request_id=REQUEST_ID)
    assert result.verified_signed_intake is True
    assert result.verified_shop_scope is False
    assert "SHOP_SCOPE_NOT_VERIFIED" in result.blockers
    assert result.matched_store_orders == 0
    assert "different.myshopify.com" not in str(result.safe_dict())


def test_unresolved_subject_never_fakes_verified_scope(sandbox):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 999999999}})
    )
    db.commit()
    result = assess_shopify_privacy_case(db, request_id=REQUEST_ID)
    assert result.scope_status == "subject_unresolved"
    assert result.verified_shop_scope is False
    assert result.matched_store_orders == 0
    assert "SHOPIFY_SUBJECT_UNRESOLVED" in result.blockers


def test_unmapped_tenant_has_no_leak_or_count(sandbox):
    db, receipt = sandbox
    receipt.organization_id = None
    db.commit()
    result = assess_shopify_privacy_case(db, request_id=REQUEST_ID)
    assert result.verified_shop_scope is False
    assert result.matched_store_orders == 0
    assert "SHOP_SCOPE_NOT_VERIFIED" in result.blockers


@pytest.mark.parametrize("request_id", ["foo", "A" * 64, "a" * 63, "", "☃"])
def test_invalid_request_id_rejected(sandbox, request_id):
    db, _ = sandbox
    with pytest.raises(ShopifyPrivacyAssessmentError, match="INVALID_PRIVACY_REQUEST_ID"):
        assess_shopify_privacy_case(db, request_id=request_id)


def test_unknown_receipt_does_not_reveal_data(sandbox):
    db, _ = sandbox
    assert assess_shopify_privacy_case(db, request_id="b" * 64) is None


def test_assessment_endpoint_authenticates_before_any_lookup(sandbox, monkeypatch):
    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-internal-secret")
    with patch(
        "app.api.shopify_privacy_backlog.assess_shopify_privacy_case"
    ) as service:
        with pytest.raises(HTTPException) as error:
            get_shopify_privacy_case_assessment(
                request_id=REQUEST_ID, x_internal_secret="incorrect", db=db
            )
        assert error.value.status_code == 401
        service.assert_not_called()


def test_assessment_endpoint_returns_sanitized_result(sandbox, monkeypatch):
    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-internal-secret")
    data = get_shopify_privacy_case_assessment(
        request_id=REQUEST_ID,
        x_internal_secret="synthetic-internal-secret", db=db,
    )
    assert data["verified_shop_scope"] is True
    assert data["fulfillment_authorized"] is False
    assert "private@example.com" not in str(data)


def test_export_manifest_is_scoped_and_contains_no_personal_data(sandbox):
    from app.services.shopify_privacy_case_assessment import (
        prepare_shopify_privacy_export_manifest,
    )
    db, receipt = sandbox
    manifest = prepare_shopify_privacy_export_manifest(db, request_id=REQUEST_ID)
    sources = {item["name"]: item for item in manifest["sources"]}
    assert sources["orders"]["matching_records"] == 1
    assert sources["customer_store_profiles"]["matching_records"] == 1
    assert manifest["shared_customers_protected"] == 1
    assert all(item["status"] == "review_required" for item in manifest["sources"])
    assert manifest["contains_personal_data"] is False
    assert manifest["export_generated"] is False
    assert manifest["delivery_authorized"] is False
    assert manifest["fulfillment_complete"] is False
    assert receipt.completed_at is None
    for private in ("SENSITIVE", "PRIVATE_SHOP_ID", "private@example.com"):
        assert private not in str(manifest)


def test_export_manifest_rejects_unsigned_and_unresolved_requests(sandbox):
    from app.services.shopify_privacy_case_assessment import (
        prepare_shopify_privacy_export_manifest,
    )
    db, receipt = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyPrivacyAssessmentError,
                       match="SIGNED_INTAKE_EVIDENCE_MISSING"):
        prepare_shopify_privacy_export_manifest(db, request_id=REQUEST_ID)

    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type="received",
        actor_type="shopify_hmac_verified", reason_code="tenant_bound",
        to_status=receipt.status, created_at=datetime.utcnow(),
    ))
    receipt.shop_domain = "incorrect.myshopify.com"
    db.commit()
    with pytest.raises(ShopifyPrivacyAssessmentError,
                       match="SHOPIFY_SUBJECT_UNRESOLVED"):
        prepare_shopify_privacy_export_manifest(db, request_id=REQUEST_ID)


def test_export_manifest_rejects_redaction_topic(sandbox):
    from app.services.shopify_privacy_case_assessment import (
        prepare_shopify_privacy_export_manifest,
    )
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    db.commit()
    with pytest.raises(ShopifyPrivacyAssessmentError,
                       match="CUSTOMER_EXPORT_TOPIC_REQUIRED"):
        prepare_shopify_privacy_export_manifest(db, request_id=REQUEST_ID)
