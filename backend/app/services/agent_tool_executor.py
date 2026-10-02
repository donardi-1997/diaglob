"""Permission-gated runtime for agent tools."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import (
    Customer,
    CustomerStoreProfile,
    Order,
    OrderItem,
    OrganizationMembership,
    Product,
)
from .action_policy import evaluate_action
from .agent_approvals import (
    AgentApprovalError,
    consume_approval,
    create_approval,
    serialize_approval,
    validate_approved_action,
)
from .ai_tool_registry import get_tool, validate_tool_arguments
from .auto_fulfillment import (
    enqueue_store_paid_orders,
    requeue_store_auto_fulfillment,
)
from .automation_flows_service import (
    activate_flow,
    create_flow,
    deactivate_flow,
    get_flow,
    list_flows,
    publish_version,
    simulate_flow,
    update_flow,
)
from .shipment_tracking import get_supplier_order_shipment
from .supplier_catalog import list_cj_products, quote_cj_freight
from .supplier_mappings import upsert_cj_variant_mapping


ToolHandler = Callable[[Session, OrganizationMembership, int, dict], Any]


class AgentToolExecutionError(Exception):
    pass


def _limit(arguments: dict, default: int = 20) -> int:
    try:
        value = int(arguments.get("limit") or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 100))


def _orders_list(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    query = db.query(Order).filter(
        Order.organization_id == membership.organization_id,
        Order.store_id == store_id,
    )
    status = str(arguments.get("status") or "").strip()
    if status:
        query = query.filter(
            or_(
                Order.lifecycle_status == status,
                Order.payment_status == status,
                Order.fulfillment_status == status,
            )
        )
    orders = query.order_by(Order.created_at.desc()).limit(_limit(arguments)).all()
    return {
        "items": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "source": order.source,
                "payment_status": order.payment_status,
                "fulfillment_status": order.fulfillment_status,
                "lifecycle_status": order.lifecycle_status,
                "total_amount": float(order.total_amount or 0),
                "currency": order.currency,
                "created_at": (
                    order.created_at.isoformat() + "Z"
                    if order.created_at
                    else None
                ),
            }
            for order in orders
        ],
        "count": len(orders),
    }


def _orders_get(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    order_id = int(arguments["order_id"])
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id == membership.organization_id,
            Order.store_id == store_id,
        )
        .first()
    )
    if order is None:
        raise AgentToolExecutionError("ORDER_NOT_FOUND")

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
        .all()
    )
    return {
        "id": order.id,
        "order_number": order.order_number,
        "source": order.source,
        "payment_status": order.payment_status,
        "fulfillment_status": order.fulfillment_status,
        "lifecycle_status": order.lifecycle_status,
        "total_amount": float(order.total_amount or 0),
        "currency": order.currency,
        "shipping_address": order.shipping_address,
        "created_at": (
            order.created_at.isoformat() + "Z"
            if order.created_at
            else None
        ),
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price or 0),
                "currency": item.currency,
                "shopify_variant_id": item.shopify_variant_id,
                "shopify_line_item_id": item.shopify_line_item_id,
            }
            for item in items
        ],
    }


def _products_list(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    query = db.query(Product).filter(
        Product.organization_id == membership.organization_id,
        Product.store_id == store_id,
        Product.active.is_(True),
    )
    search = str(arguments.get("query") or "").strip()
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Product.title.ilike(term),
                Product.handle.ilike(term),
                Product.vendor.ilike(term),
            )
        )
    products = query.order_by(Product.title).limit(_limit(arguments)).all()
    return {
        "items": [
            {
                "id": product.id,
                "title": product.title,
                "handle": product.handle,
                "vendor": product.vendor,
                "product_type": product.product_type,
                "cost": float(product.cost) if product.cost is not None else None,
                "variants": [
                    {
                        "id": variant.id,
                        "title": variant.title,
                        "sku": variant.sku,
                        "price": float(variant.price or 0),
                        "currency": variant.currency,
                        "inventory_quantity": variant.inventory_quantity,
                        "available": variant.available,
                        "shopify_variant_id": variant.shopify_variant_id,
                    }
                    for variant in product.variants
                ],
            }
            for product in products
        ],
        "count": len(products),
    }


def _customers_search(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    query = (
        db.query(Customer, CustomerStoreProfile)
        .join(
            CustomerStoreProfile,
            CustomerStoreProfile.customer_id == Customer.id,
        )
        .filter(
            Customer.organization_id == membership.organization_id,
            CustomerStoreProfile.organization_id == membership.organization_id,
            CustomerStoreProfile.store_id == store_id,
        )
    )
    search = str(arguments.get("query") or "").strip()
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Customer.name.ilike(term),
                Customer.email.ilike(term),
                Customer.phone.ilike(term),
            )
        )
    rows = query.order_by(Customer.name).limit(_limit(arguments)).all()
    return {
        "items": [
            {
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "phone": customer.phone,
                "country_code": customer.country_code,
                "orders_count": profile.orders_count,
                "total_spent": float(profile.total_spent or 0),
                "currency": profile.currency,
                "last_order_ref": profile.last_order_ref,
            }
            for customer, profile in rows
        ],
        "count": len(rows),
    }


def _tracking_get(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return get_supplier_order_shipment(
        db,
        membership.organization_id,
        store_id,
        int(arguments["supplier_order_id"]),
    )


def _cj_search(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return list_cj_products(
        db,
        membership.organization_id,
        store_id,
        query=arguments.get("query"),
        limit=_limit(arguments),
        page=max(1, int(arguments.get("page") or 1)),
    )


def _cj_quote(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return quote_cj_freight(
        db,
        membership.organization_id,
        store_id,
        start_country_code=str(arguments["start_country_code"]).upper(),
        end_country_code=str(arguments["end_country_code"]).upper(),
        zip_code=arguments.get("zip_code"),
        items=list(arguments["items"]),
    )


def _cj_map_variant(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return upsert_cj_variant_mapping(
        db,
        membership.organization_id,
        store_id,
        int(arguments["product_variant_id"]),
        external_product_id=str(arguments["external_product_id"]),
        external_variant_id=str(arguments["external_variant_id"]),
        external_sku=arguments.get("external_sku"),
        active=True,
    )


def _fulfillment_retry(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    _arguments: dict,
) -> dict:
    queued = set(
        enqueue_store_paid_orders(
            db,
            membership.organization_id,
            store_id,
        )
    )
    queued.update(
        requeue_store_auto_fulfillment(
            db,
            membership.organization_id,
            store_id,
        )
    )
    return {
        "queued_job_ids": sorted(queued),
        "count": len(queued),
        "worker_execution": "asynchronous",
    }


def _automations_list(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    items = list_flows(
        db,
        membership.organization_id,
        store_id,
        status=arguments.get("status"),
    )
    return {"items": items, "count": len(items)}


def _automations_create(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return create_flow(
        db,
        membership.organization_id,
        store_id,
        membership.user_id,
        str(arguments["name"]),
        arguments.get("description"),
        dict(arguments.get("graph") or {}),
    )


def _automations_update(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    graph = arguments.get("graph")
    return update_flow(
        db,
        membership.organization_id,
        store_id,
        int(arguments["flow_id"]),
        arguments.get("name"),
        arguments.get("description"),
        dict(graph) if graph is not None else None,
    )


def _automations_publish(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    flow_id = int(arguments["flow_id"])
    flow = get_flow(
        db,
        membership.organization_id,
        store_id,
        flow_id,
    )
    current = flow.get("current_version")
    if not current:
        raise AgentToolExecutionError("AUTOMATION_VERSION_REQUIRED")
    return publish_version(
        db,
        membership.organization_id,
        store_id,
        flow_id,
        int(current["id"]),
    )


def _automations_activate(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return activate_flow(
        db,
        membership.organization_id,
        store_id,
        int(arguments["flow_id"]),
    )


def _automations_pause(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    return deactivate_flow(
        db,
        membership.organization_id,
        store_id,
        int(arguments["flow_id"]),
    )


def _automations_test(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    arguments: dict,
) -> dict:
    flow = get_flow(
        db,
        membership.organization_id,
        store_id,
        int(arguments["flow_id"]),
    )
    current = flow.get("current_version")
    if not current:
        raise AgentToolExecutionError("AUTOMATION_VERSION_REQUIRED")
    return simulate_flow(
        db,
        membership.organization_id,
        store_id,
        dict(current["graph"]),
    )


def _analytics_summary(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
    _arguments: dict,
) -> dict:
    total_orders, total_value = (
        db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0),
        )
        .filter(
            Order.organization_id == membership.organization_id,
            Order.store_id == store_id,
        )
        .one()
    )
    paid_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.organization_id == membership.organization_id,
            Order.store_id == store_id,
            Order.payment_status == "paid",
        )
        .scalar()
        or 0
    )
    return {
        "total_orders": int(total_orders or 0),
        "paid_orders": int(paid_orders),
        "total_order_value": float(total_value or 0),
    }


HANDLERS: dict[str, ToolHandler] = {
    "orders.list": _orders_list,
    "orders.get": _orders_get,
    "products.list": _products_list,
    "customers.search": _customers_search,
    "tracking.get": _tracking_get,
    "suppliers.cj.search": _cj_search,
    "suppliers.cj.quote": _cj_quote,
    "suppliers.cj.map_variant": _cj_map_variant,
    "fulfillment.retry": _fulfillment_retry,
    "automations.list": _automations_list,
    "automations.create": _automations_create,
    "automations.update": _automations_update,
    "automations.publish": _automations_publish,
    "automations.activate": _automations_activate,
    "automations.pause": _automations_pause,
    "automations.test": _automations_test,
    "analytics.summary": _analytics_summary,
}


def execute_agent_tool(
    db: Session,
    membership: OrganizationMembership,
    *,
    tool_name: str,
    store_id: int,
    arguments: dict | None = None,
    approval_id: int | None = None,
) -> dict:
    arguments = arguments or {}
    tool = get_tool(tool_name)
    if tool is None:
        return {
            "status": "denied",
            "code": "TOOL_UNKNOWN",
            "message": "Unknown tool.",
        }

    argument_errors = validate_tool_arguments(tool, arguments)
    if argument_errors:
        return {
            "status": "denied",
            "code": "TOOL_ARGUMENTS_INVALID",
            "message": "; ".join(argument_errors[:10]),
            "tool_name": tool_name,
        }

    decision = evaluate_action(
        db,
        membership,
        tool.action,
        store_id=store_id,
    )
    if not decision.allowed:
        return {
            "status": "denied",
            **decision.as_dict(),
        }

    handler = HANDLERS.get(tool_name)
    if handler is None:
        return {
            "status": "unavailable",
            "code": "TOOL_NOT_IMPLEMENTED",
            "tool_name": tool_name,
        }

    if decision.confirmation != "none":
        if approval_id is None:
            approval = create_approval(
                db,
                membership,
                store_id=store_id,
                tool_name=tool_name,
                action=tool.action,
                arguments=arguments,
                decision=decision,
            )
            return {
                "status": "confirmation_required",
                "tool_name": tool_name,
                "title": tool.title,
                "description": tool.description,
                "risk": decision.risk,
                "confirmation": decision.confirmation,
                "approval": serialize_approval(approval),
            }
        try:
            approval = validate_approved_action(
                db,
                membership,
                approval_id,
                tool_name=tool_name,
                action=tool.action,
                store_id=store_id,
                arguments=arguments,
            )
            # Consume before the side effect. If execution fails, the user must
            # explicitly approve a new attempt instead of silently replaying it.
            consume_approval(db, approval)
        except AgentApprovalError as exc:
            return {
                "status": "denied",
                "code": str(exc),
                "message": str(exc),
                "tool_name": tool_name,
            }

    try:
        result = handler(
            db,
            membership,
            store_id,
            arguments,
        )
    except Exception as exc:
        return {
            "status": "error",
            "code": "TOOL_EXECUTION_FAILED",
            "message": str(exc),
            "tool_name": tool_name,
        }

    return {
        "status": "success",
        "tool_name": tool_name,
        "result": result,
    }


__all__ = [
    "AgentToolExecutionError",
    "HANDLERS",
    "execute_agent_tool",
]
