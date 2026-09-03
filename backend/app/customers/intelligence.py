"""
Customer Intelligence service for Diaglob.

Phase 1: Deterministic segmentation based on real data.
Phase 2: Score, priority, health, opportunities, risks,
         next best action, timeline, failed/unknown order signals.

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
# CONFIGURATION — SEGMENTATION THRESHOLDS (Phase 1)
# ============================================================

NEW_CUSTOMER_DAYS = 14
INTERESTED_MIN_CONVERSATIONS = 2
HIGH_INTENT_RECENCY_DAYS = 7
INACTIVE_DAYS = 60
AT_RISK_DAYS = 30
VIP_MIN_ORDERS = 5

VALID_ORDER_STATUSES = ("created",)
FAILED_ORDER_STATUSES = ("failed", "unknown")


# ============================================================
# CONFIGURATION — SCORE THRESHOLDS (Phase 2)
# ============================================================

SCORE_RECENCY_VERY_RECENT = 7
SCORE_RECENCY_RECENT = 30
SCORE_RECENCY_STALE = 90

SCORE_ENGAGEMENT_MAX = 30
SCORE_COMMERCE_MAX = 35
SCORE_RECENCY_MAX = 25
SCORE_LOYALTY_MAX = 10

HIGH_PRIORITY_SCORE_THRESHOLD = 70
LOW_PRIORITY_SCORE_THRESHOLD = 30


# ============================================================
# SEGMENT ENUM (string constants) — Phase 1
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
# PRIORITY / HEALTH / ACTION CONSTANTS (Phase 2)
# ============================================================

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

HEALTH_ACTIVE = "active"
HEALTH_AT_RISK = "at_risk"
HEALTH_INACTIVE = "inactive"

ACTION_FOLLOW_UP = "follow_up_conversation"
ACTION_RECOVER_FAILED = "recover_failed_order"
ACTION_REENGAGE = "reengage_customer"
ACTION_REVIEW_VIP = "review_vip"
ACTION_NO_ACTION = "no_action_needed"


# ============================================================
# HELPERS
# ============================================================


def _days_since(
    dt: datetime | None, now: datetime
) -> int | None:
    if dt is None:
        return None
    delta = now - dt
    return max(0, delta.days)


def _clamp(
    value: float, min_val: float, max_val: float
) -> float:
    return max(min_val, min(max_val, value))


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
    Deterministic classification (Phase 1).
    Returns (primary_segment, flags).
    """
    flags: list[str] = []
    customer_age_days = (
        _days_since(created_at, now) or 0
    )
    days_since_purchase = _days_since(
        last_order_at, now
    )
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
        days_since_interaction is not None
        and days_since_interaction >= INACTIVE_DAYS
    ):
        primary = SEGMENT_INACTIVE
    elif (
        days_since_interaction is not None
        and days_since_interaction
        <= HIGH_INTENT_RECENCY_DAYS
    ):
        primary = SEGMENT_HIGH_INTENT
    elif (
        conversation_count
        >= INTERESTED_MIN_CONVERSATIONS
    ):
        primary = SEGMENT_INTERESTED
    elif customer_age_days <= NEW_CUSTOMER_DAYS:
        primary = SEGMENT_NEW
    else:
        primary = SEGMENT_NEW

    # AT_RISK flag
    if (
        successful_order_count >= 1
        and days_since_purchase is not None
        and days_since_purchase >= AT_RISK_DAYS
    ):
        flags.append(FLAG_AT_RISK)

    if (
        successful_order_count >= 1
        and days_since_interaction is not None
        and days_since_interaction >= AT_RISK_DAYS
        and days_since_purchase is not None
        and days_since_purchase >= AT_RISK_DAYS
        and FLAG_AT_RISK not in flags
    ):
        flags.append(FLAG_AT_RISK)

    return primary, flags


# ============================================================
# PHASE 2 — SCORE CALCULATION
# ============================================================


