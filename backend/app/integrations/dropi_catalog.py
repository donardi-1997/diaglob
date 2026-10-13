"""Strict public-field normalization for untrusted Dropi product pages.

Never pass through the provider payload. Country-specific price/cost semantics
and nested warehouses are intentionally excluded until a real contract test.
"""
from __future__ import annotations

import math


def _safe_text(value: object, *, max_len: int) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


def _stock(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 2_000_000_000 else None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() and 0 <= value <= 2_000_000_000 else None
    if isinstance(value, str):
        value = value.strip()
        if value.isascii() and value.isdecimal() and len(value) <= 10:
            number = int(value)
            return number if number <= 2_000_000_000 else None
    return None


def normalize_product(item: dict) -> dict:
    """Use only allowlisted fields; missing stock means *unknown*, not zero."""
    raw_variants = item.get("variations")
    if raw_variants is None:
        raw_variants = item.get("variants")
    variants_known = isinstance(raw_variants, list)
    if not variants_known:
        raw_variants = []
    normalized = []
    for variant in raw_variants[:30]:
        if not isinstance(variant, dict):
            continue
        normalized.append({
            "id": _safe_text(variant.get("id"), max_len=100),
            "sku": _safe_text(variant.get("sku"), max_len=120),
            "stock": _stock(variant.get("stock")),
        })

    return {
        "id": _safe_text(item.get("id"), max_len=100),
        "name": _safe_text(item.get("name"), max_len=255),
        "sku": _safe_text(item.get("sku"), max_len=120),
        "type": _safe_text(item.get("type"), max_len=40),
        "stock": _stock(item.get("stock")),
        "variants": normalized,
        "variants_in_page": variants_known,
        "variants_truncated": len(raw_variants) > 30,
    }
