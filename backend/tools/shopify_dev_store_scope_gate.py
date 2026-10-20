"""Read-only, three-way Shopify app scope audit for an authorized dev store.

Compares repository TOML + OAuth source to Shopify's declared scopes and the
scopes actually granted to the same app on the queried shop. The API token
may belong to an authorized Admin app that can query appByKey; unlike
currentAppInstallation, this query explicitly identifies DIAGLOB by API key.

Never queries customers, orders or raw personal data, writes to Shopify,
changes installations or asserts protected customer data approval.

Run from backend/ using a development-store token in a private environment:
  SHOPIFY_AUDIT_SHOP=example.myshopify.com \
  SHOPIFY_AUDIT_ACCESS_TOKEN=<secret-env> \
  python -m tools.shopify_dev_store_scope_gate
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tomli

from app.shopify_client import ShopifyGraphQLClient
from app.shopify_oauth import SHOPIFY_SCOPES, normalize_shop_domain


QUERY = """
query DiaglobReadOnlyScopeGate($apiKey: String!) {
  shop { myshopifyDomain }
  appByKey(apiKey: $apiKey) {
    apiKey
    requestedAccessScopes { handle }
    optionalAccessScopes { handle }
    installation { accessScopes { handle } }
  }
}
"""

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "shopify.app.toml"
_SCOPE = re.compile(r"^[a-z][a-z0-9_]*$")


def _scope_set(value: str) -> set[str]:
    if not isinstance(value, str) or not value:
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_SOURCE")
    handles = [part.strip() for part in value.split(",")]
    if any(not _SCOPE.fullmatch(handle) for handle in handles):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_SOURCE")
    if len(set(handles)) != len(handles):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_SOURCE")
    return set(handles)


def _handles(value: object) -> set[str]:
    if not isinstance(value, list):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
    names = []
    for item in value:
        handle = item.get("handle") if isinstance(item, dict) else None
        if not isinstance(handle, str) or not _SCOPE.fullmatch(handle):
            raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
        names.append(handle)
    if len(names) != len(set(names)):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
    return set(names)


def inspect_shopify_dev_store_scopes(
    payload: dict, *,
    expected_shop: str,
    app_key: str,
    source_scopes: str = SHOPIFY_SCOPES,
    toml_scopes: str,
) -> dict:
    """Fail closed on shop/app mismatch and distinguish requested from granted."""
    if not isinstance(payload, dict):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
    expected_domain = normalize_shop_domain(expected_shop)
    shop = payload.get("shop")
    domain = shop.get("myshopifyDomain") if isinstance(shop, dict) else None
    if not isinstance(domain, str):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
    try:
        actual_domain = normalize_shop_domain(domain)
    except ValueError:
        raise ValueError("SHOPIFY_SCOPE_GATE_WRONG_SHOP") from None
    if actual_domain != expected_domain:
        raise ValueError("SHOPIFY_SCOPE_GATE_WRONG_SHOP")
    if not isinstance(app_key, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", app_key):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_APP_KEY")

    required = _scope_set(source_scopes)
    declared = _scope_set(toml_scopes)

    app = payload.get("appByKey")
    if app is None:
        return {
            "shop": expected_domain,
            "app_found_by_key": False,
            "installed": False,
            "source_toml_parity": declared == required,
            "remote_requested_parity": False,
            "remote_granted_parity": False,
            "scope_gate_passed": False,
            "protected_customer_data_approval_verified": False,
        }
    if not isinstance(app, dict) or app.get("apiKey") != app_key:
        raise ValueError("SHOPIFY_SCOPE_GATE_WRONG_APP")

    requested = _handles(app.get("requestedAccessScopes"))
    optional = _handles(app.get("optionalAccessScopes"))
    installation = app.get("installation")
    if installation is not None and not isinstance(installation, dict):
        raise ValueError("SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE")
    granted = _handles(installation.get("accessScopes")) if installation else set()
    installed = installation is not None

    source_toml_parity = declared == required
    remote_requested_parity = requested == required
    remote_granted_parity = installed and granted == required
    # Extra optional permissions require explicit review, even if current
    # requested/granted lists appear to match the source.
    passed = (
        source_toml_parity
        and remote_requested_parity
        and remote_granted_parity
        and not optional
    )
    return {
        "shop": expected_domain,
        "app_found_by_key": True,
        "installed": installed,
        "source_required_scopes": sorted(required),
        "toml_declared_scopes": sorted(declared),
        "shopify_requested_scopes": sorted(requested),
        "shopify_optional_scopes": sorted(optional),
        "shopify_granted_scopes": sorted(granted),
        "source_toml_parity": source_toml_parity,
        "remote_requested_parity": remote_requested_parity,
        "remote_granted_parity": remote_granted_parity,
        "requested_missing": sorted(required - requested),
        "requested_extra": sorted(requested - required),
        "granted_missing": sorted(required - granted),
        "granted_extra": sorted(granted - required),
        "scope_gate_passed": passed,
        "protected_customer_data_approval_verified": False,
        "shopify_app_version_verified": False,
        "merchant_installation_e2e_verified": False,
    }


def read_source_config(path: Path = DEFAULT_CONFIG) -> tuple[str, str]:
    """Read only committed config and do not print arbitrary TOML contents."""
    if not path.is_file() or path.stat().st_size > 256 * 1024:
        raise ValueError("SHOPIFY_SCOPE_GATE_CONFIG_UNAVAILABLE")
    app = tomli.loads(path.read_text(encoding="utf-8"))
    if not isinstance(app, dict) or not isinstance(app.get("access_scopes"), dict):
        raise ValueError("SHOPIFY_SCOPE_GATE_CONFIG_UNAVAILABLE")
    return app.get("client_id"), app["access_scopes"].get("scopes")


def main() -> int:
    shop = (os.getenv("SHOPIFY_AUDIT_SHOP") or "").strip()
    token = (os.getenv("SHOPIFY_AUDIT_ACCESS_TOKEN") or "").strip()
    if not token or not shop:
        raise SystemExit(
            "Set SHOPIFY_AUDIT_SHOP and SHOPIFY_AUDIT_ACCESS_TOKEN privately"
        )
    try:
        domain = normalize_shop_domain(shop)
        app_key, declared = read_source_config()
        if not isinstance(app_key, str) or not isinstance(declared, str):
            raise ValueError("SHOPIFY_SCOPE_GATE_CONFIG_UNAVAILABLE")
        data = ShopifyGraphQLClient(domain, token).query(
            QUERY, {"apiKey": app_key}
        )
        result = inspect_shopify_dev_store_scopes(
            data, expected_shop=domain, app_key=app_key,
            source_scopes=SHOPIFY_SCOPES, toml_scopes=declared,
        )
    except Exception:
        # Never echo provider errors, secrets, shop PII, or partial payloads.
        raise SystemExit("SHOPIFY_DEV_STORE_SCOPE_GATE_FAILED") from None
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if result["scope_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