def _calculate_score(
    *,
    now: datetime,
    created_at: datetime,
    conversation_count: int,
    message_count: int,
    last_interaction_at: datetime | None,
    successful_order_count: int,
    last_order_at: datetime | None,
    failed_order_count: int,
    unknown_order_count: int,
) -> tuple[int, list[dict[str, Any]]]:
    """
    Calculate customer score (0-100) with explanation.

    Components:
      ENGAGEMENT (0-30): conversation recency + message volume
      COMMERCE   (0-35): order count + repeat/VIP bonus
      RECENCY    (0-25): recency of last interaction/purchase
      LOYALTY    (0-10): account age + multiple orders

    Returns (score, score_factors).
    """
    factors: list[dict[str, Any]] = []
    total = 0.0

    days_since_interaction = _days_since(
        last_interaction_at, now
    )
    days_since_purchase = _days_since(
        last_order_at, now
    )
    customer_age_days = (
        _days_since(created_at, now) or 0
    )

    # --- ENGAGEMENT (0-30) ---
    engagement = 0.0

    if (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_VERY_RECENT
    ):
        engagement += 15
        factors.append(
            {
                "code": "recent_interaction",
                "impact": 15,
            }
        )
    elif (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_RECENT
    ):
        engagement += 10
        factors.append(
            {
                "code": "moderate_interaction",
                "impact": 10,
            }
        )
    elif (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_STALE
    ):
        engagement += 5
        factors.append(
            {
                "code": "stale_interaction",
                "impact": 5,
            }
        )

    if conversation_count >= 3:
        engagement += 8
        factors.append(
            {
                "code": "multiple_conversations",
                "impact": 8,
            }
        )
    elif conversation_count >= 1:
        engagement += 4
        factors.append(
            {
                "code": "has_conversations",
                "impact": 4,
            }
        )

    if message_count >= 10:
        engagement += 7
        factors.append(
            {
                "code": "high_message_volume",
                "impact": 7,
            }
        )
    elif message_count >= 3:
        engagement += 3
        factors.append(
            {
                "code": "moderate_message_volume",
                "impact": 3,
            }
        )

    engagement = min(
        engagement, SCORE_ENGAGEMENT_MAX
    )
    total += engagement

    # --- COMMERCE (0-35) ---
    commerce = 0.0

    if successful_order_count >= VIP_MIN_ORDERS:
        commerce += 25
        factors.append(
            {
                "code": "vip_customer",
                "impact": 25,
            }
        )
    elif successful_order_count >= 2:
        commerce += 18
        factors.append(
            {
                "code": "repeat_customer",
                "impact": 18,
            }
        )
    elif successful_order_count >= 1:
        commerce += 10
        factors.append(
            {
                "code": "has_orders",
                "impact": 10,
            }
        )

    if (
        days_since_purchase is not None
        and days_since_purchase <= SCORE_RECENCY_VERY_RECENT
    ):
        commerce += 10
        factors.append(
            {
                "code": "recent_purchase",
                "impact": 10,
            }
        )
    elif (
        days_since_purchase is not None
        and days_since_purchase <= SCORE_RECENCY_RECENT
    ):
        commerce += 5
        factors.append(
            {
                "code": "moderate_purchase_recency",
                "impact": 5,
            }
        )

    commerce = min(commerce, SCORE_COMMERCE_MAX)
    total += commerce

    # --- RECENCY (0-25) ---
    recency = 0.0

    if (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_VERY_RECENT
    ):
        recency += 15
        factors.append(
            {
                "code": "recent_interaction",
                "impact": 15,
            }
        )
    elif (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_RECENT
    ):
        recency += 10
        factors.append(
            {
                "code": "moderately_recent_interaction",
                "impact": 10,
            }
        )
    elif (
        days_since_interaction is not None
        and days_since_interaction
        <= SCORE_RECENCY_STALE
    ):
        recency += 5
        factors.append(
            {
                "code": "stale_interaction_recency",
                "impact": 5,
            }
        )

    if (
        days_since_purchase is not None
        and days_since_purchase <= SCORE_RECENCY_RECENT
    ):
        recency += 10
        factors.append(
            {
                "code": "recent_purchase_recency",
                "impact": 10,
            }
        )
    elif (
        days_since_purchase is not None
        and days_since_purchase <= SCORE_RECENCY_STALE
    ):
        recency += 5
        factors.append(
            {
                "code": "moderate_purchase_recency",
                "impact": 5,
            }
        )

    recency = min(recency, SCORE_RECENCY_MAX)
    total += recency

    # --- LOYALTY (0-10) ---
    loyalty = 0.0

    if customer_age_days >= 180:
        loyalty += 5
        factors.append(
            {
                "code": "long_term_customer",
                "impact": 5,
            }
        )
    elif customer_age_days >= 60:
        loyalty += 3
        factors.append(
            {
                "code": "established_customer",
                "impact": 3,
            }
        )

    if successful_order_count >= 3:
        loyalty += 5
        factors.append(
            {
                "code": "high_order_frequency",
                "impact": 5,
            }
        )
    elif successful_order_count >= 2:
        loyalty += 3
        factors.append(
            {
                "code": "repeat_buyer_loyalty",
                "impact": 3,
            }
        )

    loyalty = min(loyalty, SCORE_LOYALTY_MAX)
    total += loyalty

    final_score = int(
        _clamp(round(total), 0, 100)
    )
    return final_score, factors


# ============================================================
# PHASE 2 — PRIORITY CALCULATION
# ============================================================


