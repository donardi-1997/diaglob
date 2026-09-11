"""Shopify business orchestration service.

Handles OAuth connection lifecycle, product sync, and order creation.
Does NOT import FastAPI.
"""
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    OrganizationMembership,
    ShopifyOAuthState,
    Store,
)
from ..shopify_oauth import (
    SHOPIFY_SCOPES,
    build_authorization_url,
    exchange_access_token,
    generate_oauth_state,
    normalize_shop_domain,
    verify_shopify_hmac,
)
from ..shopify_security import encrypt_shopify_secret
from .trial_service import (
    TrialIdentityAlreadyUsed,
    activate_trial_for_verified_store,
)
from ..shopify_sync import (
    sync_shopify_products,
    test_shopify_connection,
)
from ..shopify_orders import (
    create_shopify_draft_order,
    get_shopify_order,
    list_shopify_orders,
)
from ..shopify_poc import create_poc_order
from ..shopify_client import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyGraphQLError,
    ShopifyTimeoutError,
    ShopifyUserError,
)

logger = logging.getLogger(__name__)


class ShopifyNotFoundError(Exception):
    pass


class ShopifyConnectionError(Exception):
    pass


class ShopifyOAuthError(Exception):
    pass


class ShopifyProviderError(Exception):
    pass


def _shopify_connect_frontend_url(connected: bool) -> str:
    base_url = os.getenv("FRONTEND_URL", "https://diaglob.tech").strip().rstrip("/")
    status = "connected" if connected else "already-connected"
    return f"{base_url}?shopify={status}"


def _require_store(db: Session, organization_id: int, store_id: int) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise ShopifyNotFoundError("Store not found")
    return store


def _require_connection(db: Session, organization_id: int, store_id: int) -> CommerceConnection:
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise ShopifyNotFoundError("SHOPIFY_NOT_CONNECTED")
    return connection


def start_oauth(
    db: Session,
    organization_id: int,
    store_id: int,
    user_id: int,
    shop_domain: str,
) -> dict:
    store = _require_store(db, organization_id, store_id)

    if not store.active:
        raise ShopifyConnectionError("La tienda debe estar activa para conectar Shopify.")

    existing_connection = (
        db.query(CommerceConnection)
        .filter(CommerceConnection.store_id == store.id)
        .first()
    )
    if existing_connection:
        raise ShopifyConnectionError("COMMERCE_ALREADY_CONNECTED")

    try:
        normalized_shop = normalize_shop_domain(shop_domain)
    except ValueError as exc:
        raise ShopifyOAuthError("INVALID_SHOPIFY_DOMAIN") from exc

    conflicting = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == normalized_shop,
        )
        .first()
    )
    if conflicting:
        raise ShopifyConnectionError("SHOPIFY_STORE_ALREADY_CONNECTED")

    state = generate_oauth_state()
    now = datetime.utcnow()

    oauth_state = ShopifyOAuthState(
        state=state,
        organization_id=organization_id,
        store_id=store.id,
        user_id=user_id,
        shop_domain=normalized_shop,
        expires_at=now + timedelta(minutes=10),
        used=False,
        created_at=now,
    )
    db.add(oauth_state)

    # Clean old unused states for same store/user
    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.store_id == store.id,
            ShopifyOAuthState.user_id == user_id,
            ShopifyOAuthState.state != state,
            ShopifyOAuthState.used.is_(False),
        )
        .update({ShopifyOAuthState.used: True}, synchronize_session=False)
    )

    try:
        authorization_url = build_authorization_url(normalized_shop, state)
    except RuntimeError as exc:
        db.rollback()
        raise ShopifyConnectionError("SHOPIFY_NOT_CONFIGURED") from exc

    db.commit()

    return {
        "ok": True,
        "provider": "shopify",
        "store_id": store.id,
        "shop_domain": normalized_shop,
        "expires_in_seconds": 600,
        "authorization_url": authorization_url,
    }


