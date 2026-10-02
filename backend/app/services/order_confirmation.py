"""Order confirmation helpers shared by voice and fulfillment flows."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Order


_COD_PATTERNS = (
    "cod",
    "cash on delivery",
    "cash_on_delivery",
    "contra entrega",
    "contraentrega",
    "pago contra entrega",
    "payment on delivery",
    "pay on delivery",
)


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def is_cod_payment_method(value: str | None) -> bool:
    normalized = _normalize(value)
    if not normalized:
        return False
    return any(_normalize(pattern) in normalized for pattern in _COD_PATTERNS)


def is_cod_order(order: Order) -> bool:
    return is_cod_payment_method(order.payment_method)


def set_order_confirmation(
    db: Session,
    order: Order,
    *,
    status: str,
    source: str,
    now: datetime,
) -> None:
    order.confirmation_status = status
    order.confirmation_source = source
    order.confirmed_at = now if status == "confirmed" else None
    db.flush()
