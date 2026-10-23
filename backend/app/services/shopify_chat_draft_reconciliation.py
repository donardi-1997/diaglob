"""Verified Shopify draft -> order binding for conversational checkouts.

The note attribute is merely a lookup hint; it can be supplied by buyers.
Never accept it as proof of an order or an AI sales attribution. Query Shopify
for the actual DraftOrder.order relationship using this shop's access token.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Order
from ..shopify_client import ShopifyGraphQLClient
from ..shopify_security import decrypt_shopify_secret
from ..shopify_token_lifecycle import connection_access_token


_REFERENCE = re.compile(r"chat-checkout:[0-9]+:[0-9]+")
_DRAFT_ORDER_CONVERSION_QUERY = """
query VerifyShopifyDraftConversion($draftId: ID!) {
  draftOrder(id: $draftId) {
    id
    order { id }
  }
}
"""


class ShopifyDraftConversionNotReady(RuntimeError):
    """Shopify has not exposed the draft's completed order yet; retry webhook."""


def _candidate_reference(note_attributes: Any) -> str | None:
    """Accept only one unambiguous app-scoped marker from a Shopify order."""
    if not isinstance(note_attributes, list):
        return None
    found = [
        item.get("value")
        for item in note_attributes
        if isinstance(item, dict) and item.get("name") == "diaglob_checkout_ref"
    ]
    if len(found) != 1 or not isinstance(found[0], str):
        return None
    if not _REFERENCE.fullmatch(found[0]):
        return None
    return found[0]


def verified_chat_draft_for_order(
    db: Session,
    *,
    connection: CommerceConnection,
    shopify_order_id: str,
    note_attributes: Any,
) -> Order | None:
    """Find a local pending draft *only* after Shopify attests the conversion.

    All decisions are scoped to the authorized connection's tenant and store.
    Missing references or mismatched Shopify draft/order IDs leave unrelated
    orders untouched. Shopify API failures propagate for safe webhook retry.
    """
    ref = _candidate_reference(note_attributes)
    if ref is None or not shopify_order_id.isascii() or not shopify_order_id.isdigit():
        return None

    candidates = (
        db.query(Order)
        .filter(
            Order.organization_id == connection.organization_id,
            Order.store_id == connection.store_id,
            Order.source == "shopify_chat_checkout",
            Order.idempotency_key == ref,
            Order.shopify_draft_order_id.isnot(None),
            Order.shopify_order_id.is_(None),
            Order.external_creation_status == "created",
        )
        .limit(2)
        .all()
    )
    if len(candidates) != 1:
        return None

    draft = candidates[0]
    token = connection_access_token(connection, decrypt_legacy=decrypt_shopify_secret)
    result = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    ).query(
        _DRAFT_ORDER_CONVERSION_QUERY,
        {"draftId": draft.shopify_draft_order_id},
    )
    linked = result.get("draftOrder") if isinstance(result, dict) else None
    if not isinstance(linked, dict) or linked.get("id") != draft.shopify_draft_order_id:
        return None
    converted = linked.get("order")
    if converted is None:
        # Do not write a second local Order while Shopify's draft conversion
        # is not yet visible through Admin GraphQL; retry the signed webhook.
        raise ShopifyDraftConversionNotReady("SHOPIFY_DRAFT_CONVERSION_NOT_READY")
    target_order_gid = f"gid://shopify/Order/{int(shopify_order_id)}"
    if not isinstance(converted, dict) or converted.get("id") != target_order_gid:
        return None
    return draft