def _calculate_priority(
    *,
    customer_score: int,
    primary_segment: str,
    flags: list[str],
    failed_order_count: int,
    unknown_order_count: int,
    days_since_last_interaction: int | None,
    days_since_last_purchase: int | None,
    last_failed_order_days: int | None,
    last_unknown_order_days: int | None,
) -> tuple[str, list[str]]:
    """
    Calculate customer priority.

    Returns (priority, priority_reasons).
    """
    reasons: list[str] = []

    is_at_risk = FLAG_AT_RISK in flags
    is_vip = primary_segment == SEGMENT_VIP
    is_buyer = primary_segment in (
        SEGMENT_BUYER,
        SEGMENT_REPEAT_BUYER,
        SEGMENT_VIP,
    )
    is_inactive = primary_segment == SEGMENT_INACTIVE
    is_high_intent = (
        primary_segment == SEGMENT_HIGH_INTENT
    )

    # HIGH priority triggers
    if is_at_risk:
        reasons.append("at_risk")

    if failed_order_count > 0 and (
        last_failed_order_days is not None
        and last_failed_order_days <= 30
    ):
        reasons.append("recent_failed_order")

    if unknown_order_count > 0 and (
        last_unknown_order_days is not None
        and last_unknown_order_days <= 30
    ):
        reasons.append("recent_unknown_order")

    if is_vip and is_at_risk:
        reasons.append("vip_at_risk")

    if (
        is_high_intent
        and customer_score >= HIGH_PRIORITY_SCORE_THRESHOLD
    ):
        reasons.append("high_intent_strong_signal")

    if (
        is_buyer
        and failed_order_count > 0
        and (last_failed_order_days is not None
             and last_failed_order_days <= 14)
    ):
        reasons.append("buyer_failed_order_recent")

    has_high_reasons = any(
        r in reasons
        for r in (
            "at_risk",
            "recent_failed_order",
            "recent_unknown_order",
            "vip_at_risk",
            "buyer_failed_order_recent",
        )
    )

    if has_high_reasons:
        return PRIORITY_HIGH, reasons

    # MEDIUM priority triggers
    if is_high_intent:
        reasons.append("recent_high_intent")

    if is_buyer and not is_at_risk:
        reasons.append("active_buyer")

    if (
        customer_score >= HIGH_PRIORITY_SCORE_THRESHOLD
        and not has_high_reasons
    ):
        reasons.append("high_engagement_score")

    if reasons:
        return PRIORITY_MEDIUM, reasons

    # LOW priority
    if is_inactive:
        reasons.append("inactive_customer")

    if (
        customer_score <= LOW_PRIORITY_SCORE_THRESHOLD
    ):
        reasons.append("low_engagement_score")

    if not reasons:
        reasons.append("no_priority_signal")

    return PRIORITY_LOW, reasons


# ============================================================
# PHASE 2 — HEALTH CALCULATION
# ============================================================


def _calculate_health(
    *,
    primary_segment: str,
    flags: list[str],
    days_since_last_interaction: int | None,
    days_since_last_purchase: int | None,
) -> str:
    """
    Calculate customer health state.
    """
    if FLAG_AT_RISK in flags:
        return HEALTH_AT_RISK

    if primary_segment == SEGMENT_INACTIVE:
        return HEALTH_INACTIVE

    is_buyer = primary_segment in (
        SEGMENT_BUYER,
        SEGMENT_REPEAT_BUYER,
        SEGMENT_VIP,
    )

    if is_buyer:
        if (
            days_since_last_purchase is not None
            and days_since_last_purchase <= AT_RISK_DAYS
        ):
            return HEALTH_ACTIVE
        if (
            days_since_last_interaction is not None
            and days_since_last_interaction
            <= SCORE_RECENCY_RECENT
        ):
            return HEALTH_ACTIVE
        return HEALTH_AT_RISK

    # Leads (new, interested, high_intent)
    if (
        days_since_last_interaction is not None
        and days_since_last_interaction
        <= AT_RISK_DAYS
    ):
        return HEALTH_ACTIVE

    if (
        days_since_last_interaction is not None
        and days_since_last_interaction < INACTIVE_DAYS
        and days_since_last_interaction > AT_RISK_DAYS
    ):
        return HEALTH_AT_RISK

    if (
        days_since_last_interaction is not None
        and days_since_last_interaction >= INACTIVE_DAYS
    ):
        return HEALTH_INACTIVE

    # Leads with no interaction history
    if days_since_last_interaction is None:
        return HEALTH_ACTIVE

    return HEALTH_ACTIVE


# ============================================================
# PHASE 2 — OPPORTUNITIES
# ============================================================


