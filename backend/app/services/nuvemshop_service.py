"""Nuvemshop service.

Application orchestration for Nuvemshop connection, sync, and orders.
Does NOT own HTTP requests (client does).
Does NOT own analytics formulas.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from ..integrations.nuvemshop.client import (
    NuvemshopError,
    get_store_info,
    get_order,
    list_products,
    list_customers,
    list_orders,
    parse_product,
    parse_customer,
    parse_order,
)
from ..models import CommerceConnection, Customer, NuvemshopOAuthState, Order, OrderItem, Product, ProductVariant, Store
from ..nuvemshop_security import encrypt_secret, decrypt_secret
from .trial_service import (
    TrialIdentityAlreadyUsed,
    activate_trial_for_verified_store,
)

logger = logging.getLogger(__name__)

NUVEMSHOP_CLIENT_ID = os.getenv("NUVEMSHOP_CLIENT_ID", "")
NUVEMSHOP_CLIENT_SECRET = os.getenv("NUVEMSHOP_CLIENT_SECRET", "")
NUVEMSHOP_REDIRECT_URI = os.getenv("NUVEMSHOP_REDIRECT_URI", "")


class NuvemshopNotFoundError(Exception):
    pass


class NuvemshopConnectionError(Exception):
    pass


class NuvemshopOAuthError(Exception):
    pass


class NuvemshopProviderError(Exception):
    pass


def get_oauth_url(
    db: Session,
    organization_id: int,
    store_id: int,
    user_id: int,
) -> dict:
    """Generate Nuvemshop OAuth URL with persisted state."""
    state = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=10)

    auth_url = (
        "https://www.tiendanube.com/apps/authorize?"
        + urlencode({
            "client_id": NUVEMSHOP_CLIENT_ID,
            "redirect_uri": NUVEMSHOP_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        })
    )

    oauth_state = NuvemshopOAuthState(
        state=state,
        organization_id=organization_id,
        store_id=store_id,
        user_id=user_id,
        expires_at=expires_at,
        used=False,
        created_at=now,
    )
    db.add(oauth_state)
    db.commit()

    return {
        "authorization_url": auth_url,
        "state": state,
    }


def process_oauth_callback(
    db: Session,
    code: str,
    state: str,
    organization_id: int,
    store_id: int,
) -> dict:
    """Exchange OAuth code for access token and discover store."""
    import httpx

    # Validate and consume persisted state
    oauth_state = (
        db.query(NuvemshopOAuthState)
        .filter(
            NuvemshopOAuthState.state == state,
            NuvemshopOAuthState.used.is_(False),
        )
        .first()
    )
    if not oauth_state:
        raise NuvemshopOAuthError("Invalid or already used OAuth state")
    if oauth_state.expires_at < datetime.utcnow():
        raise NuvemshopOAuthError("OAuth state expired")
    if oauth_state.organization_id != organization_id or oauth_state.store_id != store_id:
        raise NuvemshopOAuthError("OAuth state does not match the target store")

    oauth_state.used = True
    db.flush()

    token_url = "https://www.tiendanube.com/oauth/token"
    payload = {
        "client_id": NUVEMSHOP_CLIENT_ID,
        "client_secret": NUVEMSHOP_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": NUVEMSHOP_REDIRECT_URI,
    }

    try:
        response = httpx.post(token_url, json=payload, timeout=30)
        response.raise_for_status()
        token_data = response.json()
    except Exception as exc:
        raise NuvemshopConnectionError(f"Token exchange failed: {exc}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise NuvemshopConnectionError("No access token received")

    nuvemshop_store_id = token_data.get("store_id")
    if not nuvemshop_store_id:
        raise NuvemshopConnectionError("No store ID received")

    # Get store info
    try:
        store_info = get_store_info(access_token, str(nuvemshop_store_id))
    except NuvemshopError as exc:
        raise NuvemshopConnectionError(f"Failed to get store info: {exc}")

    # Encrypt token
    encrypted_token = encrypt_secret(access_token)

    return {
        "encrypted_token": encrypted_token,
        "nuvemshop_store_id": str(nuvemshop_store_id),
        "store_name": store_info.get("name", ""),
        "currency": store_info.get("currency") or "BRL",
        "timezone": store_info.get("timezone") or "America/Sao_Paulo",
        "country": store_info.get("country") or "BR",
    }


def connect_account(
    db: Session,
    organization_id: int,
    store_id: int,
    encrypted_token: str,
    nuvemshop_store_id: str,
    store_name: str,
    currency: str,
    timezone: str,
    country: str,
) -> dict:
    """Create Nuvemshop connection for a store."""
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
        raise NuvemshopNotFoundError("Store not found")

    existing = (
        db.query(CommerceConnection)
        .filter(CommerceConnection.store_id == store_id)
        .first()
    )
    if existing:
        raise NuvemshopConnectionError("COMMERCE_ALREADY_CONNECTED")

    conflicting = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "nuvemshop",
            CommerceConnection.external_store_url == str(nuvemshop_store_id),
        )
        .first()
    )
    if conflicting:
        raise NuvemshopConnectionError("NUVEMSHOP_STORE_ALREADY_CONNECTED")

    try:
        activate_trial_for_verified_store(
            db,
            organization_id=organization_id,
            store_id=store_id,
            provider="nuvemshop",
            external_identity=str(nuvemshop_store_id),
        )
    except TrialIdentityAlreadyUsed as exc:
        db.commit()
        raise NuvemshopConnectionError(str(exc)) from exc

    now = datetime.utcnow()

    connection = CommerceConnection(
        organization_id=organization_id,
        store_id=store_id,
        provider="nuvemshop",
        external_store_url=nuvemshop_store_id,
        access_token_encrypted=encrypted_token,
        scopes="",
        status="connected",
        connected_at=now,
        created_at=now,
        updated_at=now,
    )

    db.add(connection)
    db.commit()
    db.refresh(connection)

    return {
        "ok": True,
        "connected": True,
        "store_id": store_id,
        "nuvemshop_store_id": nuvemshop_store_id,
        "store_name": store_name,
        "currency": currency,
    }


def disconnect(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Remove Nuvemshop connection."""
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "nuvemshop",
        )
        .first()
    )
    if not connection:
        raise NuvemshopNotFoundError("Nuvemshop not connected")

    db.delete(connection)
    db.commit()

    return {"ok": True, "connected": False, "store_id": store_id}


