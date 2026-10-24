"""Synthetic tests for the authorized, one-store token migration script."""
from datetime import datetime
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CommerceConnection, Organization, Store
from app.shopify_oauth import SHOPIFY_SCOPES
from scripts import migrate_shopify_legacy_offline_token as migration


@pytest.fixture
def legacy(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "client-identifier")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "test-only-secret")
    with Session(engine) as db:
        db.add_all([
            Organization(id=501, name="Migration org", slug="migration-org"),
            Store(
                id=502, organization_id=501, name="Migration store",
                slug="migration-store", country_code="CO", currency="COP",
                timezone="America/Bogota", active=True, deleted=False,
            ),
            CommerceConnection(
                id=503, store_id=502, organization_id=501, provider="shopify",
                external_store_url="diaglob-poc.myshopify.com",
                access_token_encrypted="encrypted-legacy", status="connected",
                scopes=SHOPIFY_SCOPES,
            ),
        ])
        db.commit()
        yield db, db.query(CommerceConnection).one()
    engine.dispose()


@pytest.fixture
def crypto(monkeypatch):
    monkeypatch.setattr(
        migration, "decrypt_shopify_secret",
        lambda value: {"encrypted-legacy": "legacy-secret"}.get(
            value, value.removeprefix("enc:")
        ),
    )
    monkeypatch.setattr(migration, "encrypt_shopify_secret", lambda value: "enc:" + value)


def _response_data():
    return {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
        "refresh_token_expires_in": 7776000,
        "scope": SHOPIFY_SCOPES,
    }


def _apply(db):
    return migration.migrate_legacy_offline_token(
        db, shop="diaglob-poc.myshopify.com",
        expected_connection_id=503, expected_organization_id=501,
        acknowledge_token_invalidation=True,
    )


def test_dry_run_reads_only_metadata_without_decrypting_or_network(legacy, monkeypatch):
    db, conn = legacy
    monkeypatch.setattr(
        migration, "decrypt_shopify_secret",
        lambda *_: pytest.fail("dry-run decrypted a secret"),
    )
    with patch.object(migration.httpx, "Client") as client:
        preview = migration.inspect_migration(db, "diaglob-poc.myshopify.com")
    assert preview == {
        "shop_domain": "diaglob-poc.myshopify.com",
        "connection_id": 503, "organization_id": 501, "store_id": 502,
        "credential_state": "READY_FOR_DIRECT_MIGRATION",
        "eligible": True, "executed": False,
    }
    assert conn.access_token_encrypted == "encrypted-legacy"
    client.assert_not_called()


def test_exchange_uses_legacy_token_and_saves_expiring_pair(
    legacy, crypto, monkeypatch,
):
    db, connection = legacy
    payload = _response_data()
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, *, data):
            calls.append((url, data))
            return httpx.Response(200, request=httpx.Request("POST", url), json=payload)

    monkeypatch.setattr(migration.httpx, "Client", FakeClient)
    result = _apply(db)
    assert result["credential_state"] == "MIGRATED"
    assert result["requires_scope_review"] is False
    assert len(calls) == 1
    url, data = calls[0]
    assert url == "https://diaglob-poc.myshopify.com/admin/oauth/access_token"
    assert data == {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": "client-identifier",
        "client_secret": "test-only-secret",
        "subject_token": "legacy-secret",
        "subject_token_type": "urn:shopify:params:oauth:token-type:offline-access-token",
        "requested_token_type": "urn:shopify:params:oauth:token-type:offline-access-token",
        "expiring": "1",
    }
    db.refresh(connection)
    assert connection.access_token_encrypted == "enc:new-access"
    assert connection.refresh_token_encrypted == "enc:new-refresh"
    assert connection.access_token_expires_at > datetime.utcnow()
    assert connection.refresh_token_expires_at > datetime.utcnow()
    assert "new-access" not in str(result)
    assert "legacy-secret" not in str(result)

    with pytest.raises(migration.ShopifyLegacyMigrationError, match="NOT_ELIGIBLE"):
        _apply(db)
    assert len(calls) == 1


@pytest.mark.parametrize("kwargs", [
    {"acknowledge_token_invalidation": False},
    {"expected_connection_id": 1},
    {"expected_organization_id": 222},
])
def test_explicit_authorization_required_before_network(legacy, crypto, kwargs):
    db, connection = legacy
    params = {
        "shop": "diaglob-poc.myshopify.com",
        "expected_connection_id": 503,
        "expected_organization_id": 501,
        "acknowledge_token_invalidation": True,
    }
    params.update(kwargs)
    with patch.object(migration.httpx, "Client") as client:
        with pytest.raises(migration.ShopifyLegacyMigrationError):
            migration.migrate_legacy_offline_token(db, **params)
    client.assert_not_called()
    assert connection.access_token_encrypted == "encrypted-legacy"


@pytest.mark.parametrize("mutation", [
    {"refresh_token": None},
    {"expires_in": None},
    {"refresh_token_expires_in": False},
])
def test_invalid_provider_response_preserves_legacy_record(
    legacy, crypto, monkeypatch, mutation,
):
    db, connection = legacy
    body = _response_data()
    body.update(mutation)

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, *, data):
            return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    monkeypatch.setattr(migration.httpx, "Client", FakeClient)
    with pytest.raises(
        migration.ShopifyLegacyMigrationError,
        match="MIGRATION_RESPONSE_INVALID_RECOVERY_REQUIRED",
    ):
        _apply(db)
    db.refresh(connection)
    assert connection.access_token_encrypted == "encrypted-legacy"
    assert connection.refresh_token_encrypted is None


def test_scope_gap_persists_new_pair_but_flags_connection_for_review(
    legacy, crypto, monkeypatch,
):
    db, connection = legacy
    body = _response_data()
    body["scope"] = "read_products"

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, *, data):
            return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    monkeypatch.setattr(migration.httpx, "Client", FakeClient)
    result = _apply(db)
    assert result["credential_state"] == "MIGRATED_SCOPES_REQUIRE_REVIEW"
    assert result["requires_scope_review"] is True
    db.refresh(connection)
    assert connection.status == "error"
    assert connection.last_error == "SHOPIFY_MIGRATION_REQUIRED_SCOPES_MISSING"
    assert connection.access_token_encrypted == "enc:new-access"
    assert connection.refresh_token_encrypted == "enc:new-refresh"
    assert connection.scopes == "read_products"


def test_partial_or_inactive_connection_never_migrates(legacy, crypto):
    db, connection = legacy
    connection.refresh_token_encrypted = "unmatched-refresh"
    db.commit()
    assert migration.inspect_migration(db, "diaglob-poc.myshopify.com")[
        "credential_state"
    ] == "INCONSISTENT_TOKEN_STATE"
    with patch.object(migration.httpx, "Client") as client:
        with pytest.raises(migration.ShopifyLegacyMigrationError, match="NOT_ELIGIBLE"):
            _apply(db)
    client.assert_not_called()
