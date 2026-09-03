import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlencode

import httpx


SHOPIFY_SCOPES = (
    "read_products,"
    "read_inventory,"
    "read_customers,"
    "read_orders,"
    "write_orders,"
    "write_draft_orders"
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


def exchange_access_token(
    shop: str,
    code: str,
) -> str:
    shop = normalize_shop_domain(
        shop
    )

    payload = {
        "client_id":
            get_shopify_client_id(),

        "client_secret":
            get_shopify_client_secret(),

        "code":
            code,
    }

    try:
        response = httpx.post(
            (
                f"https://{shop}"
                f"/admin/oauth/access_token"
            ),
            json=payload,
            timeout=20,
        )

    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Unable to reach Shopify to "
            "exchange the OAuth code"
        ) from exc

    if (
        response.status_code
        not in {200, 201}
    ):
        raise RuntimeError(
            (
                "Shopify rejected the OAuth "
                "code exchange (HTTP "
                f"{response.status_code})."
            )
        )

    data = response.json()

    access_token = (
        data.get("access_token")
        or ""
    )

    if not access_token:
        raise RuntimeError(
            "Shopify did not return an "
            "access token"
        )

    return access_token