def get_connection_status(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Get Nuvemshop connection status."""
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "nuvemshop",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "nuvemshop_store_id": None,
            "store_name": None,
            "currency": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "nuvemshop_store_id": connection.external_store_url,
        "store_name": None,  # Not stored in CommerceConnection
        "currency": None,
        "connected_at": (
            connection.connected_at.isoformat() + "Z"
            if connection.connected_at
            else None
        ),
        "last_sync_at": (
            connection.last_sync_at.isoformat() + "Z"
            if connection.last_sync_at
            else None
        ),
        "last_error": connection.last_error,
    }


def sync_products(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Sync products from Nuvemshop to local catalog."""
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "nuvemshop",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise NuvemshopNotFoundError("Nuvemshop not connected")

    token = decrypt_secret(connection.access_token_encrypted)
    nuvemshop_store_id = connection.external_store_url

    fetched = 0
    created = 0
    updated = 0
    failed = 0

    page = 1
    per_page = 50

    while True:
        try:
            data = list_products(token, nuvemshop_store_id, page=page, per_page=per_page)
        except NuvemshopError as exc:
            raise

        products = data if isinstance(data, list) else data.get("data") or []

        for product_data in products:
            fetched += 1
            try:
                parsed = parse_product(product_data)

                existing = (
                    db.query(Product)
                    .filter(
                        Product.store_id == store_id,
                        Product.organization_id == organization_id,
                        Product.external_id == parsed["external_id"],
                    )
                    .first()
                )

                if existing:
                    existing.title = parsed["title"]
                    existing.handle = parsed.get("handle")
                    existing.description = parsed.get("description") or ""
                    existing.image_url = parsed.get("image_url")
                    existing.active = parsed["active"]
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    product = Product(
                        organization_id=organization_id,
                        store_id=store_id,
                        external_id=parsed["external_id"],
                        title=parsed["title"],
                        handle=parsed.get("handle"),
                        description=parsed.get("description") or "",
                        image_url=parsed.get("image_url"),
                        active=parsed["active"],
                        source="nuvemshop",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(product)
                    db.flush()
                    created += 1

                # Sync variants
                for variant_data in parsed.get("variants", []):
                    _sync_variant(db, store_id, organization_id, parsed["external_id"], variant_data)

            except Exception as exc:
                logger.warning("Failed to sync product %s: %s", parsed.get("external_id"), exc)
                failed += 1

        if len(products) < per_page:
            break
        page += 1

    connection.last_sync_at = datetime.utcnow()
    connection.last_error = None
    db.commit()

    return {
        "ok": True,
        "fetched": fetched,
        "created": created,
        "updated": updated,
        "failed": failed,
    }


def _sync_variant(
    db: Session,
    store_id: int,
    organization_id: int,
    product_external_id: str,
    variant_data: dict,
):
    """Sync a single product variant."""
    product = (
        db.query(Product)
        .filter(
            Product.store_id == store_id,
            Product.organization_id == organization_id,
            Product.external_id == product_external_id,
        )
        .first()
    )
    if not product:
        return

    existing = (
        db.query(ProductVariant)
        .filter(
            ProductVariant.product_id == product.id,
            ProductVariant.external_id == variant_data["external_id"],
        )
        .first()
    )

    if existing:
        existing.title = variant_data["title"]
        existing.sku = variant_data.get("sku")
        existing.price = float(variant_data.get("price") or 0)
        existing.compare_at_price = float(variant_data.get("compare_at_price") or 0) if variant_data.get("compare_at_price") else None
        existing.inventory_quantity = variant_data.get("inventory_quantity") or 0
        existing.available = variant_data.get("available", True)
        existing.updated_at = datetime.utcnow()
    else:
        variant = ProductVariant(
            product_id=product.id,
            store_id=store_id,
            organization_id=organization_id,
            external_id=variant_data["external_id"],
            title=variant_data["title"],
            sku=variant_data.get("sku"),
            price=float(variant_data.get("price") or 0),
            compare_at_price=float(variant_data.get("compare_at_price") or 0) if variant_data.get("compare_at_price") else None,
            inventory_quantity=variant_data.get("inventory_quantity") or 0,
            available=variant_data.get("available", True),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(variant)


def sync_orders(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Sync orders from Nuvemshop to local database."""
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "nuvemshop",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise NuvemshopNotFoundError("Nuvemshop not connected")

    token = decrypt_secret(connection.access_token_encrypted)
    nuvemshop_store_id = connection.external_store_url

    fetched = 0
    created = 0
    updated = 0
    failed = 0

    page = 1
    per_page = 50

    while True:
        try:
            data = list_orders(token, nuvemshop_store_id, page=page, per_page=per_page)
        except NuvemshopError as exc:
            raise

        orders = data if isinstance(data, list) else data.get("data") or []

        for order_data in orders:
            fetched += 1
            try:
                parsed = parse_order(order_data)

                existing = (
                    db.query(Order)
                    .filter(
                        Order.store_id == store_id,
                        Order.organization_id == organization_id,
                        Order.external_order_id == parsed["external_order_id"],
                    )
                    .first()
                )

                if existing:
                    existing.financial_status = parsed["financial_status"]
                    existing.payment_method = parsed["payment_method"]
                    existing.payment_status = parsed["payment_status"]
                    existing.fulfillment_status = parsed.get("fulfillment_status")
                    existing.note = parsed.get("note")
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    order = Order(
                        organization_id=organization_id,
                        store_id=store_id,
                        external_order_id=parsed["external_order_id"],
                        order_number=parsed["order_number"],
                        total_amount=parsed["total_amount"],
                        currency=parsed["currency"],
                        financial_status=parsed["financial_status"],
                        payment_method=parsed["payment_method"],
                        payment_status=parsed["payment_status"],
                        fulfillment_status=parsed.get("fulfillment_status"),
                        note=parsed.get("note"),
                        source="nuvemshop",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(order)
                    created += 1

            except Exception as exc:
                logger.warning("Failed to sync order %s: %s", order_data.get("id"), exc)
                failed += 1

        if len(orders) < per_page:
            break
        page += 1

    connection.last_sync_at = datetime.utcnow()
    connection.last_error = None
    db.commit()

    return {
        "ok": True,
        "fetched": fetched,
        "created": created,
        "updated": updated,
        "failed": failed,
    }


# ============================================================
# WEBHOOK EVENT PROCESSING
# ============================================================

# Events that require fetching the full resource from the API
_RESOURCE_FETCH_EVENTS = frozenset({
    "order/created",
    "order/paid",
    "order/cancelled",
    "order/updated",
    "order/fulfilled",
})


def process_webhook_event(
    db: Session,
    connection: CommerceConnection,
    event: str,
    resource_id: int | str | None,
) -> dict:
    """Process a Nuvemshop webhook event.

    Thin payloads only carry event type and resource ID.
    For order events, we fetch the full resource from the API.
    """
    store_id = connection.store_id
    organization_id = connection.organization_id
    token = decrypt_secret(connection.access_token_encrypted)
    nuvemshop_store_id = connection.external_store_url

    if event in _RESOURCE_FETCH_EVENTS and resource_id:
        return _process_order_event(
            db, token, nuvemshop_store_id,
            store_id, organization_id, event, str(resource_id),
        )

    if event == "app/uninstalled":
        connection.status = "disconnected"
        connection.last_error = "App uninstalled from Nuvemshop store"
        db.commit()
        return {"ok": True, "action": "disconnected"}

    # Unknown or unhandled event — acknowledge
    return {"ok": True, "action": "ignored", "event": event}


def _process_order_event(
    db: Session,
    token: str,
    nuvemshop_store_id: str,
    store_id: int,
    organization_id: int,
    event: str,
    order_id: str,
) -> dict:
    """Fetch full order from Nuvemshop API and upsert locally."""
    try:
        order_data = get_order(token, nuvemshop_store_id, order_id)
    except NuvemshopError as exc:
        logger.warning("Failed to fetch order %s: %s", order_id, exc)
        return {"ok": False, "error": str(exc)}

    parsed = parse_order(order_data)

    existing = (
        db.query(Order)
        .filter(
            Order.store_id == store_id,
            Order.organization_id == organization_id,
            Order.external_order_id == parsed["external_order_id"],
        )
        .first()
    )

    if existing:
        existing.financial_status = parsed["financial_status"]
        existing.payment_method = parsed["payment_method"]
        existing.payment_status = parsed["payment_status"]
        existing.fulfillment_status = parsed.get("fulfillment_status")
        existing.note = parsed.get("note")
        existing.updated_at = datetime.utcnow()
        action = "updated"
    else:
        order = Order(
            organization_id=organization_id,
            store_id=store_id,
            external_order_id=parsed["external_order_id"],
            order_number=parsed["order_number"],
            total_amount=parsed["total_amount"],
            currency=parsed["currency"],
            financial_status=parsed["financial_status"],
            payment_method=parsed["payment_method"],
            payment_status=parsed["payment_status"],
            fulfillment_status=parsed.get("fulfillment_status"),
            note=parsed.get("note"),
            source="nuvemshop",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(order)
        action = "created"

    db.commit()

    # Emit automation event for order.created (for PIX reminders, etc.)
    if event == "order/created":
        _emit_order_created_event(
            db, organization_id, store_id, parsed,
        )

    return {"ok": True, "action": action, "order_id": parsed["external_order_id"]}


def _emit_order_created_event(
    db: Session,
    organization_id: int,
    store_id: int,
    parsed_order: dict,
):
    """Emit order.created automation event for Nuvemshop orders.

    This triggers PIX pending reminders and other automations.
    """
    try:
        from ..automations import run_automations_for_event

        run_automations_for_event(
            db=db,
            organization_id=organization_id,
            store_id=store_id,
            event_type="order.created",
            payload={
                "order_id": parsed_order["external_order_id"],
                "order_number": parsed_order["order_number"],
                "total_amount": float(parsed_order["total_amount"]),
                "currency": parsed_order["currency"],
                "payment_method": parsed_order.get("payment_method", ""),
                "payment_status": parsed_order.get("payment_status", ""),
                "financial_status": parsed_order.get("financial_status", ""),
                "source": "nuvemshop",
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit order.created event for Nuvemshop order: %s",
            exc,
        )
