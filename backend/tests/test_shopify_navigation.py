"""Shopify return navigation cannot select arbitrary hosts, apps or secrets."""
import pytest

from app.services.shopify_navigation import shopify_app_home_url
from app.shopify_app_config_audit import DIAGLOB_SHOPIFY_CLIENT_ID


def test_return_to_the_verified_shop_and_linked_app_only():
    assert shopify_app_home_url("synthetic.myshopify.com") == (
        f"https://synthetic.myshopify.com/admin/apps/{DIAGLOB_SHOPIFY_CLIENT_ID}"
    )


@pytest.mark.parametrize("shop", [
    None, "", "https://synthetic.myshopify.com", "evil.example", "A.myshopify.com",
    "a.myshopify.com/evil", "a.myshopify.com?token=secret", "a.myshopify.com:443",
    "a.myshopify.com@evil.example", "a.myshopify.com\r\nevil", "a" * 256,
])
def test_noncanonical_shop_cannot_be_used_for_return_navigation(shop):
    with pytest.raises(ValueError):
        shopify_app_home_url(shop)
