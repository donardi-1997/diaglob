"""Regression tests for the Customer model-domain extraction."""
from pathlib import Path

from app import models
from app.model_domains.customers import Customer, CustomerStoreProfile


def test_customer_models_keep_legacy_import_identity():
    assert Customer is models.Customer
    assert CustomerStoreProfile is models.CustomerStoreProfile


def test_customer_models_are_physically_defined_in_domain_module():
    assert Customer.__module__ == "app.model_domains.customers"
    assert CustomerStoreProfile.__module__ == "app.model_domains.customers"


def test_customer_models_share_canonical_sqlalchemy_metadata():
    assert Customer.__table__ is models.Base.metadata.tables["customers"]
    assert (
        CustomerStoreProfile.__table__
        is models.Base.metadata.tables["customer_store_profiles"]
    )


def test_customer_table_contract_is_preserved():
    assert set(Customer.__table__.columns.keys()) == {
        "id",
        "organization_id",
        "name",
        "phone",
        "email",
        "country_code",
        "created_at",
    }
    assert set(CustomerStoreProfile.__table__.columns.keys()) == {
        "id",
        "organization_id",
        "customer_id",
        "store_id",
        "external_customer_id",
        "orders_count",
        "total_spent",
        "currency",
        "last_order_ref",
    }
    assert any(
        constraint.name == "uq_customer_store"
        for constraint in CustomerStoreProfile.__table__.constraints
    )


def test_legacy_models_no_longer_defines_customer_classes():
    models_source = (
        Path(models.__file__).read_text(encoding="utf-8")
    )
    assert "class Customer(Base):" not in models_source
    assert "class CustomerStoreProfile(Base):" not in models_source
    assert (
        "from .model_domains.customers import Customer, CustomerStoreProfile"
        in models_source
    )
