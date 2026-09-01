"""
Customer Intelligence service for Diaglob.

Deterministic segmentation based on real data.
No AI inference, no mock data, no revenue attribution.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    func,
    case,
    and_,
    or_,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    Customer,
    CustomerStoreProfile,
    Message,
    Order,
    Store,
)


# ============================================================
# CONFIGURATION — SEGMENTATION THRESHOLDS
# ============================================================

NEW_CUSTOMER_DAYS = 14
INTERESTED_MIN_CONVERSATIONS = 2
HIGH_INTENT_RECENCY_DAYS = 7
INACTIVE_DAYS = 60
AT_RISK_DAYS = 30
VIP_MIN_ORDERS = 5

VALID_ORDER_STATUSES = ("created",)


# ============================================================
# SEGMENT ENUM (string constants)
# ============================================================

SEGMENT_NEW = "new"
SEGMENT_INTERESTED = "interested"
SEGMENT_HIGH_INTENT = "high_intent"
SEGMENT_BUYER = "buyer"
SEGMENT_REPEAT_BUYER = "repeat_buyer"
SEGMENT_VIP = "vip"
SEGMENT_INACTIVE = "inactive"

FLAG_AT_RISK = "at_risk"


# ============================================================
# HELPERS
# ============================================================


def _days_since(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    delta = now - dt
    return max(0, delta.days)


def _classify_customer(
    *,
    now: datetime,
    created_at: datetime,
    conversation_count: int,
    last_interaction_at: datetime | None,
    successful_order_count: int,
    last_order_at: datetime | None,
) -> tuple[str, list[str]]:
    """
    Deterministic classification.

    Returns (primary_segment, flags).
    """
    flags: list[str] = []
    customer_age_days = _days_since(created_at, now) or 0
    days_since_purchase = _days_since(last_order_at, now)
    days_since_interaction = _days_since(
        last_interaction_at, now
    )

    primary = SEGMENT_NEW

    if successful_order_count >= VIP_MIN_ORDERS:
        primary = SEGMENT_VIP
    elif successful_order_count >= 2:
        primary = SEGMENT_REPEAT_BUYER
    elif successful_order_count >= 1:
        primary = SEGMENT_BUYER
    elif (
        conversation_count >= INTERESTED_MIN_CONVERSATIONS
        or (
            days_since_interaction is not None
            and days_since_interaction <= HIGH_INTENT_RECENCY_DAYS
        )
    ):
        # Interested vs High Intent:
        # High intent requires recent interaction (<=7 days)
        # AND either multiple conversations or a failed/unknown order attempt
        if (
            days_since_interaction is not None
            and days_since_interaction <= HIGH_INTENT_RECENCY_DAYS
        ):
            primary = SEGMENT_HIGH_INTENT
        else:
            primary = SEGMENT_INTERESTED
    else:
        # No orders, limited conversation activity
        if (
            days_since_interaction is not None
            and days_since_interaction >= INACTIVE_DAYS
        ):
            primary = SEGMENT_INACTIVE
        elif customer_age_days <= NEW_CUSTOMER_DAYS:
            primary = SEGMENT_NEW
        else:
            primary = SEGMENT_NEW

    # AT_RISK flag:
    # Applies only to customers who have made at least one purchase
    # and haven't purchased recently.
    if (
        successful_order_count >= 1
        and days_since_purchase is not None
        and days_since_purchase >= AT_RISK_DAYS
    ):
        flags.append(FLAG_AT_RISK)

    # Also mark as at risk if previously active buyer
    # with no interaction for extended period
    if (
        successful_order_count >= 1
        and days_since_interaction is not None
        and days_since_interaction >= AT_RISK_DAYS
        and FLAG_AT_RISK not in flags
    ):
        flags.append(FLAG_AT_RISK)

    return primary, flags


# ============================================================
# QUERY BUILDER — CUSTOMER METRICS (NO N+1)
# ============================================================


def _build_customer_metrics_subquery(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
):
    """
    Build a single query that computes per-customer metrics
    from conversations, messages, and orders.
    """

    # --- Conversation aggregates per customer ---
    conv_conv = (
        db.query(
            Conversation.customer_id,
            func.count(Conversation.id).label(
                "conversation_count"
            ),
            func.max(Conversation.updated_at).label(
                "last_interaction_at"
            ),
            func.min(Conversation.created_at).label(
                "first_interaction_at"
            ),
        )
        .filter(
            Conversation.organization_id
            == organization_id,
        )
    )

    if store_id is not None:
        conv_conv = conv_conv.filter(
            Conversation.store_id == store_id
        )

    conv_agg = conv_conv.group_by(
        Conversation.customer_id
    ).subquery()

    # --- Message count per customer (via conversations) ---
    msg_conv = (
        db.query(
            Conversation.customer_id,
            func.count(Message.id).label(
                "message_count"
            ),
        )
        .join(
            Message,
            Message.conversation_id == Conversation.id,
        )
        .filter(
            Conversation.organization_id
            == organization_id,
        )
    )

    if store_id is not None:
        msg_conv = msg_conv.filter(
            Conversation.store_id == store_id
        )

    msg_agg = msg_conv.group_by(
        Conversation.customer_id
    ).subquery()

    # --- Order aggregates per customer ---
    # Only count orders with external_creation_status = 'created'
    # as successful purchases.
    order_agg_q = (
        db.query(
            Order.customer_id,
            func.count(Order.id).label(
                "successful_order_count"
            ),
            func.max(Order.created_at).label(
                "last_order_at"
            ),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.customer_id.isnot(None),
            Order.external_creation_status.in_(
                VALID_ORDER_STATUSES
            ),
        )
    )

    if store_id is not None:
        order_agg_q = order_agg_q.filter(
            Order.store_id == store_id
        )

    order_agg = order_agg_q.group_by(
        Order.customer_id
    ).subquery()

    # --- Spend by currency per customer ---
    spend_q = (
        db.query(
            Order.customer_id,
            Order.currency,
            func.coalesce(
                func.sum(Order.total_amount), 0
            ).label("total_spend"),
            func.coalesce(
                func.avg(Order.total_amount), 0
            ).label("avg_order_value"),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.customer_id.isnot(None),
            Order.external_creation_status.in_(
                VALID_ORDER_STATUSES
            ),
        )
    )

    if store_id is not None:
        spend_q = spend_q.filter(
            Order.store_id == store_id
        )

    spend_agg = spend_q.group_by(
        Order.customer_id, Order.currency
    ).subquery()

    return conv_agg, msg_agg, order_agg, spend_agg


# ============================================================
# PUBLIC API — GET CUSTOMER METRICS
# ============================================================


def get_customer_metrics(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Compute metrics for all customers in scope.
    Returns list of dicts with segment classification.
    """
    now = datetime.utcnow()

    conv_agg, msg_agg, order_agg, spend_agg = (
        _build_customer_metrics_subquery(
            db, organization_id, store_id
        )
    )

    # Base customer query
    base_q = (
        db.query(Customer)
        .filter(
            Customer.organization_id == organization_id,
        )
    )

    if store_id is not None:
        # Only customers that have activity in this store
        # or have a store profile for this store
        base_q = base_q.outerjoin(
            CustomerStoreProfile,
            and_(
                CustomerStoreProfile.customer_id
                == Customer.id,
                CustomerStoreProfile.store_id
                == store_id,
            ),
        )

    customers = base_q.all()

    results = []

    for cust in customers:
        # Conversation metrics
        conv_row = (
            db.query(
                conv_agg.c.conversation_count,
                conv_agg.c.last_interaction_at,
                conv_agg.c.first_interaction_at,
            )
            .filter(
                conv_agg.c.customer_id == cust.id
            )
            .first()
        )

        conversation_count = (
            conv_row.conversation_count
            if conv_row
            else 0
        )
        last_interaction_at = (
            conv_row.last_interaction_at
            if conv_row
            else None
        )
        first_interaction_at = (
            conv_row.first_interaction_at
            if conv_row
            else None
        )

        # Message metrics
        msg_row = (
            db.query(msg_agg.c.message_count)
            .filter(
                msg_agg.c.customer_id == cust.id
            )
            .first()
        )

        message_count = (
            msg_row.message_count if msg_row else 0
        )

        # Order metrics
        order_row = (
            db.query(
                order_agg.c.successful_order_count,
                order_agg.c.last_order_at,
            )
            .filter(
                order_agg.c.customer_id == cust.id
            )
            .first()
        )

        successful_order_count = (
            order_row.successful_order_count
            if order_row
            else 0
        )
        last_order_at = (
            order_row.last_order_at if order_row else None
        )

        # Spend by currency
        spend_rows = (
            db.query(
                spend_agg.c.currency,
                spend_agg.c.total_spend,
                spend_agg.c.avg_order_value,
            )
            .filter(
                spend_agg.c.customer_id == cust.id
            )
            .all()
        )

        spend_by_currency: dict[str, dict] = {}
        for row in spend_rows:
            spend_by_currency[row.currency] = {
                "total": float(row.total_spend),
                "avg_order_value": float(
                    row.avg_order_value
                ),
            }

        # Classify
        primary_segment, flags = _classify_customer(
            now=now,
            created_at=cust.created_at,
            conversation_count=conversation_count,
            last_interaction_at=last_interaction_at,
            successful_order_count=successful_order_count,
            last_order_at=last_order_at,
        )

        days_since_last_interaction = _days_since(
            last_interaction_at, now
        )
        days_since_last_purchase = _days_since(
            last_order_at, now
        )

        # Store info from profile
        store_name = None
        store_id_val = None
        if store_id is not None:
            store_obj = (
                db.query(Store)
                .filter(Store.id == store_id)
                .first()
            )
            if store_obj:
                store_name = store_obj.name
                store_id_val = store_obj.id

        results.append(
            {
                "id": cust.id,
                "name": cust.name,
                "phone": cust.phone,
                "email": cust.email,
                "country_code": cust.country_code,
                "created_at": cust.created_at.isoformat(),
                "store_name": store_name,
                "store_id": store_id_val,
                "conversation_count": conversation_count,
                "message_count": message_count,
                "first_interaction_at": (
                    first_interaction_at.isoformat()
                    if first_interaction_at
                    else None
                ),
                "last_interaction_at": (
                    last_interaction_at.isoformat()
                    if last_interaction_at
                    else None
                ),
                "successful_order_count": successful_order_count,
                "last_order_at": (
                    last_order_at.isoformat()
                    if last_order_at
                    else None
                ),
                "spend_by_currency": spend_by_currency,
                "primary_segment": primary_segment,
                "flags": flags,
                "days_since_last_interaction": (
                    days_since_last_interaction
                ),
                "days_since_last_purchase": (
                    days_since_last_purchase
                ),
            }
        )

    return results


