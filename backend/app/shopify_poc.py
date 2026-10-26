"""Retired POC order creation, including internal callers.

The public route is already retired. Keep its compatibility helper fail-closed
as well: no Admin orderCreate, local order, token access or external side effect.
Buyer purchases must be completed through Shopify-hosted checkout.
"""

from sqlalchemy.orm import Session

from .models import CommerceConnection, Store
from .shopify_client import ShopifyUserError


def create_poc_order(
    *,
    db: Session,
    store: Store,
    connection: CommerceConnection,
    variant_id: str,
    quantity: int,
    customer_email: str,
    customer_phone: str | None,
    shipping_address: dict,
    tags: list[str] | None,
    note: str | None,
    idempotency_key: str,
) -> dict:
    raise ShopifyUserError("SHOPIFY_CHECKOUT_REQUIRED")
