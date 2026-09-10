"""Customer audience listing for automation builders.

Keeps audience browsing aligned with the same customer metrics and commercial
classifications used by runtime campaign resolution.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..customers.intelligence import get_customer_metrics
from .customer_classification_service import enrich_customer_metrics


def list_classified_audience_customers(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    search: str | None = None,
    segment: str | None = None,
    priority: str | None = None,
    health: str | None = None,
    country: str | None = None,
    classification: str | None = None,
    value_tier: str | None = None,
    needs_attention: bool | None = None,
    has_orders: bool | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "priority_desc",
) -> dict[str, Any]:
    metrics = get_customer_metrics(db, organization_id, store_id)
    metrics = enrich_customer_metrics(db, organization_id, store_id, metrics)

    if search:
        needle = search.strip().lower()
        metrics = [
            item
            for item in metrics
            if needle in (item.get("name") or "").lower()
            or needle in (item.get("phone") or "").lower()
            or needle in (item.get("email") or "").lower()
        ]
    if segment:
        metrics = [item for item in metrics if item.get("primary_segment") == segment]
    if priority:
        metrics = [item for item in metrics if item.get("priority") == priority]
    if health:
        metrics = [item for item in metrics if item.get("customer_health") == health]
    if country:
        metrics = [item for item in metrics if item.get("country_code") == country]
    if classification:
        metrics = [
            item
            for item in metrics
            if item.get("commercial_classification") == classification
        ]
    if value_tier:
        metrics = [item for item in metrics if item.get("value_tier") == value_tier]
    if needs_attention is not None:
        metrics = [item for item in metrics if item.get("needs_attention") == needs_attention]
    if has_orders is not None:
        metrics = [
            item
            for item in metrics
            if (item.get("successful_order_count", 0) > 0) == has_orders
        ]

    priority_order = {"high": 3, "medium": 2, "low": 1}
    if sort == "score_desc":
        metrics.sort(key=lambda item: item.get("customer_score", 0), reverse=True)
    elif sort == "value_desc":
        metrics.sort(key=lambda item: item.get("rfm_monetary_value", 0), reverse=True)
    elif sort == "frequency_desc":
        metrics.sort(key=lambda item: item.get("rfm_frequency", 0), reverse=True)
    elif sort == "last_interaction_desc":
        metrics.sort(key=lambda item: item.get("last_interaction_at") or "", reverse=True)
    else:
        metrics.sort(
            key=lambda item: (
                priority_order.get(item.get("priority", ""), 0),
                item.get("customer_score", 0),
            ),
            reverse=True,
        )

    total = len(metrics)
    page_size = min(max(1, page_size), 100)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size

    fields = (
        "id",
        "name",
        "phone",
        "email",
        "country_code",
        "primary_segment",
        "priority",
        "customer_score",
        "customer_health",
        "last_interaction_at",
        "successful_order_count",
        "spend_by_currency",
        "needs_attention",
        "commercial_classification",
        "value_tier",
        "rfm_recency_days",
        "rfm_frequency",
        "rfm_monetary_value",
        "rfm_score",
    )
    items = []
    for item in metrics[start:start + page_size]:
        row = {
            ("customer_id" if key == "id" else key): item.get(key)
            for key in fields
        }
        items.append(row)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