# ============================================================
# PUBLIC API — SUMMARY
# ============================================================


def get_summary(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
) -> dict[str, Any]:
    """
    Get aggregate customer intelligence summary.
    """
    metrics = get_customer_metrics(
        db, organization_id, store_id
    )

    total = len(metrics)

    segment_counts: dict[str, int] = {
        SEGMENT_NEW: 0,
        SEGMENT_INTERESTED: 0,
        SEGMENT_HIGH_INTENT: 0,
        SEGMENT_BUYER: 0,
        SEGMENT_REPEAT_BUYER: 0,
        SEGMENT_VIP: 0,
        SEGMENT_INACTIVE: 0,
    }

    at_risk_count = 0

    for m in metrics:
        seg = m["primary_segment"]
        if seg in segment_counts:
            segment_counts[seg] += 1
        if FLAG_AT_RISK in m["flags"]:
            at_risk_count += 1

    return {
        "total_customers": total,
        "new_customers": segment_counts[SEGMENT_NEW],
        "interested": segment_counts[SEGMENT_INTERESTED],
        "high_intent": segment_counts[
            SEGMENT_HIGH_INTENT
        ],
        "buyers": segment_counts[SEGMENT_BUYER],
        "repeat_buyers": segment_counts[
            SEGMENT_REPEAT_BUYER
        ],
        "vip": segment_counts[SEGMENT_VIP],
        "at_risk": at_risk_count,
        "inactive": segment_counts[SEGMENT_INACTIVE],
    }


