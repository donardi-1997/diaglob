"""Protected Shopify customer fields must never bleed across independent stores.

Synthetic SQLite only: no tokens, real PII, network, or production records.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Customer, CustomerStoreProfile, Organization, Store
from app.services.shopify_webhook_service import _upsert_customer


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(
            id=7201, name="Fixture merchant", slug="pcd-shopify-fixture",
            plan="pro", subscription_status="active",
        )
        alpha = Store(
            id=7202, organization_id=7201, name="Shopify Alpha",
            slug="shopify-alpha-pcd", country_code="CO", currency="COP",
            timezone="America/Bogota", shopify_domain="alpha.myshopify.com",
            active=True, deleted=False,
        )
        beta = Store(
            id=7203, organization_id=7201, name="Shopify Beta",
            slug="shopify-beta-pcd", country_code="CO", currency="COP",
            timezone="America/Bogota", shopify_domain="beta.myshopify.com",
            active=True, deleted=False,
        )
        db.add_all([org, alpha, beta])
        db.commit()
        yield db, alpha, beta
    engine.dispose()


def _payload(*, customer_id=None, name="Fixture Buyer", email="shared@example.invalid", phone="+570000000001"):
    customer = {
        "first_name": name.split(" ")[0],
        "last_name": " ".join(name.split(" ")[1:]),
        "email": email, "phone": phone,
    }
    if customer_id is not None:
        customer["id"] = customer_id
    return {"customer": customer, "shipping_address": {"country_code": "CO"}}


def test_same_email_and_phone_from_two_shops_cannot_merge_distinct_buyers(sandbox):
    db, alpha, beta = sandbox
    first = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Alpha Original",
    ))
    db.commit()
    second = _upsert_customer(db, store=beta, payload=_payload(
        customer_id=222, name="Beta Buyer",
    ))
    db.commit()
    assert first.id != second.id
    assert db.query(Customer).count() == 2
    assert db.query(CustomerStoreProfile).filter_by(
        store_id=beta.id, external_customer_id="222",
    ).one().customer_id == second.id
    db.refresh(first)
    assert first.name == "Alpha Original"


def test_same_shop_different_shopify_ids_with_same_contact_do_not_merge(sandbox):
    db, alpha, _ = sandbox
    original = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Buyer One",
    ))
    db.commit()
    other = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=222, name="Buyer Two",
    ))
    db.commit()
    assert original.id != other.id
    assert db.query(CustomerStoreProfile).filter_by(store_id=alpha.id).count() == 2
    db.refresh(original)
    assert original.name == "Buyer One"


def test_verified_same_store_shopify_customer_id_updates_its_profile(sandbox):
    db, alpha, _ = sandbox
    original = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Original Name",
    ))
    db.commit()
    updated = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Updated Name", phone="+570000000002",
    ))
    db.commit()
    assert original.id == updated.id
    assert updated.name == "Updated Name"
    assert updated.phone == "+570000000002"
    assert db.query(Customer).count() == 1


def test_guest_order_contact_fallback_only_reuses_guest_profile_in_same_store(sandbox):
    db, alpha, beta = sandbox
    guest = _upsert_customer(db, store=alpha, payload=_payload(customer_id=None))
    db.commit()
    same = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=None, name="Guest Changed",
    ))
    db.commit()
    assert same.id == guest.id
    other_shop = _upsert_customer(db, store=beta, payload=_payload(
        customer_id=None, name="Other Guest",
    ))
    db.commit()
    assert other_shop.id != guest.id
    db.refresh(guest)
    assert guest.name == "Guest Changed"


def test_guest_cannot_reuse_registered_customer_or_cross_store_identity(sandbox):
    db, alpha, beta = sandbox
    registered = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Registered Buyer",
    ))
    db.commit()
    guest = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=None, name="Unlinked Guest",
    ))
    db.commit()
    assert guest.id != registered.id
    from_other_store = _upsert_customer(db, store=beta, payload=_payload(
        customer_id=None, name="Beta Guest",
    ))
    db.commit()
    assert from_other_store.id not in (registered.id, guest.id)


def test_legacy_shared_customer_does_not_overwrite_another_stores_pcd(sandbox):
    db, alpha, beta = sandbox
    shared = _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Original Shared",
    ))
    db.commit()
    db.add(CustomerStoreProfile(
        customer_id=shared.id, organization_id=alpha.organization_id,
        store_id=beta.id, external_customer_id="222", currency="COP",
    ))
    db.commit()
    _upsert_customer(db, store=alpha, payload=_payload(
        customer_id=111, name="Attempted Overwrite", phone="+570000000007",
    ))
    db.commit()
    db.refresh(shared)
    assert shared.name == "Original Shared"
    assert shared.phone == "+570000000001"
    assert db.query(CustomerStoreProfile).filter_by(customer_id=shared.id).count() == 2


def test_suppression_rejects_even_guest_contact_fallback(sandbox):
    db, alpha, _ = sandbox
    guest = _upsert_customer(db, store=alpha, payload=_payload(customer_id=None))
    db.commit()
    other = _upsert_customer(
        db, store=alpha, payload=_payload(customer_id=None, name="No Relink"),
        allow_contact_fallback=False,
    )
    db.commit()
    assert guest.id != other.id
