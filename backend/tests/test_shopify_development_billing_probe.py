"""Strict no-grant tests for Shopify development-store billing observation."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.billing import shopify_development_subscription_probe, router
from app.services.shopify_app_pricing import (
    ShopifyAppPricingError,
    ShopifySubscriptionSnapshot,
)
from app.services.shopify_development_billing_probe import (
    probe_shopify_development_subscription,
)


def _org(provider="shopify"):
    return SimpleNamespace(id=17, billing_provider=provider, active=True, plan="trial")


def _conn(domain="diaglob-poc.myshopify.com"):
    return SimpleNamespace(
        organization_id=17, store_id=23, provider="shopify",
        status="connected", external_store_url=domain,
    )


def _shopify_snapshot(*, active=True, amount="0.00", period="EVERY_30_DAYS"):
    return ShopifySubscriptionSnapshot(
        active=active, billing_period=period,
        item_handles=("private-test-handle",),
        eligible_handles=("private-test-handle",),
        eligible_amounts=(amount,),
    )


def _enabled(monkeypatch):
    monkeypatch.setenv("SHOPIFY_BILLING_TEST_PROBE_ENABLED", "true")
    monkeypatch.setenv(
        "SHOPIFY_BILLING_TEST_SHOP_DOMAIN", "diaglob-poc.myshopify.com"
    )


def test_dev_probe_disabled_by_default_no_shopify_requests(monkeypatch):
    monkeypatch.delenv("SHOPIFY_BILLING_TEST_PROBE_ENABLED", raising=False)
    with patch(
        "app.services.shopify_development_billing_probe.resolve_trusted_shop_gid"
    ) as identity:
        with pytest.raises(ShopifyAppPricingError, match="PROBE_DISABLED"):
            probe_shopify_development_subscription(
                _org(), _conn(), connected_shopify_store_count=1
            )
        identity.assert_not_called()


@pytest.mark.parametrize("domain", [
    "another-shop.myshopify.com",
    "bakata.myshopify.com",
])
def test_dev_probe_refuses_any_store_outside_operator_allowlist(
    monkeypatch, domain,
):
    _enabled(monkeypatch)
    with patch(
        "app.services.shopify_development_billing_probe.resolve_trusted_shop_gid"
    ) as identity:
        with pytest.raises(ShopifyAppPricingError, match="NOT_ALLOWLISTED"):
            probe_shopify_development_subscription(
                _org(), _conn(domain), connected_shopify_store_count=1
            )
        identity.assert_not_called()


@pytest.mark.parametrize("provider,count", [
    ("paddle", 1),
    ("shopify", 0),
    ("shopify", 2),
])
def test_dev_probe_refuses_non_shopify_and_ambiguous_tenants(
    monkeypatch, provider, count,
):
    _enabled(monkeypatch)
    with patch(
        "app.services.shopify_development_billing_probe.resolve_trusted_shop_gid"
    ) as identity:
        with pytest.raises(ShopifyAppPricingError, match="TENANT_REVIEW"):
            probe_shopify_development_subscription(
                _org(provider), _conn(), connected_shopify_store_count=count
            )
        identity.assert_not_called()


@pytest.mark.parametrize("contract,status", [
    (_shopify_snapshot(), "zero_usd_contract_observed_no_grant"),
    (_shopify_snapshot(amount="0"), "zero_usd_contract_observed_no_grant"),
    (_shopify_snapshot(amount="49.00"), "nonzero_contract_observed_no_grant"),
    (_shopify_snapshot(active=False), "no_active_contract"),
    (_shopify_snapshot(amount=None), "unrecognized_contract_no_grant"),
    (_shopify_snapshot(period="WEEKLY"), "unrecognized_contract_no_grant"),
])
def test_development_probe_classifies_partner_evidence_without_grants(
    monkeypatch, contract, status,
):
    _enabled(monkeypatch)
    with patch(
        "app.services.shopify_development_billing_probe.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/999",
    ) as identity, patch(
        "app.services.shopify_development_billing_probe.get_active_shopify_subscription",
        return_value=contract,
    ) as api:
        output = probe_shopify_development_subscription(
            _org(), _conn(), connected_shopify_store_count=1
        )
    identity.assert_called_once()
    api.assert_called_once_with("gid://shopify/Shop/999")
    assert output["status"] == status
    assert output["commercial_entitlements_granted"] is False
    assert output["applied"] is False
    assert output["requires_review"] is True
    assert "private-test-handle" not in str(output)
    assert "gid://shopify/Shop/" not in str(output)
    assert "diaglob-poc.myshopify.com" not in str(output)


def _membership(role="owner", provider="shopify"):
    return SimpleNamespace(role=role, organization_id=17, organization=_org(provider))


def _db(*connections):
    db = MagicMock()
    scoped = db.query.return_value.filter.return_value
    scoped.limit.return_value.all.return_value = list(connections)
    scoped.first.return_value = SimpleNamespace(
        id=23, active=True, deleted=False, organization_id=17
    )
    return db


def test_dev_probe_route_is_get_only_and_requires_owner(monkeypatch):
    assert any(
        route.path == "/api/billing/shopify/development-probe"
        and route.methods == {"GET"}
        for route in router.routes
    )
    _enabled(monkeypatch)
    for role in ["manager", "operator", "viewer"]:
        db = _db(_conn())
        with patch("app.api.billing.probe_shopify_development_subscription") as svc:
            with pytest.raises(HTTPException) as exc:
                shopify_development_subscription_probe(
                    membership=_membership(role), db=db
                )
            assert exc.value.status_code == 403
            db.query.assert_not_called()
            svc.assert_not_called()


def test_dev_probe_route_disabled_before_query(monkeypatch):
    monkeypatch.delenv("SHOPIFY_BILLING_TEST_PROBE_ENABLED", raising=False)
    db = _db(_conn())
    with pytest.raises(HTTPException) as exc:
        shopify_development_subscription_probe(
            membership=_membership(), db=db
        )
    assert exc.value.status_code == 404
    db.query.assert_not_called()


def test_dev_probe_route_never_changes_tenant_or_exposes_provider_errors(monkeypatch):
    _enabled(monkeypatch)
    db = _db(_conn())
    with patch(
        "app.api.billing.probe_shopify_development_subscription",
        side_effect=ShopifyAppPricingError("unexpected-token-value")
    ):
        with pytest.raises(HTTPException) as exc:
            shopify_development_subscription_probe(
                membership=_membership(), db=db
            )
    assert exc.value.status_code == 503
    assert exc.value.detail == {"code": "SHOPIFY_TEST_PROBE_UNAVAILABLE"}
    db.commit.assert_not_called()
    db.add.assert_not_called()


def test_dev_probe_route_refuses_non_shopify_before_query(monkeypatch):
    _enabled(monkeypatch)
    db = _db(_conn())
    with pytest.raises(HTTPException) as exc:
        shopify_development_subscription_probe(
            membership=_membership(provider="paddle"), db=db
        )
    assert exc.value.status_code == 409
    db.query.assert_not_called()


def test_dev_probe_route_only_queries_verification_service(monkeypatch):
    _enabled(monkeypatch)
    db = _db(_conn())
    evidence = {
        "status": "zero_usd_contract_observed_no_grant",
        "organization_id": 17,
        "contract_observed": True,
        "billing_period": "EVERY_30_DAYS",
        "requires_review": True,
        "applied": False,
        "commercial_entitlements_granted": False,
    }
    with patch(
        "app.api.billing.probe_shopify_development_subscription",
        return_value=evidence,
    ) as svc:
        result = shopify_development_subscription_probe(
            membership=_membership(), db=db
        )
    assert result == evidence
    svc.assert_called_once()
    db.commit.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize("legacy_field", [
    "billing_customer_id", "billing_subscription_id", "billing_price_id"
])
def test_dev_probe_does_not_cross_mixed_legacy_billing_provenance(
    monkeypatch, legacy_field,
):
    _enabled(monkeypatch)
    org = _org()
    setattr(org, legacy_field, "legacy-paddle-reference")
    with patch(
        "app.services.shopify_development_billing_probe.resolve_trusted_shop_gid"
    ) as identity:
        with pytest.raises(ShopifyAppPricingError, match="TENANT_REVIEW"):
            probe_shopify_development_subscription(
                org, _conn(), connected_shopify_store_count=1
            )
        identity.assert_not_called()
