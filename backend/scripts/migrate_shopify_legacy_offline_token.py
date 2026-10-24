"""Operator-gated, one-store migration of a legacy Shopify offline token.

Run from backend/, with existing production env securely loaded:

    python -m scripts.migrate_shopify_legacy_offline_token --shop example.myshopify.com

Only after reviewing the tenant-scoped dry-run:
    python -m scripts.migrate_shopify_legacy_offline_token \
        --shop example.myshopify.com --apply \
        --connection-id <ID_FROM_DRY_RUN> --organization-id <ORG_FROM_DRY_RUN> \
        --acknowledge-token-invalidation

NEVER provide tokens through CLI arguments, print them, or save provider JSON
to files. A successful Shopify exchange INVALIDATES the legacy access token.
If persistence fails after exchange, Shopify permits recovery by replaying the
original request with the original token within seven days (subject to limits).
This script must only be run by an authorized operator on the server.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CommerceConnection
from app.shopify_oauth import SHOPIFY_SCOPES, normalize_shop_domain
from app.shopify_security import decrypt_shopify_secret, encrypt_shopify_secret

_OFFLINE_TYPE = "urn:shopify:params:oauth:token-type:offline-access-token"
_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
_IMPLIED_READS = {
    "write_orders": "read_orders",
    "write_draft_orders": "read_draft_orders",
    "write_merchant_managed_fulfillment_orders": "read_merchant_managed_fulfillment_orders",
}


class ShopifyLegacyMigrationError(RuntimeError):
    """Only stable error codes, never provider payloads or secrets."""


def _get_connection(db: Session, shop: str, *, lock: bool = False) -> CommerceConnection:
    query = db.query(CommerceConnection).filter(
        CommerceConnection.provider == "shopify",
        CommerceConnection.external_store_url == shop,
    )
    if lock:
        query = query.with_for_update()
    connection = query.one_or_none()
    if connection is None:
        raise ShopifyLegacyMigrationError("SHOPIFY_CONNECTION_NOT_FOUND")
    return connection


def _eligibility(connection: CommerceConnection) -> str:
    if connection.status not in {"connected", "error"}:
        return "CONNECTION_NOT_ACTIVE"
    if not connection.access_token_encrypted:
        return "NO_STORED_ACCESS_TOKEN"
    if any((
        connection.refresh_token_encrypted,
        connection.access_token_expires_at,
        connection.refresh_token_expires_at,
    )):
        if all((
            connection.refresh_token_encrypted,
            connection.access_token_expires_at,
            connection.refresh_token_expires_at,
        )):
            return "ALREADY_EXPIRING"
        return "INCONSISTENT_TOKEN_STATE"
    return "READY_FOR_DIRECT_MIGRATION"


def inspect_migration(db: Session, shop: str) -> dict:
    """Metadata-only inspection: no decrypt, network request or DB mutation."""
    canonical = normalize_shop_domain(shop)
    connection = _get_connection(db, canonical)
    state = _eligibility(connection)
    return {
        "shop_domain": canonical,
        "connection_id": connection.id,
        "organization_id": connection.organization_id,
        "store_id": connection.store_id,
        "credential_state": state,
        "eligible": state == "READY_FOR_DIRECT_MIGRATION",
        "executed": False,
    }


def migrate_legacy_offline_token(
    db: Session, *,
    shop: str,
    expected_connection_id: int,
    expected_organization_id: int,
    acknowledge_token_invalidation: bool,
) -> dict:
    """Convert exactly one eligible existing Shopify connection.

    Holds the target row lock through the exchange and commit to prevent a
    concurrent DB-level token write. Do not run token refresh or reauthorize
    the same shop concurrently with this one-time migration.
    """
    canonical = normalize_shop_domain(shop)
    if (
        not acknowledge_token_invalidation
        or type(expected_connection_id) is not int or expected_connection_id <= 0
        or type(expected_organization_id) is not int or expected_organization_id <= 0
    ):
        raise ShopifyLegacyMigrationError("EXPLICIT_MIGRATION_CONFIRMATION_REQUIRED")

    connection = _get_connection(db, canonical, lock=True)
    if (
        connection.id != expected_connection_id
        or connection.organization_id != expected_organization_id
    ):
        raise ShopifyLegacyMigrationError("MIGRATION_TENANT_OR_CONNECTION_MISMATCH")
    if _eligibility(connection) != "READY_FOR_DIRECT_MIGRATION":
        raise ShopifyLegacyMigrationError("LEGACY_MIGRATION_NOT_ELIGIBLE")

    client_id = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ShopifyLegacyMigrationError("SHOPIFY_MIGRATION_NOT_CONFIGURED")

    # Preflight BOTH cipher operations before Shopify invalidates the old token.
    # The existing credential must be decryptable by this exact runtime key.
    try:
        old_token = decrypt_shopify_secret(connection.access_token_encrypted)
        probe = encrypt_shopify_secret("shopify-migration-preflight")
        if decrypt_shopify_secret(probe) != "shopify-migration-preflight":
            raise ValueError("preflight mismatch")
    except (RuntimeError, ValueError) as exc:
        raise ShopifyLegacyMigrationError("TOKEN_ENCRYPTION_PREFLIGHT_FAILED") from None
    if not old_token:
        raise ShopifyLegacyMigrationError("LEGACY_TOKEN_UNAVAILABLE")

    request_data = {
        "grant_type": _EXCHANGE_GRANT,
        "client_id": client_id,
        "client_secret": client_secret,
        "subject_token": old_token,
        "subject_token_type": _OFFLINE_TYPE,
        "requested_token_type": _OFFLINE_TYPE,
        "expiring": "1",
    }
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as http:
            response = http.post(
                f"https://{canonical}/admin/oauth/access_token",
                data=request_data,
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ShopifyLegacyMigrationError("SHOPIFY_DIRECT_MIGRATION_REQUEST_FAILED") from None

    # Once the exchange succeeds, the original token may be invalid. NEVER
    # return without attempting to store a valid new pair.
    if not isinstance(payload, dict):
        raise ShopifyLegacyMigrationError("MIGRATION_RESPONSE_INVALID_RECOVERY_REQUIRED")
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires = payload.get("expires_in")
    refresh_expires = payload.get("refresh_token_expires_in")
    if (
        not isinstance(access, str) or not access or len(access) > 8192
        or not isinstance(refresh, str) or not refresh or len(refresh) > 8192
        or type(expires) is not int or expires < 300
        or type(refresh_expires) is not int or refresh_expires < 900
    ):
        raise ShopifyLegacyMigrationError("MIGRATION_RESPONSE_INVALID_RECOVERY_REQUIRED")

    # A scope gap does not justify throwing away the recovered token pair.
    # Persist credentials and fail closed for Admin API operations instead.
    raw_scopes = payload.get("scope")
    received_scopes = (
        {scope.strip() for scope in raw_scopes.split(",") if scope.strip()}
        if isinstance(raw_scopes, str) else set()
    )
    effective_scopes = received_scopes | {
        read for write, read in _IMPLIED_READS.items()
        if write in received_scopes
    }
    missing_scopes = set(SHOPIFY_SCOPES.split(",")) - effective_scopes
    now = datetime.utcnow()
    try:
        connection.access_token_encrypted = encrypt_shopify_secret(access)
        connection.refresh_token_encrypted = encrypt_shopify_secret(refresh)
        connection.access_token_expires_at = now + timedelta(seconds=expires)
        connection.refresh_token_expires_at = now + timedelta(seconds=refresh_expires)
        connection.updated_at = now
        if missing_scopes:
            connection.status = "error"
            connection.last_error = "SHOPIFY_MIGRATION_REQUIRED_SCOPES_MISSING"
            connection.scopes = ",".join(sorted(received_scopes))
        else:
            connection.status = "connected"
            connection.last_error = None
            connection.scopes = SHOPIFY_SCOPES
        db.commit()
    except Exception:
        db.rollback()
        # Repeating the *same* migration exchange with the retained legacy
        # token may recover the pair for a limited window under Shopify rules.
        raise ShopifyLegacyMigrationError(
            "MIGRATION_PERSISTENCE_FAILED_RECOVERY_REQUIRED"
        ) from None

    return {
        "shop_domain": canonical,
        "connection_id": connection.id,
        "organization_id": connection.organization_id,
        "credential_state": (
            "MIGRATED_SCOPES_REQUIRE_REVIEW" if missing_scopes else "MIGRATED"
        ),
        "executed": True,
        "requires_scope_review": bool(missing_scopes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shop", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--connection-id", type=int)
    parser.add_argument("--organization-id", type=int)
    parser.add_argument("--acknowledge-token-invalidation", action="store_true")
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            if args.apply:
                result = migrate_legacy_offline_token(
                    db, shop=args.shop,
                    expected_connection_id=args.connection_id,
                    expected_organization_id=args.organization_id,
                    acknowledge_token_invalidation=args.acknowledge_token_invalidation,
                )
            else:
                result = inspect_migration(db, args.shop)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ShopifyLegacyMigrationError, ValueError) as exc:
        # All errors are stable codes, not token values or provider responses.
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
