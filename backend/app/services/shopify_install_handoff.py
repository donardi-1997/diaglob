"""Unauthenticated Shopify install handoff — no tenant binding or OAuth grant.

The incoming shop name is UNTRUSTED until an authenticated DIAGLOB user
explicitly chooses an authorized store and the signed OAuth callback succeeds.
"""
from __future__ import annotations

import os
from urllib.parse import urlencode, urlsplit, urlunsplit

from ..shopify_oauth import normalize_shop_domain


class ShopifyInstallHandoffError(ValueError):
    """Invalid public shop hint or unsafe frontend configuration."""


def build_shopify_install_handoff(shop: str) -> str:
    if not isinstance(shop, str) or len(shop) > 255:
        raise ShopifyInstallHandoffError("INVALID_SHOP_DOMAIN")
    try:
        normalized_shop = normalize_shop_domain(shop)
    except (ValueError, AttributeError) as exc:
        raise ShopifyInstallHandoffError("INVALID_SHOP_DOMAIN") from exc

    # Shopify sends a domain name, not a URL; don't normalize malformed input
    # into an apparently trusted installation identity.
    if normalized_shop != shop.strip().lower():
        raise ShopifyInstallHandoffError("INVALID_SHOP_DOMAIN")

    base = os.getenv("FRONTEND_URL", "https://diaglob.tech").strip()
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment
        or parsed.hostname is None
        or (parsed.port is not None and parsed.port != 443)
    ):
        raise ShopifyInstallHandoffError("FRONTEND_URL_NOT_SAFE")

    # Do not inherit request.host, forwarded headers, arbitrary return_to,
    # Shopify host values or user-supplied redirect_uri.
    return urlunsplit((
        "https", parsed.netloc, "/shopify/install",
        urlencode({"shop": normalized_shop}), "",
    ))
