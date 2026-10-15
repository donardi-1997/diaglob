"""Read-only proof of Shopify-managed embedded installation.

A verified App Bridge ID token may be exchanged for an online access token.
This service never stores or returns either token and never grants a DIAGLOB
membership. Tenant onboarding and billing remain independent blocked gates.

Shopify: https://shopify.dev/docs/apps/build/authentication-authorization/implement-token-exchange
"""
from __future__ import annotations

import os

import httpx

from ..shopify_client import ShopifyAPIError, ShopifyGraphQLClient
from ..shopify_oauth import normalize_shop_domain


class ManagedShopifyInstallationError(RuntimeError):
    """Managed installation couldn't be independently verified."""


_TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
_SUBJECT_TYPE = "urn:ietf:params:oauth:token-type:id_token"
_ONLINE_TYPE = "urn:shopify:params:oauth:token-type:online-access-token"
_SHOP_QUERY = "query ManagedInstallationShop { shop { myshopifyDomain } }"


def verify_managed_installation(*, identity: dict[str, str], id_token: str) -> dict:
    """Verify remote Shopify install without linking accounts or persisting a token.

    The caller MUST validate the JWT signature, expiry, issuer, audience and
    destination using verify_shopify_id_token before calling this function.
    The remote response is not treated as a DIAGLOB tenant authorization.
    """
    shop = identity.get("shop")
    try:
        if not isinstance(shop, str) or shop != normalize_shop_domain(shop):
            raise ManagedShopifyInstallationError("INVALID_SHOPIFY_SHOP")
    except (TypeError, ValueError) as exc:
        raise ManagedShopifyInstallationError("INVALID_SHOPIFY_SHOP") from exc
    if not isinstance(id_token, str) or not id_token or len(id_token) > 8192:
        raise ManagedShopifyInstallationError("INVALID_SHOPIFY_SESSION")
    client_id = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ManagedShopifyInstallationError("SHOPIFY_MANAGED_INSTALL_NOT_CONFIGURED")

    # Do not log tokens, provider responses or user data.
    try:
        with httpx.Client(timeout=8.0, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                f"https://{shop}/admin/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": _TOKEN_EXCHANGE_GRANT,
                    "subject_token": id_token,
                    "subject_token_type": _SUBJECT_TYPE,
                    "requested_token_type": _ONLINE_TYPE,
                },
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise ManagedShopifyInstallationError("SHOPIFY_TOKEN_EXCHANGE_FAILED")
        token = result.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise ManagedShopifyInstallationError("SHOPIFY_TOKEN_EXCHANGE_FAILED")
        details = ShopifyGraphQLClient(shop_domain=shop, access_token=token).query(_SHOP_QUERY)
        provider_shop = details.get("shop") if isinstance(details, dict) else None
        raw_domain = provider_shop.get("myshopifyDomain") if isinstance(provider_shop, dict) else None
        if not isinstance(raw_domain, str) or normalize_shop_domain(raw_domain) != shop:
            raise ManagedShopifyInstallationError("SHOPIFY_MANAGED_INSTALL_IDENTITY_MISMATCH")
    except ManagedShopifyInstallationError:
        raise
    except (ShopifyAPIError, httpx.HTTPError, ValueError, TypeError, RuntimeError) as exc:
        raise ManagedShopifyInstallationError("SHOPIFY_MANAGED_INSTALL_VERIFICATION_FAILED") from exc

    return {
        "shopify_installation_verified": True,
        "diaglob_link_required": True,
        # Nothing about tenants, members, Shopify subjects, or tokens.
        "shop": shop,
    }
