"""Dropi mapping, tenant isolation, order dry-run tests. No external calls."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.supplier_variant_mappings import SupplierVariantMapping
from app.models import (
    CommerceConnection,
    DropiConnection,
    Order,
    OrderItem,
    Organization,
    Product,
    ProductVariant,
    Store,
)
from app.services import dropi_mappings, dropi_readiness


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def seed(db):
    org = Organization(
        name="Dropi Org", slug="dropi-test-org", plan="growth",
        subscription_status="active", active=True,
    )
    outsider = Organization(
        name="Other Org", slug="another-dropi-test-org", plan="growth",
        subscription_status="active", active=True,
    )
    db.add_all([org, outsider])
    db.flush()
    store = Store(
        organization_id=org.id, name="Dropi Shopify", slug="dropi-shop",
        country_code="CO", currency="COP", timezone="America/Bogota",
        default_language="es", active=True, deleted=False,
    )
    db.add(store)
    db.flush()
    product = Product(
        organization_id=org.id, store_id=store.id,
        shopify_product_id="prod-1", title="Product", description="", active=True,
    )
    db.add(product)
    db.flush()
    variant = ProductVariant(
        product_id=product.id, shopify_variant_id="variation-1",
        title="M", sku="SHOP-M", price=20000,
        currency="COP", inventory_quantity=10, available=True,
    )
    db.add(variant)
    db.flush()
    order = Order(
        organization_id=org.id, store_id=store.id,
        shopify_order_id="shopify-123", order_number="ORDER-123",
        total_amount=20000, currency="COP", financial_status="paid",
        payment_status="paid", payment_method="prepaid",
        fulfillment_status="unfulfilled", lifecycle_status="paid",
        source="shopify",
        shipping_address={
            "customer_name": "Jane Private",
            "address1": "Private Street 5",
            "city": "Bogotá", "province": "Cundinamarca", "phone": "3000000000",
            "country_code": "CO", "email": "secret@example.com",
        },
    )
    db.add(order)
    db.flush()
    item = OrderItem(
        order_id=order.id, organization_id=org.id, store_id=store.id,
        product_id=product.id, variant_id=variant.id,
        shopify_variant_id="variation-1", shopify_line_item_id="line-1",
        title="Product", sku="SHOP-M", quantity=1,
        unit_price=20000, currency="COP",
    )
    db.add(item)
    db.add(
        CommerceConnection(
            organization_id=org.id, store_id=store.id, provider="shopify",
            external_store_url="dropi-shop.myshopify.com",
            access_token_encrypted="fake", status="connected",
            connected_at=datetime.utcnow(),
        )
    )
    db.add(
        DropiConnection(
            organization_id=org.id, store_id=store.id,
            api_token_encrypted="do-not-disclose", webhook_token="fake-webhook-id",
            status="verified", connected_at=datetime.utcnow(),
        )
    )
    db.commit()
    return org, outsider, store, product, variant, order, item


def test_scoped_mapping_does_not_modify_cj(db):
    org, outsider, store, _product, variant, order, _item = seed(db)
    created = dropi_mappings.upsert_mapping(
        db, org.id, store.id, variant.id,
        external_product_id="DROP-101",
        external_variant_id="DROP-V-1",
    )
    assert created["mapped"] is True
    assert created["provider"] == "dropi"
    assert dropi_mappings.list_mappings(db, org.id, store.id)["mapped"] == 1

    db.add(
        SupplierVariantMapping(
            organization_id=org.id, store_id=store.id,
            product_variant_id=variant.id, provider="cj",
            external_product_id="CJ-101", external_variant_id="CJ-V-1",
            active=True,
        )
    )
    db.commit()
    with pytest.raises(dropi_mappings.DropiMappingError, match="DROPI_STORE_NOT_FOUND"):
        dropi_mappings.list_mappings(db, outsider.id, store.id)
    with pytest.raises(dropi_readiness.DropiReadinessError, match="DROPI_STORE_NOT_FOUND"):
        dropi_readiness.order_readiness(db, outsider.id, store.id, order.id)

    assert dropi_mappings.delete_mapping(db, org.id, store.id, variant.id)["ok"]
    assert db.query(SupplierVariantMapping).filter(
        SupplierVariantMapping.provider == "cj"
    ).count() == 1


def test_ready_order_maps_products_without_leaking_pii(db):
    org, _outsider, store, _product, variant, order, _item = seed(db)
    dropi_mappings.upsert_mapping(
        db, org.id, store.id, variant.id,
        external_product_id="DROP-P-1", external_variant_id="DROP-V-1",
    )
    preview = dropi_readiness.order_readiness(db, org.id, store.id, order.id)
    assert preview["ready_for_provider_contract_test"] is True
    assert preview["can_send_to_dropi"] is False
    assert preview["rate_type"] == "SIN RECAUDO"
    assert preview["items"][0]["dropi_product_id"] == "DROP-P-1"
    assert preview["idempotency_key"] == dropi_readiness.order_readiness(
        db, org.id, store.id, order.id,
    )["idempotency_key"]
    assert "secret@example.com" not in str(preview)
    assert "Private Street" not in str(preview)
    assert "Jane Private" not in str(preview)


def test_unmapped_order_fails_closed_and_cancelled_order_blocked(db):
    org, _outsider, store, _product, variant, order, item = seed(db)
    readiness = dropi_readiness.order_readiness(db, org.id, store.id, order.id)
    assert readiness["can_send_to_dropi"] is False
    assert "DROPI_VARIANT_UNMAPPED" in readiness["blockers"]

    dropi_mappings.upsert_mapping(
        db, org.id, store.id, variant.id,
        external_product_id="P", external_variant_id="V",
    )
    order.lifecycle_status = "cancelled"
    order.payment_status = "pending"
    order.shipping_address = {"country_code": "PE"}
    db.commit()
    readiness = dropi_readiness.order_readiness(db, org.id, store.id, order.id)
    assert {"PAYMENT_NOT_READY", "ORDER_ALREADY_FINALIZED", "SHIPPING_INCOMPLETE", "SHIPPING_COUNTRY_MISMATCH"}.issubset(
        set(readiness["blockers"])
    )


def test_cross_store_variants_cannot_be_mapped(db):
    org, outsider, store, product, variant, order, item = seed(db)
    with pytest.raises(dropi_mappings.DropiMappingError, match="DROPI_STORE_NOT_FOUND"):
        dropi_mappings.upsert_mapping(
            db, outsider.id, store.id, variant.id,
            external_product_id="X", external_variant_id="Y",
        )
    with pytest.raises(dropi_mappings.DropiMappingError, match="DROPI_VARIANT_NOT_FOUND"):
        dropi_mappings.upsert_mapping(
            db, org.id, store.id, 99999,
            external_product_id="X", external_variant_id="Y",
        )


def test_read_only_connection_status_never_claims_order_permission(db):
    from app.services import dropi_service

    org, _outsider, store, *_ = seed(db)
    status = dropi_service.get_connection(db, org.id, store.id)
    assert status["connected"] is True
    assert status["status"] == "verified"
    assert status["access_mode"] == "read_only"
    assert status["orders_write_enabled"] is False
    assert status["shopify_dropify_coexistence"] == "requires_independent_token_validation"


def test_stock_read_only_uses_separate_dropi_credential_and_never_writes(db, monkeypatch):
    from app.services import dropi_service

    org, outsider, store, *_ = seed(db)
    captured = {}

    def fake_decrypt(value):
        assert value == "do-not-disclose"
        return "private-test-token"

    def fake_provider(token, product_id, *, country_code):
        captured.update({"token": token, "id": product_id, "country": country_code})
        return {"id": 18, "stock": 7, "variations": []}

    monkeypatch.setattr(dropi_service, "decrypt_dropi_secret", fake_decrypt)
    monkeypatch.setattr(dropi_service, "read_product_details", fake_provider)
    result = dropi_service.inspect_product(db, org.id, store.id, "18")
    assert captured == {"token": "private-test-token", "id": "18", "country": "CO"}
    assert result["access_mode"] == "read_only"
    assert result["stock_synced_to_shopify"] is False
    assert "private-test-token" not in str(result)
    with pytest.raises(dropi_service.DropiNotFoundError):
        dropi_service.inspect_product(db, outsider.id, store.id, "18")


def test_stock_read_only_unverified_stops_before_external_call(db, monkeypatch):
    from app.services import dropi_service

    org, _outsider, store, *_ = seed(db)
    connection = db.query(DropiConnection).filter_by(store_id=store.id).one()
    connection.status = "pending_validation"
    db.commit()
    monkeypatch.setattr(dropi_service, "decrypt_dropi_secret", lambda _value: "test-token")

    def forbidden(*args, **kwargs):
        raise AssertionError("Unverified token must not reach Dropi")

    monkeypatch.setattr(dropi_service, "read_product_details", forbidden)
    with pytest.raises(dropi_service.DropiConnectionError, match="DROPPI_NOT_VERIFIED"):
        dropi_service.inspect_product(db, org.id, store.id, "18")


def test_paginated_catalog_comparison_is_tenant_scoped(db, monkeypatch):
    from app.services import dropi_catalog_service, dropi_service
    from app.integrations.dropi_catalog import normalize_product

    org, outsider, store, _product, variant, *_ = seed(db)
    dropi_mappings.upsert_mapping(
        db, org.id, store.id, variant.id,
        external_product_id="44", external_variant_id="50",
    )
    monkeypatch.setattr(dropi_service, "decrypt_dropi_secret", lambda _: "test-token")
    calls = []

    def fake_search(token, *, country_code, page, limit, query):
        calls.append((token, country_code, page, limit, query))
        product = normalize_product({
            "id": 44,
            "name": "Dropi Product",
            "variations": [{"id": 50, "sku": "SHOP-M", "stock": 10}],
        })
        return {
            "page": page, "limit": limit, "query": query,
            "items": [product], "returned": 1, "has_more": False,
            "next_page": None, "total": None,
        }

    monkeypatch.setattr(dropi_catalog_service, "search_products", fake_search)
    result = dropi_catalog_service.list_catalog_page(
        db, org.id, store.id, page=2, limit=5, query="zapatos",
    )
    assert calls == [("test-token", "CO", 2, 5, "zapatos")]
    assert result["access_mode"] == "read_only"
    assert result["shopify_write_performed"] is False
    assert result["unmapped_products"] == 0
    assert result["products_with_differences"] == 0
    assert result["items"][0]["shopify_mappings"][0]["product_variant_id"] == variant.id

    with pytest.raises(dropi_service.DropiNotFoundError):
        dropi_catalog_service.list_catalog_page(db, outsider.id, store.id)


def test_paginated_catalog_does_not_fetch_for_unverified_connection(db, monkeypatch):
    from app.services import dropi_catalog_service, dropi_service

    org, _outsider, store, *_ = seed(db)
    connection = db.query(DropiConnection).filter_by(store_id=store.id).one()
    connection.status = "pending_validation"
    db.commit()
    monkeypatch.setattr(dropi_service, "decrypt_dropi_secret", lambda _: "test-token")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unverified connection should never contact Dropi")

    monkeypatch.setattr(dropi_catalog_service, "search_products", forbidden)
    with pytest.raises(dropi_service.DropiConnectionError, match="DROPPI_NOT_VERIFIED"):
        dropi_catalog_service.list_catalog_page(db, org.id, store.id)