def _calculate_opportunities(
    *,
    primary_segment: str,
    flags: list[str],
    customer_score: int,
    failed_order_count: int,
    unknown_order_count: int,
    days_since_last_interaction: int | None,
    days_since_last_purchase: int | None,
    successful_order_count: int,
) -> list[str]:
    """
    Detect real commercial opportunities.
    Only evidence-backed signals.
    """
    opps: list[str] = []

    is_vip = primary_segment == SEGMENT_VIP
    is_buyer = primary_segment in (
        SEGMENT_BUYER,
        SEGMENT_REPEAT_BUYER,
        SEGMENT_VIP,
    )
    is_high_intent = (
        primary_segment == SEGMENT_HIGH_INTENT
    )

    if (
        is_high_intent
        and days_since_last_interaction is not None
        and days_since_last_interaction <= 7
    ):
        opps.append("high_intent_no_order")

    if (
        is_buyer
        and successful_order_count >= 2
    ):
        opps.append("repeat_customer")

    if is_vip:
        opps.append("vip_customer")

    if (
        failed_order_count > 0
        and days_since_last_purchase is not None
        and days_since_last_purchase <= 30
    ):
        opps.append("recent_failed_order_recovery")

    if (
        days_since_last_interaction is not None
        and days_since_last_interaction <= 7
        and days_since_last_purchase is not None
        and days_since_last_purchase > 30
    ):
        opps.append("recent_reengagement")

    if (
        days_since_last_interaction is not None
        and days_since_last_interaction <= 7
        and successful_order_count == 0
    ):
        opps.append("recent_conversation_no_order")

    return opps


# ============================================================
# PHASE 2 — RISKS
# ============================================================


def _calculate_risks(
    *,
    primary_segment: str,
    flags: list[str],
    days_since_last_interaction: int | None,
    days_since_last_purchase: int | None,
    failed_order_count: int,
    unknown_order_count: int,
    customer_age_days: int,
) -> list[str]:
    """
    Detect real risks.
    Only evidence-backed signals.
    """
    risks: list[str] = []

    if FLAG_AT_RISK in flags:
        risks.append("at_risk")

    if primary_segment == SEGMENT_INACTIVE:
        risks.append("inactive")

    if failed_order_count > 0:
        risks.append("failed_order")

    if unknown_order_count > 0:
        risks.append("unknown_order")

    if (
        days_since_last_purchase is not None
        and days_since_last_purchase >= 60
    ):
        risks.append("long_time_since_purchase")

    if (
        days_since_last_interaction is not None
        and days_since_last_interaction >= 60
    ):
        risks.append("long_time_since_interaction")

    if (
        days_since_last_interaction is None
        and days_since_last_purchase is None
        and customer_age_days >= 30
    ):
        risks.append("no_engagement_history")

    return risks


# ============================================================
# PHASE 2 — NEXT BEST ACTION
# ============================================================


def _calculate_next_best_action(
    *,
    primary_segment: str,
    flags: list[str],
    customer_score: int,
    failed_order_count: int,
    unknown_order_count: int,
    last_failed_order_days: int | None,
    days_since_last_interaction: int | None,
    health: str,
    priority: str,
) -> tuple[str, list[str]]:
    """
    Determine next best action.
    Deterministic, no automation.
    Returns (action, action_reasons).
    """
    reasons: list[str] = []
    is_at_risk = FLAG_AT_RISK in flags
    is_vip = primary_segment == SEGMENT_VIP

    # Priority 1: recover failed order
    if (
        failed_order_count > 0
        and last_failed_order_days is not None
        and last_failed_order_days <= 30
    ):
        reasons.append("order_failed_recently")
        return ACTION_RECOVER_FAILED, reasons

    # Priority 2: review VIP at risk
    if is_vip and is_at_risk:
        reasons.append("vip_customer_at_risk")
        return ACTION_REVIEW_VIP, reasons

    # Priority 3: re-engage at-risk customer
    if is_at_risk:
        reasons.append("customer_at_risk")
        return ACTION_REENGAGE, reasons

    # Priority 4: follow up high-intent
    if (
        primary_segment == SEGMENT_HIGH_INTENT
        and days_since_last_interaction is not None
        and days_since_last_interaction <= 7
    ):
        reasons.append("recent_high_intent_conversation")
        return ACTION_FOLLOW_UP, reasons

    # Priority 5: re-engage stale buyer
    if (
        primary_segment
        in (SEGMENT_BUYER, SEGMENT_REPEAT_BUYER)
        and days_since_last_interaction is not None
        and days_since_last_interaction >= INACTIVE_DAYS
    ):
        reasons.append("buyer_becoming_inactive")
        return ACTION_REENGAGE, reasons

    # Priority 6: re-engage inactive
    if primary_segment == SEGMENT_INACTIVE:
        reasons.append("customer_inactive")
        return ACTION_REENGAGE, reasons

    # Priority 7: re-engage no-engagement history
    if (
        days_since_last_interaction is None
        and primary_segment == SEGMENT_NEW
    ):
        reasons.append("new_customer_no_engagement")
        return ACTION_REENGAGE, reasons

    return ACTION_NO_ACTION, reasons


