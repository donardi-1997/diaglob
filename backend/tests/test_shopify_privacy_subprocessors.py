"""Synthetic SQLite checks for the Shopify privacy subprocessor manifest.

Manifest completeness, per-shop activation counts, tenant isolation and the
fail-closed posture of every entry. No provider is contacted and no stored
credential, email or object key may ever appear in any result.
"""
import json
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.model_domains.knowledge import KnowledgeBase, KnowledgeSource
from app.model_domains.paddle_billing import PaddleBillingCustomer
from app.models import (
    CommerceConnection,
    Customer,
    CustomerStoreProfile,
    Organization,
    PaymentConnection,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    Store,
)
from app.services.shopify_privacy_controls import (
    PROCESSOR_CONTROLS,
    ShopifyPrivacyControlError,
)
from app.services.shopify_privacy_subprocessors import (
    SUBPROCESSOR_MANIFEST,
    ShopifyPrivacySubprocessorError,
    inspect_shopify_privacy_case_subprocessors,
    inspect_shopify_privacy_subprocessors,
)
from app.shopify_security import encrypt_shopify_secret


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org_a = Organization(name="Org A", slug="org-a", plan="starter")
        org_b = Organization(name="Org B", slug="org-b", plan="starter")
        db.add_all([org_a, org_b])
        db.flush()
        stores = {}
        for suffix, org in (("a", org_a), ("b", org_a), ("c", org_b)):
            store = Store(
                organization_id=org.id, name=f"Store {suffix}",
                slug=f"store-{suffix}", country_code="CO", currency="COP",
                timezone="UTC", shopify_domain=f"{suffix}.myshopify.com",
            )
            db.add(store)
            stores[suffix] = store
        db.flush()

        buyer = Customer(
            organization_id=org_a.id,
            name="PII_SECRET_BUYER_NAME",
            phone="+573001112233",
        )
        db.add(buyer)
        db.flush()
        db.add(CustomerStoreProfile(
            organization_id=org_a.id, store_id=stores["a"].id,
            customer_id=buyer.id, external_customer_id="700", currency="COP",
        ))

        db.add_all([
            CommerceConnection(
                organization_id=org_a.id, store_id=stores["a"].id,
                provider="shopify", external_store_url="a.myshopify.com",
                status="connected",
            ),
            CommerceConnection(
                organization_id=org_a.id, store_id=stores["b"].id,
                provider="nuvemshop", external_store_url="b.nuvemshop.com",
                status="connected",
            ),
            PaymentConnection(
                organization_id=org_a.id, store_id=stores["a"].id,
                provider="nequi", status="connected",
            ),
            PaddleBillingCustomer(
                customer_id="cusc_test_a", organization_id=org_a.id,
                email="billing-secret@example.com",
            ),
        ])
        kb = KnowledgeBase(
            organization_id=org_a.id, name="KB Org A", scope="organization",
        )
        db.add(kb)
        db.flush()
        db.add(KnowledgeSource(
            organization_id=org_a.id, knowledge_base_id=kb.id, name="Doc",
            s3_bucket="diaglob-bucket",
            s3_key="organizations/1/knowledge-bases/1/documents/secret-doc.pdf",
        ))
        db.commit()

        store_ids = {key: store.id for key, store in stores.items()}
        org_ids = {"a": org_a.id, "b": org_b.id}
        yield db, org_ids, store_ids
    engine.dispose()


def _items(result):
    return {item["key"]: item for item in result["subprocessors"]}


def test_manifest_controls_match_processor_controls_exactly():
    referenced = {entry.control for entry in SUBPROCESSOR_MANIFEST}
    assert referenced == set(PROCESSOR_CONTROLS)
    keys = [entry.key for entry in SUBPROCESSOR_MANIFEST]
    assert len(keys) == len(set(keys))
    for entry in SUBPROCESSOR_MANIFEST:
        assert entry.purpose
        assert entry.data_categories
        assert entry.scope in {"store", "organization", "manual"}


def test_activation_counts_are_scoped_to_one_store(db):
    db, org_ids, store_ids = db
    result = inspect_shopify_privacy_subprocessors(
        db, organization_id=org_ids["a"], store_id=store_ids["a"],
    )
    items = _items(result)
    assert items["shopify_admin_api"]["activation"] == "connected"
    # The nuvemshop connection belongs to store b of the same organization.
    assert items["nuvemshop_admin_api"]["activation"] == "not_detected"
    assert items["nequi_payments"]["activation"] == "connected"
    assert items["mercado_pago_payments"]["activation"] == "not_detected"
    # Organization-scoped processors are visible from every store of org A.
    assert items["paddle_billing"]["activation"] == "present_unverified"
    assert items["aws_bedrock"]["activation"] == "connected"
    assert items["files_and_object_storage"]["activation"] == "present_unverified"
    # No detector exists for email delivery; it must never be assumed inactive.
    assert items["email_delivery"]["activation"] == "manual_confirmation_required"
    assert items["dropi_supplier"]["activation"] == "not_detected"
    assert result["active_processor_count"] == 5


