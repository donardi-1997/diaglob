"""Retired legacy COD order creation.

Shopify App Store requirement 1.1.2 does not permit a conversational sale to
register a buyer order via Admin API while bypassing Shopify Checkout.
This compatibility entry point deliberately has no GraphQL, database or other
side effects; callers must use Shopify-hosted checkout via a Draft Order URL.
"""

from sqlalchemy.orm import Session

from .models import CommerceConnection, Store
from .shopify_client import ShopifyUserError


def create_shopify_cod_order(
    *,
    db: Session,
    store: Store,
    connection: CommerceConnection,
    customer_id: int,
    variant_local_id: int,
    quantity: int,
    customer_email: str | None,
    customer_phone: str,
    shipping_address: dict,
    note: str,
    idempotency_key: str,
) -> dict:
    """Reject every attempt to register a conversational buyer order offsite."""
    raise ShopifyUserError("SHOPIFY_CHECKOUT_REQUIRED")
