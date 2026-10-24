import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx


SHOPIFY_SCOPES = (
    "read_products,"
    "read_inventory,"
    ""
    "read_orders,"
    "write_orders,"
    "write_draft_orders,"
    "read_merchant_managed_fulfillment_orders,"
    "write_merchant_managed_fulfillment_orders"
)


SHOP_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$"
)


def get_shopify_client_id() -> str:
    value = os.getenv(
        "SHOPIFY_CLIENT_ID",
        "",
    ).strip()

    if not value:
        raise RuntimeError(
            "SHOPIFY_CLIENT_ID is not configured"
        )

    return value


def get_shopify_client_secret() -> str:
    value = os.getenv(
        "SHOPIFY_CLIENT_SECRET",
        "",
    ).strip()

    if not value:
        raise RuntimeError(
            "SHOPIFY_CLIENT_SECRET is not configured"
        )

    return value


def get_shopify_redirect_uri() -> str:
    value = os.getenv(
        "SHOPIFY_REDIRECT_URI",
        "",
    ).strip()

    if not value:
        raise RuntimeError(
            "SHOPIFY_REDIRECT_URI is not configured"
        )

    return value


def normalize_shop_domain(
    shop: str,
) -> str:
    value = (
        shop.strip()
        .lower()
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
    )

    if not SHOP_DOMAIN_RE.fullmatch(
        value
    ):
        raise ValueError(
            "Invalid Shopify shop domain"
        )

    return value


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorization_url(
    shop: str,
    state: str,
) -> str:
    shop = normalize_shop_domain(
        shop
    )

    params = {
        "client_id":
            get_shopify_client_id(),

        "scope":
            SHOPIFY_SCOPES,

        "redirect_uri":
            get_shopify_redirect_uri(),

        "state":
            state,
    }

    return (
        f"https://{shop}"
        f"/admin/oauth/authorize?"
        f"{urlencode(params)}"
    )


def verify_shopify_hmac(
    query_params: dict[str, str],
) -> bool:
    received_hmac = (
        query_params.get("hmac")
        or ""
    )

    if not received_hmac:
        return False

    pairs = []

    for key in sorted(query_params):
        if key in {
            "hmac",
            "signature",
        }:
            continue

        value = query_params[key]

        pairs.append(
            f"{key}={value}"
        )

    message = "&".join(
        pairs
    )

    digest = hmac.new(
        get_shopify_client_secret()
        .encode("utf-8"),

        message.encode("utf-8"),

        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        digest,
        received_hmac,
    )


@dataclass(frozen=True)
class ShopifyExpiringOfflineGrant:
    """Fresh Shopify code-grant credentials. Never serialize to HTTP clients."""
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


# Shopify grants corresponding read scopes implicitly when the related write
# scope is present. Derive effective scopes only from Shopify's token response.
_IMPLIED_READ_SCOPES = {
    "write_orders": "read_orders",
    "write_draft_orders": "read_draft_orders",
    "write_merchant_managed_fulfillment_orders": "read_merchant_managed_fulfillment_orders",
}


def effective_shopify_scopes(scope_list: str) -> set[str]:
    """Compute effective API rights from the actual token's Shopify scopes.

    Shopify omits some implicit read handles when granting write scopes.
    Never infer access beyond these explicit write->read pairs.
    """
    granted = {part.strip() for part in scope_list.split(",") if part.strip()}
    return granted | {
        read for write, read in _IMPLIED_READ_SCOPES.items()
        if write in granted
    }


def exchange_access_token(shop: str, code: str) -> ShopifyExpiringOfflineGrant:
    """Exchange a signed OAuth code for an expiring, refreshable offline pair.

    Fail closed if Shopify omits refresh metadata or required API scopes:
    persisting an access-only result would silently create another obsolete
    installation. Never include provider response bodies in exceptions.
    """
    shop = normalize_shop_domain(shop)
    payload = {
        "client_id": get_shopify_client_id(),
        "client_secret": get_shopify_client_secret(),
        "code": code,
        "expiring": "1",
    }
    try:
        response = httpx.post(
            f"https://{shop}/admin/oauth/access_token",
            data=payload,
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("SHOPIFY_OAUTH_CODE_EXCHANGE_FAILED") from exc

    if not isinstance(data, dict):
        raise RuntimeError("SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED")
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires = data.get("expires_in")
    refresh_expires = data.get("refresh_token_expires_in")
    if (
        not isinstance(access, str) or not access or len(access) > 8192
        or not isinstance(refresh, str) or not refresh or len(refresh) > 8192
        or type(expires) is not int or expires < 300
        or type(refresh_expires) is not int or refresh_expires < 900
    ):
        raise RuntimeError("SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED")

    raw_scopes = data.get("scope")
    if not isinstance(raw_scopes, str):
        raise RuntimeError("SHOPIFY_OAUTH_REQUIRED_SCOPES_MISSING")
    effective_scopes = effective_shopify_scopes(raw_scopes)
    if not set(SHOPIFY_SCOPES.split(",")).issubset(effective_scopes):
        raise RuntimeError("SHOPIFY_OAUTH_REQUIRED_SCOPES_MISSING")

    received_at = datetime.utcnow()
    return ShopifyExpiringOfflineGrant(
        access_token=access,
        refresh_token=refresh,
        access_token_expires_at=received_at + timedelta(seconds=expires),
        refresh_token_expires_at=received_at + timedelta(seconds=refresh_expires),
    )