def test_activation_is_never_inferred_from_another_organization(db):
    db, org_ids, store_ids = db
    result = inspect_shopify_privacy_subprocessors(
        db, organization_id=org_ids["b"], store_id=store_ids["c"],
    )
    items = _items(result)
    assert items["shopify_admin_api"]["activation"] == "not_detected"
    assert items["nequi_payments"]["activation"] == "not_detected"
    assert items["paddle_billing"]["activation"] == "not_detected"
    assert items["aws_bedrock"]["activation"] == "not_detected"
    assert items["files_and_object_storage"]["activation"] == "not_detected"
    assert result["active_processor_count"] == 0


def test_every_entry_stays_unverified_and_fail_closed(db):
    db, org_ids, store_ids = db
    result = inspect_shopify_privacy_subprocessors(
        db, organization_id=org_ids["a"], store_id=store_ids["a"],
    )
    for item in result["subprocessors"]:
        assert item["verification_status"] == "unverified"
        assert item["independently_verified"] is False
        assert item["external_erasure_verified"] is False
        assert isinstance(item["connection_rows"], int)
    assert result["controls_without_manifest_entry"] == []
    assert result["manifest_entries_without_control"] == []
    assert result["independently_verified"] is False
    assert result["external_erasure_verified"] is False
    assert result["fulfillment_complete"] is False


def test_results_never_contain_credentials_emails_or_object_keys(db):
    db, org_ids, store_ids = db
    result = inspect_shopify_privacy_subprocessors(
        db, organization_id=org_ids["a"], store_id=store_ids["a"],
    )
    rendered = str(result)
    assert "billing-secret@example.com" not in rendered
    assert "PII_SECRET_BUYER_NAME" not in rendered
    assert "+573001112233" not in rendered
    assert "secret-doc.pdf" not in rendered
    assert "a.myshopify.com" not in rendered


def test_tenant_identifiers_are_validated_before_any_query(db):
    db, org_ids, store_ids = db
    with pytest.raises(ShopifyPrivacySubprocessorError) as bad_org:
        inspect_shopify_privacy_subprocessors(
            db, organization_id=True, store_id=store_ids["a"],
        )
    assert str(bad_org.value) == "UNVERIFIED_SUBPROCESSOR_ORGANIZATION_ID"
    with pytest.raises(ShopifyPrivacySubprocessorError) as bad_store:
        inspect_shopify_privacy_subprocessors(
            db, organization_id=org_ids["a"], store_id=0,
        )
    assert str(bad_store.value) == "UNVERIFIED_SUBPROCESSOR_STORE_ID"
    with pytest.raises(ShopifyPrivacySubprocessorError) as cross_tenant:
        inspect_shopify_privacy_subprocessors(
            db, organization_id=org_ids["b"], store_id=store_ids["a"],
        )
    assert str(cross_tenant.value) == "SUBPROCESSOR_SHOP_NOT_FOUND"


def test_case_view_requires_signed_intake_and_verified_shop(db):
    db, org_ids, store_ids = db
    receipt = ShopifyPrivacyRequest(
        request_id="a" * 64,
        topic="customers/data_request",
        shop_id="111",
        shop_domain="a.myshopify.com",
        organization_id=org_ids["a"],
        store_id=store_ids["a"],
        selector_encrypted=encrypt_shopify_secret(
            json.dumps({"customer": {"id": 700}})
        ),
    )
    db.add(receipt)
    db.commit()

    with pytest.raises(ShopifyPrivacyControlError) as unsigned:
        inspect_shopify_privacy_case_subprocessors(
            db, request_id=receipt.request_id,
        )
    assert str(unsigned.value) == "SIGNED_INTAKE_REQUIRED"

    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type="received", actor_type="shopify_hmac_verified",
        from_status=None, to_status="pending_policy_review",
        reason_code="tenant_bound", created_at=datetime.utcnow(),
    ))
    db.commit()

    result = inspect_shopify_privacy_case_subprocessors(
        db, request_id=receipt.request_id,
    )
    assert result["shop_scope"] == "customer_scope_preview_only"
    assert result["request_id"] == receipt.request_id
    assert result["fulfillment_complete"] is False
    assert "billing-secret@example.com" not in str(result)