def process_oauth_callback(db: Session, query_params: dict) -> str:
    """Process OAuth callback. Returns frontend redirect URL."""
    if not verify_shopify_hmac(query_params):
        raise ShopifyOAuthError("Invalid Shopify HMAC")

    code = query_params.get("code", "")
    state = query_params.get("state", "")
    shop = query_params.get("shop", "")

    if not (code and state and shop):
        raise ShopifyOAuthError("Missing required Shopify OAuth parameters")

    oauth_state = (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.state == state,
            ShopifyOAuthState.used.is_(False),
        )
        .first()
    )
    if not oauth_state:
        raise ShopifyOAuthError("Invalid or already used OAuth state")

    if oauth_state.expires_at < datetime.utcnow():
        raise ShopifyOAuthError("OAuth state expired")

    try:
        normalized_shop = normalize_shop_domain(shop)
    except ValueError as exc:
        raise ShopifyOAuthError("Invalid shop domain") from exc

    if oauth_state.shop_domain != normalized_shop:
        raise ShopifyOAuthError("OAuth state does not match the shop domain")

    try:
        access_token = exchange_access_token(normalized_shop, code)
    except RuntimeError as exc:
        raise ShopifyProviderError(str(exc)) from exc

    encrypted_token = encrypt_shopify_secret(access_token)

    existing_connection = (
        db.query(CommerceConnection)
        .filter(CommerceConnection.store_id == oauth_state.store_id)
        .first()
    )

    if existing_connection:
        (
            db.query(ShopifyOAuthState)
            .filter(ShopifyOAuthState.id == oauth_state.id)
            .update({ShopifyOAuthState.used: True}, synchronize_session=False)
        )
        db.commit()
        return _shopify_connect_frontend_url(connected=False)

    try:
        activate_trial_for_verified_store(
            db,
            organization_id=oauth_state.organization_id,
            store_id=oauth_state.store_id,
            provider="shopify",
            external_identity=normalized_shop,
        )
    except TrialIdentityAlreadyUsed as exc:
        db.commit()
        raise ShopifyConnectionError(str(exc)) from exc

    now = datetime.utcnow()
    connection = CommerceConnection(
        organization_id=oauth_state.organization_id,
        store_id=oauth_state.store_id,
        provider="shopify",
        external_store_url=normalized_shop,
        access_token_encrypted=encrypted_token,
        scopes=SHOPIFY_SCOPES,
        status="connected",
        connected_at=now,
    )
    db.add(connection)

    (
        db.query(ShopifyOAuthState)
        .filter(ShopifyOAuthState.id == oauth_state.id)
        .update({ShopifyOAuthState.used: True}, synchronize_session=False)
    )

    db.commit()

    # Analytics: Shopify connected
    from .product_analytics import track_shopify_connected
    track_shopify_connected(
        user_id=oauth_state.user_id,
        organization_id=oauth_state.organization_id,
        store_id=oauth_state.store_id,
    )

    return _shopify_connect_frontend_url(connected=True)


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    store = _require_store(db, organization_id, store_id)

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store.id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .first()
    )
    if not connection:
        raise ShopifyNotFoundError("SHOPIFY_NOT_CONNECTED")

    db.delete(connection)
    db.commit()

    return {"ok": True, "connected": False, "store_id": store.id}


def test_connection(db: Session, organization_id: int, store_id: int) -> dict:
    store = _require_store(db, organization_id, store_id)
    connection = _require_connection(db, organization_id, store_id)

    try:
        result = test_shopify_connection(connection)
    except ShopifyAuthError:
        connection.status = "error"
        connection.last_error = "auth error"
        db.commit()
        raise
    except (ShopifyAPIError, ShopifyGraphQLError):
        connection.status = "error"
        connection.last_error = "api error"
        db.commit()
        raise

    connection.status = "connected"
    connection.last_error = None
    db.commit()

    return result


def sync_products(db: Session, organization_id: int, store_id: int) -> dict:
    store = _require_store(db, organization_id, store_id)
    connection = _require_connection(db, organization_id, store_id)

    try:
        result = sync_shopify_products(db, connection)
    except ShopifyAuthError:
        connection.status = "error"
        connection.last_error = "auth error"
        db.commit()
        raise
    except (ShopifyAPIError, ShopifyGraphQLError):
        connection.last_error = "api error"
        db.commit()
        raise

    return result


def create_order(
    db: Session,
    organization_id: int,
    store_id: int,
    items_payload: list[dict],
    customer_email: str | None,
    customer_name: str | None,
    note: str | None,
    idempotency_key: str | None,
) -> dict:
    store = _require_store(db, organization_id, store_id)
    connection = _require_connection(db, organization_id, store_id)

    try:
        result = create_shopify_draft_order(
            db=db,
            store=store,
            connection=connection,
            items_payload=items_payload,
            customer_email=customer_email,
            customer_name=customer_name,
            note=note,
            idempotency_key=idempotency_key,
        )
    except ValueError:
        raise
    except ShopifyAuthError:
        connection.status = "error"
        connection.last_error = "auth error"
        db.commit()
        raise
    except ShopifyUserError:
        raise
    except (ShopifyAPIError, ShopifyGraphQLError):
        connection.last_error = "api error"
        db.commit()
        raise

    return result


def create_poc(
    db: Session,
    organization_id: int,
    store_id: int,
    variant_id: str,
    quantity: int,
    customer_email: str,
    customer_phone: str | None,
    shipping_address: dict,
    tags: list[str],
    note: str | None,
    idempotency_key: str,
) -> dict:
    store = _require_store(db, organization_id, store_id)
    connection = _require_connection(db, organization_id, store_id)

    try:
        return create_poc_order(
            db=db,
            store=store,
            connection=connection,
            variant_id=variant_id,
            quantity=quantity,
            customer_email=customer_email,
            customer_phone=customer_phone,
            shipping_address=shipping_address,
            tags=tags,
            note=note,
            idempotency_key=idempotency_key,
        )
    except ValueError:
        raise
    except ShopifyAuthError:
        connection.status = "error"
        connection.last_error = "auth error"
        db.commit()
        raise
    except ShopifyUserError:
        raise
    except ShopifyTimeoutError:
        raise
    except (ShopifyAPIError, ShopifyGraphQLError):
        connection.last_error = "api error"
        db.commit()
        raise


def list_orders(db: Session, organization_id: int, store_id: int) -> list:
    _require_store(db, organization_id, store_id)
    return list_shopify_orders(db=db, store_id=store_id, organization_id=organization_id)


def get_order(db: Session, organization_id: int, store_id: int, order_id: int) -> dict | None:
    _require_store(db, organization_id, store_id)
    return get_shopify_order(db=db, order_id=order_id, store_id=store_id, organization_id=organization_id)