# ============================================================
# PHASE 2 — TIMELINE
# ============================================================


def _build_timeline(
    db: Session,
    customer_id: int,
    organization_id: int,
    store_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Build activity timeline from real events.
    Sources: customer creation, conversations, orders.
    Returns up to 30 events, most recent first.
    No N+1 — uses bounded queries.
    """
    events: list[dict[str, Any]] = []

    # Customer created event
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id
            == organization_id,
        )
        .first()
    )

    if customer:
        events.append(
            {
                "type": "customer_created",
                "timestamp": (
                    customer.created_at.isoformat()
                    if customer.created_at
                    else None
                ),
                "customer_id": customer.id,
            }
        )

    # Conversation events (bounded query)
    conv_q = (
        db.query(Conversation)
        .filter(
            Conversation.customer_id == customer_id,
            Conversation.organization_id
            == organization_id,
        )
        .order_by(
            Conversation.created_at.desc()
        )
        .limit(15)
    )

    if store_id is not None:
        conv_q = conv_q.filter(
            Conversation.store_id == store_id
        )

    for conv in conv_q.all():
        events.append(
            {
                "type": "conversation",
                "timestamp": (
                    conv.created_at.isoformat()
                    if conv.created_at
                    else None
                ),
                "conversation_id": conv.id,
                "channel": conv.channel,
                "preview": (
                    (conv.preview or "")[:120]
                ),
            }
        )

    # Order events (bounded query)
    order_q = (
        db.query(Order)
        .filter(
            Order.customer_id == customer_id,
            Order.organization_id == organization_id,
        )
        .order_by(Order.created_at.desc())
        .limit(15)
    )

    if store_id is not None:
        order_q = order_q.filter(
            Order.store_id == store_id
        )

    for order in order_q.all():
        status = order.external_creation_status
        if status == "failed":
            event_type = "order_status_failed"
        elif status == "unknown":
            event_type = "order_status_unknown"
        elif status == "created":
            event_type = "order_created"
        else:
            event_type = "order_pending"

        events.append(
            {
                "type": event_type,
                "timestamp": (
                    order.created_at.isoformat()
                    if order.created_at
                    else None
                ),
                "order_id": order.id,
                "order_number": order.order_number,
                "total_amount": float(
                    order.total_amount
                ),
                "currency": order.currency,
            }
        )

    # Sort by timestamp descending, most recent first
    def _ts_sort(e: dict) -> str:
        return e.get("timestamp") or ""

    events.sort(key=_ts_sort, reverse=True)

    # Deduplicate and limit
    seen = set()
    unique_events: list[dict[str, Any]] = []
    for ev in events:
        key = (
            ev["type"],
            ev.get("timestamp", ""),
            ev.get("conversation_id")
            or ev.get("order_id")
            or ev.get("customer_id", 0),
        )
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)
        if len(unique_events) >= 30:
            break

    return unique_events


# ============================================================
# PHASE 2 — FAILED/UNKNOWN ORDER SIGNALS
# ============================================================


def _get_failed_unknown_signals(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """
    Get failed/unknown order signals per customer.
    Returns dict keyed by customer_id.
    Uses batched query to avoid N+1.
    """
    q = (
        db.query(
            Order.customer_id,
            func.count(Order.id).label(
                "total_failed"
            ),
            func.max(Order.created_at).label(
                "last_failed_at"
            ),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.customer_id.isnot(None),
            Order.external_creation_status.in_(
                FAILED_ORDER_STATUSES
            ),
        )
        .group_by(Order.customer_id)
    )

    if store_id is not None:
        q = q.filter(Order.store_id == store_id)

    result: dict[int, dict[str, Any]] = {}
    now = datetime.utcnow()

    for row in q.all():
        customer_id = row.customer_id
        last_failed_days = _days_since(
            row.last_failed_at, now
        )
        # Split into failed vs unknown counts
        failed_count_q = (
            db.query(func.count(Order.id))
            .filter(
                Order.organization_id
                == organization_id,
                Order.customer_id == customer_id,
                Order.external_creation_status
                == "failed",
            )
        )
        unknown_count_q = (
            db.query(func.count(Order.id))
            .filter(
                Order.organization_id
                == organization_id,
                Order.customer_id == customer_id,
                Order.external_creation_status
                == "unknown",
            )
        )

        if store_id is not None:
            failed_count_q = failed_count_q.filter(
                Order.store_id == store_id
            )
            unknown_count_q = unknown_count_q.filter(
                Order.store_id == store_id
            )

        failed_count = failed_count_q.scalar() or 0
        unknown_count = unknown_count_q.scalar() or 0

        # Recalculate last failed days per status
        last_failed_at = (
            db.query(func.max(Order.created_at))
            .filter(
                Order.organization_id
                == organization_id,
                Order.customer_id == customer_id,
                Order.external_creation_status
                == "failed",
            )
            .scalar()
        )
        last_unknown_at = (
            db.query(func.max(Order.created_at))
            .filter(
                Order.organization_id
                == organization_id,
                Order.customer_id == customer_id,
                Order.external_creation_status
                == "unknown",
            )
            .scalar()
        )

        result[customer_id] = {
            "failed_order_count": failed_count,
            "unknown_order_count": unknown_count,
            "last_failed_order_days": _days_since(
                last_failed_at, now
            ),
            "last_unknown_order_days": _days_since(
                last_unknown_at, now
            ),
        }

    return result


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

    # --- Message count per customer ---
    msg_conv = (
        db.query(
            Conversation.customer_id,
            func.count(Message.id).label(
                "message_count"
            ),
        )
        .join(
            Message,
            Message.conversation_id
            == Conversation.id,
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

    # --- Order aggregates (successful only) ---
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

    # --- Spend by currency ---
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
    Phase 2: includes score, priority, health,
    opportunities, risks, next_best_action.
    """
    now = datetime.utcnow()

    conv_agg, msg_agg, order_agg, spend_agg = (
        _build_customer_metrics_subquery(
            db, organization_id, store_id
        )
    )

    # Base customer query
    q = (
        db.query(
            Customer,
            func.coalesce(
                conv_agg.c.conversation_count, 0
            ).label("conversation_count"),
            conv_agg.c.last_interaction_at,
            conv_agg.c.first_interaction_at,
            func.coalesce(
                msg_agg.c.message_count, 0
            ).label("message_count"),
            func.coalesce(
                order_agg.c.successful_order_count,
                0,
            ).label("successful_order_count"),
            order_agg.c.last_order_at,
        )
        .outerjoin(
            conv_agg,
            conv_agg.c.customer_id == Customer.id,
        )
        .outerjoin(
            msg_agg,
            msg_agg.c.customer_id == Customer.id,
        )
        .outerjoin(
            order_agg,
            order_agg.c.customer_id == Customer.id,
        )
        .filter(
            Customer.organization_id
            == organization_id,
        )
    )

    if store_id is not None:
        q = q.join(
            CustomerStoreProfile,
            and_(
                CustomerStoreProfile.customer_id
                == Customer.id,
                CustomerStoreProfile.store_id
                == store_id,
            ),
        )

    rows = q.all()

    # Pre-fetch spend
    customer_ids = [r[0].id for r in rows]

    spend_by_customer: dict[int, dict] = {}
    if customer_ids:
        spend_rows = (
            db.query(
                spend_agg.c.customer_id,
                spend_agg.c.currency,
                spend_agg.c.total_spend,
                spend_agg.c.avg_order_value,
            )
            .filter(
                spend_agg.c.customer_id.in_(
                    customer_ids
                )
            )
            .all()
        )
        for sr in spend_rows:
            cid = sr.customer_id
            if cid not in spend_by_customer:
                spend_by_customer[cid] = {}
            spend_by_customer[cid][sr.currency] = {
                "total": float(sr.total_spend),
                "avg_order_value": float(
                    sr.avg_order_value
                ),
            }

    # Pre-fetch failed/unknown order signals
    fu_signals = _get_failed_unknown_signals(
        db, organization_id, store_id
    )

    # Pre-fetch store name
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

    results = []

    for (
        cust,
        conversation_count,
        last_interaction_at,
        first_interaction_at,
        message_count,
        successful_order_count,
        last_order_at,
    ) in rows:
        primary_segment, flags = _classify_customer(
            now=now,
            created_at=cust.created_at,
            conversation_count=conversation_count,
            last_interaction_at=last_interaction_at,
            successful_order_count=(
                successful_order_count
            ),
            last_order_at=last_order_at,
        )

        days_since_last_interaction = _days_since(
            last_interaction_at, now
        )
        days_since_last_purchase = _days_since(
            last_order_at, now
        )

        sig = fu_signals.get(cust.id, {})
        failed_order_count = sig.get(
            "failed_order_count", 0
        )
        unknown_order_count = sig.get(
            "unknown_order_count", 0
        )
        last_failed_order_days = sig.get(
            "last_failed_order_days"
        )
        last_unknown_order_days = sig.get(
            "last_unknown_order_days"
        )

        customer_age_days = (
            _days_since(cust.created_at, now) or 0
        )

        # Phase 2: Score
        customer_score, score_factors = (
            _calculate_score(
                now=now,
                created_at=cust.created_at,
                conversation_count=conversation_count,
                message_count=message_count,
                last_interaction_at=last_interaction_at,
                successful_order_count=(
                    successful_order_count
                ),
                last_order_at=last_order_at,
                failed_order_count=failed_order_count,
                unknown_order_count=unknown_order_count,
            )
        )

        # Phase 2: Health
        health = _calculate_health(
            primary_segment=primary_segment,
            flags=flags,
            days_since_last_interaction=(
                days_since_last_interaction
            ),
            days_since_last_purchase=(
                days_since_last_purchase
            ),
        )

        # Phase 2: Priority
        priority, priority_reasons = (
            _calculate_priority(
                customer_score=customer_score,
                primary_segment=primary_segment,
                flags=flags,
                failed_order_count=failed_order_count,
                unknown_order_count=unknown_order_count,
                days_since_last_interaction=(
                    days_since_last_interaction
                ),
                days_since_last_purchase=(
                    days_since_last_purchase
                ),
                last_failed_order_days=(
                    last_failed_order_days
                ),
                last_unknown_order_days=(
                    last_unknown_order_days
                ),
            )
        )

        # Phase 2: Opportunities
        opportunities = _calculate_opportunities(
            primary_segment=primary_segment,
            flags=flags,
            customer_score=customer_score,
            failed_order_count=failed_order_count,
            unknown_order_count=unknown_order_count,
            days_since_last_interaction=(
                days_since_last_interaction
            ),
            days_since_last_purchase=(
                days_since_last_purchase
            ),
            successful_order_count=(
                successful_order_count
            ),
        )

        # Phase 2: Risks
        risks = _calculate_risks(
            primary_segment=primary_segment,
            flags=flags,
            days_since_last_interaction=(
                days_since_last_interaction
            ),
            days_since_last_purchase=(
                days_since_last_purchase
            ),
            failed_order_count=failed_order_count,
            unknown_order_count=unknown_order_count,
            customer_age_days=customer_age_days,
        )

        # Phase 2: Next Best Action
        action, action_reasons = (
            _calculate_next_best_action(
                primary_segment=primary_segment,
                flags=flags,
                customer_score=customer_score,
                failed_order_count=failed_order_count,
                unknown_order_count=unknown_order_count,
                last_failed_order_days=(
                    last_failed_order_days
                ),
                days_since_last_interaction=(
                    days_since_last_interaction
                ),
                health=health,
                priority=priority,
            )
        )

        # Phase 2: needs_attention
        # Urgent / higher-value intervention
        needs_attention = False
        if priority == PRIORITY_HIGH:
            needs_attention = True
        elif (
            priority == PRIORITY_MEDIUM
            and action in (
                ACTION_RECOVER_FAILED,
                ACTION_FOLLOW_UP,
            )
        ):
            needs_attention = True
        elif (
            action == ACTION_REENGAGE
            and primary_segment in (
                SEGMENT_BUYER,
                SEGMENT_REPEAT_BUYER,
                SEGMENT_VIP,
            )
        ):
            needs_attention = True

        results.append(
            {
                "id": cust.id,
                "name": cust.name,
                "phone": cust.phone,
                "email": cust.email,
                "country_code": cust.country_code,
                "created_at": (
                    cust.created_at.isoformat()
                ),
                "store_name": store_name,
                "store_id": store_id_val,
                "conversation_count": (
                    conversation_count
                ),
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
                "successful_order_count": (
                    successful_order_count
                ),
                "last_order_at": (
                    last_order_at.isoformat()
                    if last_order_at
                    else None
                ),
                "spend_by_currency": (
                    spend_by_customer.get(cust.id, {})
                ),
                "primary_segment": primary_segment,
                "flags": flags,
                "days_since_last_interaction": (
                    days_since_last_interaction
                ),
                "days_since_last_purchase": (
                    days_since_last_purchase
                ),
                # Phase 2 fields
                "customer_score": customer_score,
                "score_factors": score_factors,
                "priority": priority,
                "priority_reasons": priority_reasons,
                "customer_health": health,
                "opportunities": opportunities,
                "risks": risks,
                "next_best_action": action,
                "next_best_action_reasons": (
                    action_reasons
                ),
                "failed_order_count": (
                    failed_order_count
                ),
                "unknown_order_count": (
                    unknown_order_count
                ),
                "last_failed_order_days": (
                    last_failed_order_days
                ),
                "needs_attention": needs_attention,
            }
        )

    return results


# ============================================================
# PUBLIC API — SUMMARY (Phase 2)
# ============================================================


def get_summary(
    db: Session,
    organization_id: int,
    store_id: int | None = None,
) -> dict[str, Any]:
    """
    Get aggregate customer intelligence summary.
    Phase 2: includes priority/health/action counts.
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
    high_priority_count = 0
    needs_followup_count = 0
    active_count = 0
    at_risk_health_count = 0
    inactive_health_count = 0

    for m in metrics:
        seg = m["primary_segment"]
        if seg in segment_counts:
            segment_counts[seg] += 1
        if FLAG_AT_RISK in m["flags"]:
            at_risk_count += 1
        if m["priority"] == PRIORITY_HIGH:
            high_priority_count += 1
        if m["next_best_action"] != ACTION_NO_ACTION:
            needs_followup_count += 1
        if m["customer_health"] == HEALTH_ACTIVE:
            active_count += 1
        if m["customer_health"] == HEALTH_AT_RISK:
            at_risk_health_count += 1
        if m["customer_health"] == HEALTH_INACTIVE:
            inactive_health_count += 1

    return {
        "total_customers": total,
        "new_customers": segment_counts[SEGMENT_NEW],
        "interested": segment_counts[
            SEGMENT_INTERESTED
        ],
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
        # Phase 2
        "high_priority": high_priority_count,
        "needs_followup": needs_followup_count,
        "active_health": active_count,
        "at_risk_health": at_risk_health_count,
        "inactive_health": inactive_health_count,
    }


# ============================================================
# PUBLIC API — FILTERED LIST (Phase 2)
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
    # Phase 2 filters
    priority: str | None = None,
    health: str | None = None,
    needs_attention: bool | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    """
    Get paginated, filtered, sorted customer list.
    Phase 2: supports priority, health, needs_attention filters.
    """
    metrics = get_customer_metrics(
        db, organization_id, store_id
    )

    # Filter by segment
    if segment:
        metrics = [
            m
            for m in metrics
            if m["primary_segment"] == segment
        ]

    # Filter by flag
    if flag:
        metrics = [
            m
            for m in metrics
            if flag in m["flags"]
        ]

    # Filter by search
    if search:
        search_lower = search.lower()
        metrics = [
            m
            for m in metrics
            if search_lower
            in (m["name"] or "").lower()
            or search_lower
            in (m["phone"] or "").lower()
            or search_lower
            in (m["email"] or "").lower()
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

    # Phase 2: Filter by priority
    if priority:
        metrics = [
            m
            for m in metrics
            if m["priority"] == priority
        ]

    # Phase 2: Filter by health
    if health:
        metrics = [
            m
            for m in metrics
            if m["customer_health"] == health
        ]

    # Phase 2: Filter by needs_attention
    if needs_attention is not None:
        metrics = [
            m
            for m in metrics
            if m["needs_attention"] == needs_attention
        ]

    if country:
        metrics = [m for m in metrics if m.get("country_code") == country]

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
    elif sort == "score_desc":
        sort_key = "customer_score"
        reverse = True
    elif sort == "priority_desc":
        sort_key = "priority"
        reverse = True

    def _sort_val(m: dict) -> Any:
        if sort_key == "priority":
            order = {
                PRIORITY_HIGH: 3,
                PRIORITY_MEDIUM: 2,
                PRIORITY_LOW: 1,
            }
            return order.get(m.get(sort_key, ""), 0)
        v = m.get(sort_key)
        if v is None:
            if sort_key == "customer_score":
                return 0
            return (
                ""
                if isinstance(m.get("name"), str)
                else (
                    datetime.min
                    if "at" in sort_key
                    else 0
                )
            )
        return v

    metrics.sort(
        key=_sort_val, reverse=reverse
    )

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
# PUBLIC API — CUSTOMER DETAIL (Phase 2)
# ============================================================


def get_customer_detail(
    db: Session,
    organization_id: int,
    customer_id: int,
    store_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Get detailed metrics for a single customer.
    Phase 2: includes timeline.
    """
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id
            == organization_id,
        )
        .first()
    )

    if not customer:
        return None

    metrics = get_customer_metrics(
        db, organization_id, store_id
    )

    customer_metric = next(
        (
            m
            for m in metrics
            if m["id"] == customer_id
        ),
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
                "preview": (
                    (conv.preview or "")[:200]
                ),
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
            Order.organization_id
            == organization_id,
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
                "external_creation_status": (
                    order.external_creation_status
                ),
                "financial_status": (
                    order.financial_status
                ),
                "created_at": (
                    order.created_at.isoformat()
                    if order.created_at
                    else None
                ),
            }
        )

    # Phase 2: Timeline
    timeline = _build_timeline(
        db,
        customer_id,
        organization_id,
        store_id,
    )

    # Merge detail with metrics
    detail = {**customer_metric}
    detail["recent_conversations"] = (
        recent_conversations
    )
    detail["recent_orders"] = recent_orders
    detail["timeline"] = timeline

    return detail
