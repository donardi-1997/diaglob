"""Synthetic-only privacy scope preview tests."""
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Customer, CustomerStoreProfile, Organization, Order,
    ShopifyPrivacyRequest, Store,
)
from app.services.shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError, preview_shopify_privacy_scope,
)
from app.shopify_security import encrypt_shopify_secret


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic", slug="synthetic", plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for num in (1, 2):
            store = Store(
                organization_id=org.id, name=f"S{num}", slug=f"s{num}",
                country_code="CO", currency="COP", timezone="UTC",
                shopify_domain=f"s{num}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        customer = Customer(organization_id=org.id, name="Test", phone="0")
        db.add(customer)
        db.flush()
        for store in stores:
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, external_customer_id="700",
                currency="COP",
            ))
            db.add(Order(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, order_number=str(store.id),
                total_amount=1, currency="COP",
            ))
        db.flush()
        receipt = ShopifyPrivacyRequest(
            request_id="r" * 64, topic="customers/redact",
            shop_id="1", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700}})
            ),
        )
        db.add(receipt)
        db.commit()
        yield db, receipt


def test_preview_counts_scoped_records_without_changes(setup):
    db, receipt = setup
    result = preview_shopify_privacy_scope(db, receipt)
    assert result.matched_customer_profiles == 1
    assert result.matched_store_orders == 1
    assert result.shared_customers_protected == 1
    assert db.query(CustomerStoreProfile).count() == 2
    assert db.query(Order).count() == 2


def test_preview_rejects_invalid_store_binding(setup):
    db, receipt = setup
    receipt.shop_domain = "wrong.myshopify.com"
    with pytest.raises(ShopifyPrivacyScopeError, match="STORE_MISMATCH"):
        preview_shopify_privacy_scope(db, receipt)
