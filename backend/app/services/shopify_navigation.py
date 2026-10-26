"""Navigation back to this app in Shopify Admin, never a tenant grant."""
from __future__ import annotations

from ..shopify_app_config_audit import DIAGLOB_SHOPIFY_CLIENT_ID
from ..shopify_oauth import normalize_shop_domain


def shopify_app_home_url(verified_shop: str) -> str:
    """Only callers holding a verified installation may expose this URL."""
    if not isinstance(verified_shop, str) or len(verified_shop) > 255:
        raise ValueError("INVALID_SHOPIFY_RETURN_SHOP")
    canonical = normalize_shop_domain(verified_shop)
    if canonical != verified_shop:
        raise ValueError("INVALID_SHOPIFY_RETURN_SHOP")
    return f"https://{canonical}/admin/apps/{DIAGLOB_SHOPIFY_CLIENT_ID}"
