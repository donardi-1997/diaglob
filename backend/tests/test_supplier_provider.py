"""Tests for the provider-neutral supplier contract and registry."""

import pytest

from app.suppliers import (
    SupplierCapabilityNotSupportedError,
    SupplierProvider,
    SupplierProviderNotRegisteredError,
    SupplierRuntimeContext,
    clear_supplier_registry,
    get_supplier_provider,
    register_supplier_provider,
    registered_supplier_providers,
)


class FakeSupplier(SupplierProvider):
    provider_key = "fake"

    def get_products(self, store_id, query=None, limit=20):
        return [{"id": "p1", "store_id": store_id}]

    def create_order(self, store_id, items, customer=None):
        return {"id": "o1", "store_id": store_id}

    def get_order(self, store_id, order_id):
        return {"id": order_id, "store_id": store_id}

    def get_shipping_quote(self, store_id, items, destination):
        return {"amount": 5.0, "currency": "USD"}


@pytest.fixture(autouse=True)
def reset_registry():
    clear_supplier_registry()
    yield
    clear_supplier_registry()


@pytest.fixture()
def context():
    return SupplierRuntimeContext(
        organization_id=10,
        store_id=20,
        credentials={"access_token": "secret"},
    )


def test_provider_exposes_normalized_key():
    assert FakeSupplier().key() == "fake"


def test_runtime_context_is_tenant_scoped(context):
    provider = FakeSupplier(context)

    assert provider.require_context().organization_id == 10
    assert provider.require_context().store_id == 20
    assert provider.require_context().credentials["access_token"] == "secret"


def test_optional_capability_fails_explicitly():
    provider = FakeSupplier()

    with pytest.raises(SupplierCapabilityNotSupportedError) as exc:
        provider.get_tracking(store_id=1, order_id="o1")

    assert exc.value.provider == "fake"
    assert exc.value.capability == "get_tracking"
    assert exc.value.status_code == 501


def test_registry_resolves_provider_with_context(context):
    register_supplier_provider("FAKE", FakeSupplier)

    provider = get_supplier_provider(" fake ", context)

    assert isinstance(provider, FakeSupplier)
    assert provider.context is context
    assert registered_supplier_providers() == ("fake",)


def test_registry_rejects_duplicate_registration():
    register_supplier_provider("fake", FakeSupplier)

    with pytest.raises(ValueError, match="already registered"):
        register_supplier_provider("fake", FakeSupplier)


def test_registry_can_replace_registration(context):
    register_supplier_provider("fake", FakeSupplier)
    register_supplier_provider("fake", FakeSupplier, replace=True)

    assert isinstance(get_supplier_provider("fake", context), FakeSupplier)


def test_registry_rejects_unknown_provider(context):
    with pytest.raises(SupplierProviderNotRegisteredError):
        get_supplier_provider("cj", context)
