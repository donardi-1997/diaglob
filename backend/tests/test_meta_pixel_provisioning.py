"""Inert Web Pixel provisioning: fail closed and never send events."""
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from app.db import Base
from app.models import CommerceConnection, MetaPixelConfiguration, Organization, Store
from app.services.meta_pixel_provisioning import (
    PixelProvisioningError, provision, readiness, remove_remote, verify_remote
)


@pytest.fixture
def store_setup(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED", "true")
    monkeypatch.setenv("META_WEB_PIXEL_EXTENSION_DEPLOYED", "true")
    monkeypatch.setenv("META_WEB_PIXEL_SHOP_ALLOWLIST", "diaglob-poc.myshopify.com")
    with Session(engine) as db:
        org = Organization(id=801, name="Pixel tester", slug="pixel-tester")
        store = Store(
            id=802, organization_id=801, name="Diaglob test", slug="diaglob-test",
            country_code="CO", currency="COP", timezone="America/Bogota",
            active=True, deleted=False,
        )
        row = MetaPixelConfiguration(
            organization_id=801, store_id=802, pixel_id="12345678901234",
            existing_tracking="none", enabled=False, status="awaiting_extension",
        )
        conn = CommerceConnection(
            organization_id=801, store_id=802, provider="shopify",
            external_store_url="diaglob-poc.myshopify.com",
            access_token_encrypted="synthetic_ciphertext",
            scopes="read_products,write_pixels,read_customer_events,read_pixels",
            status="connected",
        )
        db.add_all([org, store, row, conn])
        db.commit()
        yield db, store, row, conn
    engine.dispose()


def test_default_closed_even_if_store_and_pixel_exist(store_setup, monkeypatch):
    db, store, row, connection = store_setup
    monkeypatch.delenv("META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED")
    result = readiness(db, store)
    assert not result["can_provision"]
    assert "FEATURE_DISABLED" in result["blockers"]
    with patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        with pytest.raises(PixelProvisioningError, match="FEATURE_DISABLED"):
            provision(db, store)
        client.assert_not_called()


@pytest.mark.parametrize("attr,value,reason", [
    ("existing_tracking", "shopify_meta", "DUPLICATE_TRACKING_NOT_CLEARED"),
    ("existing_tracking", "unknown", "DUPLICATE_TRACKING_NOT_CLEARED"),
])
def test_duplicate_risk_is_blocked(store_setup, attr, value, reason):
    db, store, row, conn = store_setup
    setattr(row, attr, value)
    db.commit()
    assert reason in readiness(db, store)["blockers"]


def test_shop_allowlist_and_granted_scopes_gate(store_setup, monkeypatch):
    db, store, row, conn = store_setup
    monkeypatch.setenv("META_WEB_PIXEL_SHOP_ALLOWLIST", "another.myshopify.com")
    assert "SHOP_NOT_ALLOWLISTED" in readiness(db, store)["blockers"]
    monkeypatch.setenv("META_WEB_PIXEL_SHOP_ALLOWLIST", "diaglob-poc.myshopify.com")
    conn.scopes = "read_products,write_pixels"
    db.commit()
    assert "SHOPIFY_PIXEL_SCOPES_MISSING" in readiness(db, store)["blockers"]


def test_provision_creates_only_inert_pixel_settings(store_setup):
    db, store, row, conn = store_setup
    with patch(
        "app.services.meta_pixel_provisioning.decrypt_shopify_secret",
        return_value="only_mock_token"
    ), patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        client.return_value.query.return_value = {
            "webPixelCreate": {"webPixel": {"id": "gid://shopify/WebPixel/17"}, "userErrors": []}
        }
        result = provision(db, store)
        client.assert_called_once()
        args, kwargs = client.return_value.query.call_args
        payload = args[1]["webPixel"]["settings"]
    assert result["provisioned"] is True
    assert result["events_active"] is False
    assert payload["trackingEnabled"] == "false"
    assert payload["pixelId"] == row.pixel_id
    assert payload["collectorUrl"] == "https://api.diaglob.tech/api/web-pixels/collect"
    assert row.web_pixel_gid == "gid://shopify/WebPixel/17"
    assert row.source_id and len(row.source_id) == 36
    assert row.enabled is False
    assert not readiness(db, store)["can_provision"]
    with pytest.raises(PixelProvisioningError, match="PIXEL_ALREADY_PROVISIONED"):
        provision(db, store)


def test_upstream_user_errors_do_not_mark_pixel_installed(store_setup):
    db, store, row, conn = store_setup
    with patch(
        "app.services.meta_pixel_provisioning.decrypt_shopify_secret",
        return_value="synthetic"
    ), patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        client.return_value.query.return_value = {
            "webPixelCreate": {"webPixel": None, "userErrors": [{"message": "not approved"}]}
        }
        with pytest.raises(PixelProvisioningError, match="SHOPIFY_WEB_PIXEL_REJECTED"):
            provision(db, store)
    db.rollback()
    assert row.web_pixel_gid is None
    assert row.enabled is False


def test_remote_unprovision_requires_verified_shop_and_response(store_setup):
    db, store, row, conn = store_setup
    row.web_pixel_gid = "gid://shopify/WebPixel/8"
    row.source_id = "00000000-0000-4000-8000-000000000008"
    row.status = "provisioned"
    db.commit()
    with patch(
        "app.services.meta_pixel_provisioning.decrypt_shopify_secret",
        return_value="synthetic"
    ), patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        client.return_value.query.return_value = {
            "webPixelDelete": {"deletedWebPixelId": row.web_pixel_gid, "userErrors": []}
        }
        result = remove_remote(db, store)
        client.return_value.query.assert_called_once()
    assert result["provisioned"] is False
    assert row.web_pixel_gid is None
    assert row.source_id is None
    assert row.enabled is False


def test_production_merchant_not_mutated(store_setup, monkeypatch):
    db, store, row, conn = store_setup
    conn.external_store_url = "bakata.myshopify.com"
    db.commit()
    with patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        with pytest.raises(PixelProvisioningError, match="SHOP_NOT_ALLOWLISTED"):
            provision(db, store)
        client.assert_not_called()



def test_read_only_remote_verify_detects_exact_inactive_shopify_record(store_setup):
    db, store, row, conn = store_setup
    row.web_pixel_gid = "gid://shopify/WebPixel/123"
    row.source_id = "7bcdefab-0000-4000-8000-000000000001"
    db.commit()
    with patch("app.services.meta_pixel_provisioning.decrypt_shopify_secret",
               return_value="only_fake"), patch(
        "app.services.meta_pixel_provisioning.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {
            "webPixel": {"id": row.web_pixel_gid, "settings": {
                "pixelId": row.pixel_id, "sourceId": row.source_id,
                "trackingEnabled": "false",
                "collectorUrl": "https://api.diaglob.tech/api/web-pixels/collect",
            }}
        }
        result = verify_remote(db, store)
        assert client.return_value.query.call_count == 1
    assert result == {
        "verified": True, "reason": "VERIFIED_INERT", "events_active": False
    }


def test_verify_remote_requires_read_pixels(store_setup):
    db, store, row, conn = store_setup
    row.web_pixel_gid = "gid://shopify/WebPixel/123"
    conn.scopes = "read_products,write_pixels,read_customer_events"
    db.commit()
    with patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        result = verify_remote(db, store)
        client.assert_not_called()
    assert result["verified"] is False
    assert result["reason"] == "SHOPIFY_PIXEL_READ_SCOPE_MISSING"


def test_remote_pixel_drift_does_not_claim_live_tracking(store_setup):
    db, store, row, conn = store_setup
    row.web_pixel_gid = "gid://shopify/WebPixel/123"
    row.source_id = "7bcdefab-0000-4000-8000-000000000001"
    db.commit()
    with patch("app.services.meta_pixel_provisioning.decrypt_shopify_secret",
               return_value="only_fake"), patch(
        "app.services.meta_pixel_provisioning.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {
            "webPixel": {"id": row.web_pixel_gid, "settings": {
                "pixelId": "999999999999", "sourceId": row.source_id,
                "trackingEnabled": "true",
                "collectorUrl": "https://api.diaglob.tech/api/web-pixels/collect",
            }}
        }
        result = verify_remote(db, store)
    assert result["verified"] is False
    assert result["reason"] == "REMOTE_SETTINGS_MISMATCH"
    assert result["events_active"] is False


def test_remote_query_refused_for_other_merchant(store_setup, monkeypatch):
    db, store, row, conn = store_setup
    row.web_pixel_gid = "gid://shopify/WebPixel/123"
    conn.external_store_url = "not-authorized.myshopify.com"
    db.commit()
    with patch("app.services.meta_pixel_provisioning.ShopifyGraphQLClient") as client:
        assert verify_remote(db, store)["reason"] == "SHOP_NOT_ALLOWLISTED"
        client.assert_not_called()
