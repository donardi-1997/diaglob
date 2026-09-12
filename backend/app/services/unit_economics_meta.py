"""Resolve store-level Meta Ads spend for Unit Economics.

This service owns business semantics only. Provider HTTP remains in the existing
Meta Ads client. Missing or unavailable provider data is never coerced to zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from ..integrations.meta_ads.client import (
    MetaAdsError,
    get_insights,
    parse_insights_row,
)
from ..meta_ads_security import decrypt_secret
from ..models import MetaAdsConnection, Store


SOURCE = "meta_ads"
ZERO = Decimal("0")


def _result(
    *,
    amount: Decimal | None,
    status: str,
    reason: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "amount": amount,
        "source": SOURCE,
        "status": status,
        "reason": reason,
        "metadata": metadata or {},
    }


def _missing(reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return _result(amount=None, status="missing", reason=reason, metadata=metadata)


def _meta_time_range(
    date_from: datetime,
    date_to_exclusive: datetime,
) -> dict[str, str]:
    """Convert Diaglob's half-open window to Meta's inclusive date window."""
    return {
        "since": date_from.date().isoformat(),
        "until": (date_to_exclusive.date() - timedelta(days=1)).isoformat(),
    }


def _validated_spend(row: dict[str, Any]) -> Decimal | None:
    """Return provider spend only when the raw value is present and finite.

    The generic Meta parser intentionally defaults malformed metrics to zero for
    resilient dashboards. Unit Economics must be stricter because a fabricated
    zero would overstate contribution profit.
    """
    raw_spend = row.get("spend")
    if raw_spend is None:
        return None
    try:
        spend = Decimal(str(raw_spend))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return spend if spend.is_finite() else None


def resolve_meta_ad_spend(
    db: Session,
    organization_id: int,
    store: Store,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    """Resolve exact-period Meta spend without fabricating unavailable costs.

    ``date_to`` follows the analytics half-open convention and is exclusive.
    A provider-confirmed empty response is an actual zero; connection, currency,
    credential, malformed-data, or provider failures remain explicitly missing.
    """
    connection = (
        db.query(MetaAdsConnection)
        .filter(
            MetaAdsConnection.organization_id == organization_id,
            MetaAdsConnection.store_id == store.id,
            MetaAdsConnection.status == "connected",
        )
        .first()
    )
    if connection is None:
        return _missing("meta_not_connected")

    if date_from is None or date_to is None or date_to <= date_from:
        return _missing("bounded_date_range_required")

    provider_currency = (connection.account_currency or "").strip().upper()
    store_currency = (store.currency or "").strip().upper()
    currency_metadata = {
        "store_currency": store_currency or None,
        "provider_currency": provider_currency or None,
    }

    if not provider_currency:
        return _missing("currency_unknown", currency_metadata)

    if not store_currency or provider_currency != store_currency:
        return _missing("currency_mismatch", currency_metadata)

    time_range = _meta_time_range(date_from, date_to)
    metadata = {
        **currency_metadata,
        "account_id": connection.external_account_id,
        "time_range": time_range,
    }

    try:
        access_token = decrypt_secret(connection.access_token_encrypted)
    except Exception:
        return _missing("credentials_unavailable", metadata)

    try:
        insights = get_insights(
            access_token,
            connection.external_account_id,
            date_preset=None,
            time_range=time_range,
        )
    except MetaAdsError as exc:
        return _missing(
            "provider_error",
            {
                **metadata,
                "provider_error_code": exc.code,
            },
        )

    spend = ZERO
    for index, row in enumerate(insights or []):
        raw_spend = _validated_spend(row)
        if raw_spend is None:
            return _missing(
                "provider_error",
                {
                    **metadata,
                    "invalid_spend_row": index,
                },
            )
        # Preserve the existing provider parser as the canonical conversion path
        # after validating that Unit Economics is not inheriting its zero fallback.
        spend += parse_insights_row({**row, "spend": str(raw_spend)})["spend"]

    return _result(
        amount=spend,
        status="actual",
        reason=None,
        metadata={
            **metadata,
            "rows": len(insights or []),
        },
    )