# ============================================================
# PUBLIC API — FILTERED LIST
# ============================================================


def get_customer_list(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
    segment: str | None = None,
    flag: str | None = None,
    search: str | None = None,
    has_orders: bool | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "last_interaction_desc",
) -> dict[str, Any]:
    """
    Get paginated, filtered, sorted customer list.
    """
    metrics = get_customer_metrics(
        db, organization_id, store_id
    )

    # Filter by segment
    if segment:
        metrics = [
            m for m in metrics if m["primary_segment"] == segment
        ]

    # Filter by flag
    if flag:
        metrics = [
            m for m in metrics if flag in m["flags"]
        ]

    # Filter by search
    if search:
        search_lower = search.lower()
        metrics = [
            m
            for m in metrics
            if search_lower in (m["name"] or "").lower()
            or search_lower in (m["phone"] or "").lower()
            or search_lower in (m["email"] or "").lower()
        ]

    # Filter by has_orders
    if has_orders is not None:
        if has_orders:
            metrics = [
                m
                for m in metrics
                if m["successful_order_count"] > 0
            ]
        else:
            metrics = [
                m
                for m in metrics
                if m["successful_order_count"] == 0
            ]

    # Sort
    reverse = True
    sort_key = "last_interaction_at"

    if sort == "last_interaction_desc":
        sort_key = "last_interaction_at"
        reverse = True
    elif sort == "last_interaction_asc":
        sort_key = "last_interaction_at"
        reverse = False
    elif sort == "last_purchase_desc":
        sort_key = "last_order_at"
        reverse = True
    elif sort == "order_count_desc":
        sort_key = "successful_order_count"
        reverse = True
    elif sort == "created_desc":
        sort_key = "created_at"
        reverse = True
    elif sort == "name_asc":
        sort_key = "name"
        reverse = False

    def _sort_val(m: dict) -> Any:
        v = m.get(sort_key)
        if v is None:
            return "" if isinstance(
                m.get("name"), str
            ) else (datetime.min if "at" in sort_key else 0)
        return v

    metrics.sort(key=_sort_val, reverse=reverse)

    total = len(metrics)
    total_pages = max(
        1, (total + page_size - 1) // page_size
    )
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    page_items = metrics[start:end]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ============================================================
# PUBLIC API — CUSTOMER DETAIL
# ============================================================


