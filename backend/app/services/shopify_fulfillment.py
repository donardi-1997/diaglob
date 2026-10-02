"""Push supplier tracking into Shopify Fulfillment Orders."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..model_domains.shipments import Shipment
from ..model_domains.supplier_orders import SupplierOrder, SupplierOrderItem
from ..models import CommerceConnection, Order, OrderItem
from ..shopify_client import ShopifyGraphQLClient, ShopifyUserError
from ..shopify_security import decrypt_shopify_secret


REQUIRED_FULFILLMENT_SCOPES = frozenset(
    {
        "read_merchant_managed_fulfillment_orders",
        "write_merchant_managed_fulfillment_orders",
    }
)

FULFILLMENT_ORDERS_QUERY = """
query DiaglobFulfillmentOrders($id: ID!) {
  order(id: $id) {
    id
    fulfillments(first: 50) {
      id
      status
      trackingInfo {
        company
        number
        url
      }
    }
    fulfillmentOrders(first: 50) {
      nodes {
        id
        status
        lineItems(first: 250) {
          nodes {
            id
            remainingQuantity
            lineItem {
              id
            }
          }
        }
      }
    }
  }
}
"""

FULFILLMENT_CREATE_MUTATION = """
mutation DiaglobFulfillmentCreate($fulfillment: FulfillmentInput!) {
  fulfillmentCreate(fulfillment: $fulfillment) {
    fulfillment {
      id
      status
      trackingInfo {
        company
        number
        url
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


class ShopifyFulfillmentError(Exception):
    pass


def missing_fulfillment_scopes(connection: CommerceConnection) -> list[str]:
    scopes = {
        value.strip()
        for value in (connection.scopes or "").split(",")
        if value.strip()
    }
    return sorted(REQUIRED_FULFILLMENT_SCOPES - scopes)


def _gid(kind: str, value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("gid://shopify/"):
        return value
    return f"gid://shopify/{kind}/{value}"


def _raw_id(value: str | None) -> str:
    return str(value or "").rstrip("/").split("/")[-1]


def _require_connection(
    db: Session,
    organization_id: int,
    store_id: int,
) -> CommerceConnection:
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if connection is None:
        raise ShopifyFulfillmentError("SHOPIFY_NOT_CONNECTED")

    missing = missing_fulfillment_scopes(connection)
    if missing:
        raise ShopifyFulfillmentError(
            "SHOPIFY_FULFILLMENT_SCOPES_REQUIRED:" + ",".join(missing)
        )
    return connection


def create_shopify_fulfillment_from_shipment(
    db: Session,
    *,
    supplier_order: SupplierOrder,
    shipment: Shipment,
    notify_customer: bool,
) -> dict[str, Any]:
    if supplier_order.order_id is None:
        raise ShopifyFulfillmentError("COMMERCE_ORDER_NOT_LINKED")

    order = (
        db.query(Order)
        .filter(
            Order.id == supplier_order.order_id,
            Order.organization_id == supplier_order.organization_id,
            Order.store_id == supplier_order.store_id,
        )
        .first()
    )
    if order is None or not order.shopify_order_id:
        raise ShopifyFulfillmentError("SHOPIFY_ORDER_NOT_FOUND")
    if not shipment.tracking_number:
        raise ShopifyFulfillmentError("TRACKING_NUMBER_REQUIRED")

    connection = _require_connection(
        db,
        supplier_order.organization_id,
        supplier_order.store_id,
    )
    token = decrypt_shopify_secret(connection.access_token_encrypted or "")
    client = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    )

    data = client.query(
        FULFILLMENT_ORDERS_QUERY,
        {"id": _gid("Order", order.shopify_order_id)},
    )
    remote_order = data.get("order") or {}
    if not remote_order:
        raise ShopifyFulfillmentError("SHOPIFY_ORDER_NOT_FOUND")

    tracking_number = shipment.tracking_number.strip()
    for fulfillment in remote_order.get("fulfillments") or []:
        info = fulfillment.get("trackingInfo") or []
        for tracking in info:
            if str(tracking.get("number") or "").strip() == tracking_number:
                return {
                    "ok": True,
                    "idempotent": True,
                    "fulfillment_id": fulfillment.get("id"),
                    "status": fulfillment.get("status"),
                }

    supplier_items = (
        db.query(SupplierOrderItem, OrderItem)
        .join(OrderItem, OrderItem.id == SupplierOrderItem.order_item_id)
        .filter(SupplierOrderItem.supplier_order_id == supplier_order.id)
        .all()
    )
    wanted = {
        str(item.shopify_line_item_id): supplier_item.quantity
        for supplier_item, item in supplier_items
        if item.shopify_line_item_id
    }
    if not wanted:
        raise ShopifyFulfillmentError("SHOPIFY_LINE_ITEMS_NOT_AVAILABLE")

    remaining = dict(wanted)
    groups: list[dict[str, Any]] = []

    for fulfillment_order in (
        (remote_order.get("fulfillmentOrders") or {}).get("nodes") or []
    ):
        if str(fulfillment_order.get("status") or "").upper() not in {
            "OPEN",
            "IN_PROGRESS",
        }:
            continue

        line_inputs = []
        for line in (
            (fulfillment_order.get("lineItems") or {}).get("nodes") or []
        ):
            line_item_id = _raw_id((line.get("lineItem") or {}).get("id"))
            requested = remaining.get(line_item_id, 0)
            available = int(line.get("remainingQuantity") or 0)
            quantity = min(requested, available)
            if quantity <= 0:
                continue
            line_inputs.append(
                {
                    "id": line.get("id"),
                    "quantity": quantity,
                }
            )
            remaining[line_item_id] = requested - quantity

        if line_inputs:
            groups.append(
                {
                    "fulfillmentOrderId": fulfillment_order.get("id"),
                    "fulfillmentOrderLineItems": line_inputs,
                }
            )

    unresolved = {key: value for key, value in remaining.items() if value > 0}
    if unresolved:
        raise ShopifyFulfillmentError("SHOPIFY_FULFILLMENT_ITEMS_UNRESOLVED")

    if not groups:
        return {
            "ok": True,
            "idempotent": True,
            "fulfillment_id": None,
            "status": "already_fulfilled",
        }

    tracking_info: dict[str, Any] = {
        "number": tracking_number,
    }
    company = (shipment.logistic_name or shipment.tracking_provider or "").strip()
    if company:
        tracking_info["company"] = company
    if shipment.tracking_url:
        tracking_info["url"] = shipment.tracking_url

    result = client.query(
        FULFILLMENT_CREATE_MUTATION,
        {
            "fulfillment": {
                "lineItemsByFulfillmentOrder": groups,
                "notifyCustomer": bool(notify_customer),
                "trackingInfo": tracking_info,
            }
        },
    )
    payload = result.get("fulfillmentCreate") or {}
    user_errors = payload.get("userErrors") or []
    if user_errors:
        message = str(user_errors[0].get("message") or "Shopify fulfillment failed")
        raise ShopifyUserError(message)

    fulfillment = payload.get("fulfillment") or {}
    if not fulfillment.get("id"):
        raise ShopifyFulfillmentError("SHOPIFY_FULFILLMENT_ID_MISSING")

    return {
        "ok": True,
        "idempotent": False,
        "fulfillment_id": fulfillment.get("id"),
        "status": fulfillment.get("status"),
    }


__all__ = [
    "REQUIRED_FULFILLMENT_SCOPES",
    "ShopifyFulfillmentError",
    "create_shopify_fulfillment_from_shipment",
    "missing_fulfillment_scopes",
]
