"""Supplier variant mapping tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.supplier_variant_mappings import SupplierVariantMapping
from app.models import Organization, Product, ProductVariant, Store
from app.services import supplier_mappings as service


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed(db):
    org = Organization(
        name="Mappings Org",
        slug="supplier-mappings-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Mappings Store",
        slug="supplier-mappings-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    product = Product(
        organization_id=org.id,
        store_id=store.id,
        shopify_product_id="100",
        title="Mapped product",
        description="",
        active=True,
    )
    db.add(product)
    db.flush()
    variant = ProductVariant(
        product_id=product.id,
        shopify_variant_id="101",
        title="Black / M",
        sku="SHOP-101",
        price=29.99,
        currency="USD",
        inventory_quantity=10,
        available=True,
    )
    db.add(variant)
    db.commit()
    return org, store, variant


def test_mapping_crud_and_resolution():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        org, store, variant = _seed(db)
        created = service.upsert_cj_variant_mapping(
            db,
            org.id,
            store.id,
            variant.id,
            external_product_id="CJ-P-1",
            external_variant_id="CJ-V-1",
            external_sku="CJ-SKU-1",
        )
        assert created["mapped"] is True
        assert created["external_variant_id"] == "CJ-V-1"

        listing = service.list_cj_variant_mappings(db, org.id, store.id)
        assert listing["total"] == 1
        assert listing["mapped"] == 1
        assert listing["unmapped"] == 0

        resolved = service.resolve_cj_variant_mapping(
            db,
            org.id,
            store.id,
            shopify_variant_id="101",
        )
        assert resolved is not None
        assert resolved.external_variant_id == "CJ-V-1"

        deleted = service.delete_cj_variant_mapping(
            db,
            org.id,
            store.id,
            variant.id,
        )
        assert deleted["ok"] is True
        assert db.query(SupplierVariantMapping).count() == 0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
