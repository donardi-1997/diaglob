"""Block C: store visibility and product purchasability contract.

Uses only synthetic organizations, shops, products and no Shopify credentials.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Organization, OrganizationMembership, Product, ProductVariant, Store, User
from app.api.products import (
    get_allowed_store_ids,
    get_commerce_product,
    list_commerce_products,
    serialize_commerce_product,
)
from app.api.deps import (
    get_store_scope,
    get_allowed_store_ids as get_global_allowed_store_ids,
)


@pytest.fixture
def world():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Store A org", slug="store-a-org", plan="growth", active=True)
        foreign = Organization(name="Store B org", slug="store-b-org", plan="growth", active=True)
        db.add_all([org, foreign])
        db.flush()

        def store(name, slug, org_id, active=True, deleted=False):
            s = Store(
                organization_id=org_id, name=name, slug=slug, country_code="CO",
                currency="COP", timezone="America/Bogota", default_language="es",
                active=active, deleted=deleted,
            )
            db.add(s)
            db.flush()
            return s

        local = store("Active Pet Home", "active-pet-home", org.id)
        suspended = store("Suspended", "suspended", org.id, active=False)
        deleted = store("Deleted", "deleted", org.id, deleted=True)
        other_tenant = store("Foreign", "foreign", foreign.id)
        user = User(name="Reviewer", email="reviewer@fixture.invalid", active=True)
        db.add(user)
        db.flush()
        member = OrganizationMembership(
            organization_id=org.id, user_id=user.id,
            role="manager", all_stores=False, active=True,
        )
        # Corrupt/old store assignments must never grant cross-tenant or
        # soft-deleted/suspended store access.
        member.stores = [local, suspended, deleted, other_tenant]
        db.add(member)
        db.commit()
        yield db, org, local, suspended, deleted, other_tenant, member
    engine.dispose()


def make_product(db, org_id, store_id, *, active=True, price=25000,
                 stock=4, provider_available=True):
    product = Product(
        organization_id=org_id, store_id=store_id,
        title=f"Pet Home product {store_id}", active=active,
    )
    db.add(product)
    db.flush()
    db.add(ProductVariant(
        product_id=product.id, title="Default", price=price, currency="COP",
        inventory_quantity=stock, available=provider_available,
    ))
    db.commit()
    db.refresh(product)
    return product


@pytest.mark.parametrize("price,stock,provider_available,active,expected,reason", [
    (0, 5, True, True, False, "invalid_price"),
    (10000, 0, True, True, False, "stock_not_verified"),
    (10000, -4, True, True, False, "stock_not_verified"),
    (10000, 5, False, True, False, "unavailable"),
    (10000, 5, True, False, False, "inactive_product"),
    (10000, 5, True, True, True, "in_stock"),
])
def test_commerce_api_agrees_with_ai_and_checkout_purchase_guard(
    world, price, stock, provider_available, active, expected, reason,
):
    db, org, local, _, _, _, _ = world
    product = make_product(
        db, org.id, local.id, active=active, price=price,
        stock=stock, provider_available=provider_available,
    )
    row = serialize_commerce_product(product)["variants"][0]
    assert row["available"] is expected
    assert row["availability_reason"] == reason
    # Raw provider boolean must not be exposed as "available" to clients.
    assert row["inventory_quantity"] == stock


def test_global_catalog_never_lists_suspended_deleted_or_foreign_shop(world):
    db, org, local, suspended, deleted, foreign, member = world
    p = make_product(db, org.id, local.id)
    paused = make_product(db, org.id, suspended.id)
    removed = make_product(db, org.id, deleted.id)
    outsider = make_product(db, foreign.organization_id, foreign.id)
    draft = make_product(db, org.id, local.id, active=False)

    # Unlimited role must still respect the selected organization's active
    # non-deleted store visibility.
    member.all_stores = True
    db.commit()
    response = list_commerce_products(q=None, membership=member, store=None, db=db)
    assert response["total"] == 1
    assert [item["id"] for item in response["items"]] == [p.id]

    for hidden_id in (paused.id, removed.id, outsider.id):
        with pytest.raises(HTTPException) as exc:
            get_commerce_product(
                hidden_id, membership=member, store=None, db=db,
            )
        assert exc.value.status_code == 404

    # Draft may be inspected by permitted staff but cannot be purchased.
    details = get_commerce_product(draft.id, membership=member, store=None, db=db)
    assert details["variants"][0]["available"] is False
    assert details["variants"][0]["availability_reason"] == "inactive_product"


def test_restricted_member_never_inherits_suspended_deleted_or_cross_tenant(world):
    db, org, local, suspended, deleted, foreign, member = world
    assert get_allowed_store_ids(member) == [local.id]
    assert get_global_allowed_store_ids(member) == [local.id]

    visible = make_product(db, org.id, local.id)
    make_product(db, org.id, suspended.id)
    make_product(db, org.id, deleted.id)
    listing = list_commerce_products(q=None, membership=member, store=None, db=db)
    assert [x["id"] for x in listing["items"]] == [visible.id]

    for not_allowed in (suspended, deleted, foreign):
        with pytest.raises(HTTPException) as exc:
            get_store_scope(membership=member, x_store_id=not_allowed.id, db=db)
        assert exc.value.status_code == 404

    scoped = get_store_scope(membership=member, x_store_id=local.id, db=db)
    assert scoped.id == local.id