def get_customer_detail(
    db: Session,
    organization_id: int,
    customer_id: int,
    store_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Get detailed metrics for a single customer.
    """
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id == organization_id,
        )
        .first()
    )

    if not customer:
        return None

    # Get metrics for this customer
    metrics = get_customer_metrics(
        db, organization_id, store_id
    )

    customer_metric = next(
        (m for m in metrics if m["id"] == customer_id),
        None,
    )

    if not customer_metric:
        return None

    # Recent conversations (last 5)
    conv_q = (
        db.query(Conversation)
        .filter(
            Conversation.customer_id == customer_id,
            Conversation.organization_id
            == organization_id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(5)
    )

    if store_id is not None:
        conv_q = conv_q.filter(
            Conversation.store_id == store_id
        )

    recent_conversations = []
    for conv in conv_q.all():
        recent_conversations.append(
            {
                "id": conv.id,
                "channel": conv.channel,
                "mode": conv.mode,
                "preview": (conv.preview or "")[:200],
                "updated_at": (
                    conv.updated_at.isoformat()
                    if conv.updated_at
                    else None
                ),
            }
        )

    # Recent orders (last 5)
    order_q = (
        db.query(Order)
        .filter(
            Order.customer_id == customer_id,
            Order.organization_id == organization_id,
        )
        .order_by(Order.created_at.desc())
        .limit(5)
    )

    if store_id is not None:
        order_q = order_q.filter(
            Order.store_id == store_id
        )

    recent_orders = []
    for order in order_q.all():
        recent_orders.append(
            {
                "id": order.id,
                "order_number": order.order_number,
                "total_amount": float(
                    order.total_amount
                ),
                "currency": order.currency,
                "external_creation_status": order.external_creation_status,
                "financial_status": order.financial_status,
                "created_at": (
                    order.created_at.isoformat()
                    if order.created_at
                    else None
                ),
            }
        )

    # Merge detail with metrics
    detail = {**customer_metric}
    detail["recent_conversations"] = recent_conversations
    detail["recent_orders"] = recent_orders

    return detail
