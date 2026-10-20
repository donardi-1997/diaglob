"""Read-only development-store verification of actual Shopify access scopes.

Run as:
    SHOPIFY_AUDIT_SHOP=example.myshopify.com \
    SHOPIFY_AUDIT_ACCESS_TOKEN=<provided-in-secret-env> \
    python -m tools.shopify_scope_grant_probe

Never place credentials in command-line flags, git, logs or CI artifacts.
The result does NOT verify protected customer data field approvals.
"""
from __future__ import annotations

import json
import os

from app.shopify_client import ShopifyGraphQLClient
from app.shopify_oauth import SHOPIFY_SCOPES, normalize_shop_domain


SCOPE_QUERY = """
query DiaglobCurrentAppInstallationScopes {
  currentAppInstallation {
    accessScopes {
      handle
    }
  }
}
"""


def inspect_granted_scopes(payload: dict, *, required: str = SHOPIFY_SCOPES) -> dict:
    """Compare installed grants to the source's required set without tokens."""
    if not isinstance(payload, dict):
        raise ValueError("SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE")
    installation = payload.get("currentAppInstallation")
    if not isinstance(installation, dict):
        raise ValueError("SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE")
    scopes = installation.get("accessScopes")
    if not isinstance(scopes, list):
        raise ValueError("SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE")
    granted: set[str] = set()
    for item in scopes:
        if not isinstance(item, dict) or not isinstance(item.get("handle"), str):
            raise ValueError("SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE")
        handle = item["handle"].strip()
        if not handle:
            raise ValueError("SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE")
        granted.add(handle)
    expected = {s.strip() for s in required.split(",") if s.strip()}
    return {
        "source_required_scopes": sorted(expected),
        "currently_granted_scopes": sorted(granted),
        "missing_from_current_grant": sorted(expected - granted),
        "additional_existing_grants": sorted(granted - expected),
        "grant_parity": expected.issubset(granted),
        "protected_customer_data_approval_verified": False,
    }


def main() -> int:
    shop = (os.environ.get("SHOPIFY_AUDIT_SHOP") or "").strip()
    token = (os.environ.get("SHOPIFY_AUDIT_ACCESS_TOKEN") or "").strip()
    if not token or not shop:
        raise SystemExit("Set SHOPIFY_AUDIT_SHOP and SHOPIFY_AUDIT_ACCESS_TOKEN securely")
    try:
        normalized = normalize_shop_domain(shop)
        response = ShopifyGraphQLClient(normalized, token).query(SCOPE_QUERY)
        report = inspect_granted_scopes(response)
    except Exception as exc:
        # Provider exceptions may contain request details: only emit a code.
        raise SystemExit("SHOPIFY_SCOPE_AUDIT_FAILED") from None
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["grant_parity"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
