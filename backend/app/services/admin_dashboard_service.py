"""Admin dashboard service.

Provides aggregate platform metrics for internal founder/operator use.
Does NOT expose merchant data to other merchants.
Does NOT import FastAPI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Automation,
    Conversation,
    CommerceConnection,
    KnowledgeBase,
    Message,
    MetaAdsConnection,
    Order,
    Organization,
    OrganizationMembership,
    Store,
    User,
    WhatsAppConnection,
)
from ..plan_limits import PLAN_LIMITS, get_organization_limits

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def get_admin_overview(db: Session) -> dict:
    """Get platform-wide overview metrics."""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # Organizations
    total_orgs = db.query(func.count(Organization.id)).scalar() or 0

    # Users
    total_users = db.query(func.count(User.id)).scalar() or 0

    # Stores
    total_stores = (
        db.query(func.count(Store.id))
        .filter(Store.deleted.is_(False))
        .scalar() or 0
    )

    # Active stores
    active_stores = (
        db.query(func.count(Store.id))
        .filter(Store.deleted.is_(False), Store.active.is_(True))
        .scalar() or 0
    )

    # Plan distribution
    plan_distribution = {}
    for plan_name, limits in PLAN_LIMITS.items():
        count = (
            db.query(func.count(Organization.id))
            .filter(Organization.plan == plan_name)
            .scalar() or 0
        )
        plan_distribution[plan_name] = count

    # MRR (approximate from plan prices)
    PLAN_PRICES = {
        "starter": Decimal("19"),
        "growth": Decimal("49"),
        "pro": Decimal("99"),
        "scale": Decimal("199"),
    }

    mrr = ZERO
    for plan_name, price in PLAN_PRICES.items():
        count = plan_distribution.get(plan_name, 0)
        mrr += price * count

    arr = mrr * 12

    # Conversations
    total_conversations = db.query(func.count(Conversation.id)).scalar() or 0

    # Messages
    total_messages = db.query(func.count(Message.id)).scalar() or 0

    # AI messages
    ai_messages = (
        db.query(func.count(Message.id))
        .filter(Message.sender == "ai")
        .scalar() or 0
    )

    # Orders
    total_orders = db.query(func.count(Order.id)).scalar() or 0

    # Integrations
    shopify_connected = (
        db.query(func.count(CommerceConnection.id))
        .filter(CommerceConnection.provider == "shopify")
        .scalar() or 0
    )

    whatsapp_connected = (
        db.query(func.count(WhatsAppConnection.id))
        .filter(WhatsAppConnection.status == "connected")
        .scalar() or 0
    )

    meta_ads_connected = (
        db.query(func.count(MetaAdsConnection.id))
        .filter(MetaAdsConnection.status == "connected")
        .scalar() or 0
    )

    knowledge_bases = db.query(func.count(KnowledgeBase.id)).scalar() or 0

    automations = db.query(func.count(Automation.id)).scalar() or 0

    return {
        "organizations": {
            "total": total_orgs,
            "by_plan": plan_distribution,
        },
        "users": {"total": total_users},
        "stores": {
            "total": total_stores,
            "active": active_stores,
        },
        "revenue": {
            "mrr": str(mrr),
            "arr": str(arr),
            "currency": "USD",
        },
        "conversations": {
            "total": total_conversations,
            "total_messages": total_messages,
            "ai_messages": ai_messages,
        },
        "orders": {"total": total_orders},
        "integrations": {
            "shopify_connected": shopify_connected,
            "whatsapp_connected": whatsapp_connected,
            "meta_ads_connected": meta_ads_connected,
            "knowledge_bases": knowledge_bases,
        },
        "automations": {"total": automations},
    }


def get_organization_list(
    db: Session,
    page: int = 1,
    page_size: int = 25,
    plan_filter: str | None = None,
) -> dict:
    """List all organizations with summary metrics."""
    query = db.query(Organization)

    if plan_filter:
        query = query.filter(Organization.plan == plan_filter)

    total = query.count()

    orgs = (
        query.order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for org in orgs:
        limits = get_organization_limits(org)

        # Store count
        store_count = (
            db.query(func.count(Store.id))
            .filter(Store.organization_id == org.id, Store.deleted.is_(False))
            .scalar() or 0
        )

        # AI usage
        ai_used = (
            db.query(func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.organization_id == org.id,
                Message.sender == "ai",
            )
            .scalar() or 0
        )

        ai_included = limits.included_ai_responses
        ai_pct = (ai_used / ai_included * 100) if ai_included > 0 else 0

        if ai_pct >= 100:
            ai_status = "EXHAUSTED"
        elif ai_pct >= 95:
            ai_status = "WARNING_95"
        elif ai_pct >= 80:
            ai_status = "WARNING_80"
        else:
            ai_status = "NORMAL"

        # Integrations
        has_shopify = (
            db.query(CommerceConnection.id)
            .filter(
                CommerceConnection.organization_id == org.id,
                CommerceConnection.provider == "shopify",
            )
            .first()
            is not None
        )

        has_whatsapp = (
            db.query(WhatsAppConnection.id)
            .filter(
                WhatsAppConnection.organization_id == org.id,
                WhatsAppConnection.status == "connected",
            )
            .first()
            is not None
        )

        has_meta_ads = (
            db.query(MetaAdsConnection.id)
            .filter(
                MetaAdsConnection.organization_id == org.id,
                MetaAdsConnection.status == "connected",
            )
            .first()
            is not None
        )

        # Plan price
        PLAN_PRICES = {
            "starter": 19,
            "growth": 49,
            "pro": 99,
            "scale": 199,
        }

        items.append({
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan or "none",
            "plan_price": PLAN_PRICES.get(org.plan, 0),
            "stores": store_count,
            "ai_used": ai_used,
            "ai_included": ai_included,
            "ai_usage_percent": round(ai_pct, 1),
            "ai_status": ai_status,
            "shopify": has_shopify,
            "whatsapp": has_whatsapp,
            "meta_ads": has_meta_ads,
            "created_at": org.created_at.isoformat() + "Z" if org.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_organization_detail(db: Session, org_id: int) -> dict | None:
    """Get detailed organization info."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return None

    limits = get_organization_limits(org)

    # Stores
    stores = (
        db.query(Store)
        .filter(Store.organization_id == org.id, Store.deleted.is_(False))
        .all()
    )

    # AI usage
    ai_used = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.organization_id == org.id,
            Message.sender == "ai",
        )
        .scalar() or 0
    )

    ai_included = limits.included_ai_responses
    ai_pct = (ai_used / ai_included * 100) if ai_included > 0 else 0

    # Token usage
    from ..services.product_analytics import capture
    # Token data from PostHog (not available in DB)
    # Show what we can from DB

    # Conversations
    conv_count = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.organization_id == org.id)
        .scalar() or 0
    )

    # Orders
    order_count = (
        db.query(func.count(Order.id))
        .filter(Order.organization_id == org.id)
        .scalar() or 0
    )

    # Integrations
    shopify = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == org.id,
            CommerceConnection.provider == "shopify",
        )
        .first()
    )

    whatsapp = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.organization_id == org.id)
        .first()
    )

    meta_ads = (
        db.query(MetaAdsConnection)
        .filter(MetaAdsConnection.organization_id == org.id)
        .first()
    )

    PLAN_PRICES = {
        "starter": 19,
        "growth": 49,
        "pro": 99,
        "scale": 199,
    }

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan or "none",
        "plan_price": PLAN_PRICES.get(org.plan, 0),
        "stores": [
            {
                "id": s.id,
                "name": s.name,
                "country_code": s.country_code,
                "currency": s.currency,
                "active": s.active,
            }
            for s in stores
        ],
        "ai_usage": {
            "used": ai_used,
            "included": ai_included,
            "usage_percent": round(ai_pct, 1),
        },
        "conversations": {"total": conv_count},
        "orders": {"total": order_count},
        "integrations": {
            "shopify": {
                "connected": shopify is not None,
                "status": shopify.status if shopify else None,
            },
            "whatsapp": {
                "connected": whatsapp is not None and whatsapp.status == "connected",
                "status": whatsapp.status if whatsapp else None,
            },
            "meta_ads": {
                "connected": meta_ads is not None and meta_ads.status == "connected",
                "status": meta_ads.status if meta_ads else None,
            },
        },
        "created_at": org.created_at.isoformat() + "Z" if org.created_at else None,
    }


def get_attention_list(db: Session) -> list[dict]:
    """Find organizations that need attention."""
    items = []

    orgs = db.query(Organization).all()

    for org in orgs:
        limits = get_organization_limits(org)
        ai_included = limits.included_ai_responses

        if ai_included == 0:
            continue

        ai_used = (
            db.query(func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.organization_id == org.id,
                Message.sender == "ai",
            )
            .scalar() or 0
        )

        ai_pct = ai_used / ai_included * 100

        if ai_pct >= 95:
            items.append({
                "organization_id": org.id,
                "organization_name": org.name,
                "plan": org.plan or "none",
                "issue": "AI usage at {:.0f}%".format(ai_pct),
                "severity": "CRITICAL" if ai_pct >= 100 else "WARNING",
                "ai_used": ai_used,
                "ai_included": ai_included,
            })
        elif ai_pct >= 80:
            items.append({
                "organization_id": org.id,
                "organization_name": org.name,
                "plan": org.plan or "none",
                "issue": "AI usage at {:.0f}%".format(ai_pct),
                "severity": "INFO",
                "ai_used": ai_used,
                "ai_included": ai_included,
            })

    return sorted(items, key=lambda x: x["ai_used"], reverse=True)
