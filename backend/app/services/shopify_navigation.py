"""Navigation back to this app in Shopify Admin, never a tenant grant."""
from __future__ import annotations

import os
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from ..shopify_app_config_audit import DIAGLOB_SHOPIFY_CLIENT_ID
from ..shopify_oauth import normalize_shop_domain


def shopify_app_pricing_welcome_url(query_string: str) -> str:
    """Route Shopify plan returns to the frontend billing workspace safely."""
    if not isinstance(query_string, str) or len(query_string) > 16_384:
        raise ValueError("INVALID_SHOPIFY_PRICING_RETURN")

    base = os.getenv("FRONTEND_URL", "https://diaglob.tech").strip()
    try:
        parsed = urlsplit(base)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("FRONTEND_URL_NOT_SAFE") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.hostname is None
        or (port is not None and port != 443)
    ):
        raise ValueError("FRONTEND_URL_NOT_SAFE")

    # The handle is only a signal for a fresh Partner API check. Never forward
    # the untrusted value, shop hint, charge id, or arbitrary return parameters.
    has_plan_handle = bool(parse_qs(query_string, keep_blank_values=True).get("plan_handle"))
    query = urlencode({"plan_handle": "shopify-hosted-return"}) if has_plan_handle else ""
    return urlunsplit(("https", parsed.netloc, "/app/plans", query, ""))


def shopify_app_home_url(verified_shop: str) -> str:
    """Only callers holding a verified installation may expose this URL."""
    if not isinstance(verified_shop, str) or len(verified_shop) > 255:
        raise ValueError("INVALID_SHOPIFY_RETURN_SHOP")
    canonical = normalize_shop_domain(verified_shop)
    if canonical != verified_shop:
        raise ValueError("INVALID_SHOPIFY_RETURN_SHOP")
    return f"https://{canonical}/admin/apps/{DIAGLOB_SHOPIFY_CLIENT_ID}"
