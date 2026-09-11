import csv
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


# ============================================================
# PADDLE PRICE MATRIX
# ============================================================

VALID_BILLING_PERIODS = {
    1,
    3,
    6,
    12,
}


PADDLE_PRICE_CSV = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "paddle-period-prices.csv"
)


def load_paddle_prices_from_csv():
    prices = {
        "starter": {},
        "growth": {},
        "pro": {},
        "scale": {},
    }

    if not PADDLE_PRICE_CSV.exists():
        return prices

    try:
        with PADDLE_PRICE_CSV.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)

            for row in reader:
                plan = (
                    row.get("Plan")
                    or ""
                ).strip().lower()

                price_id = (
                    row.get("PriceId")
                    or ""
                ).strip()

                status = (
                    row.get("Status")
                    or ""
                ).strip().lower()

                try:
                    months = int(
                        row.get("Months")
                        or 0
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if plan not in prices:
                    continue

                if months not in VALID_BILLING_PERIODS:
                    continue

                if not price_id:
                    continue

                if status and status != "active":
                    continue

                prices[plan][months] = (
                    price_id
                )

    except (
        OSError,
        csv.Error,
    ):
        return prices

    return prices


CSV_PADDLE_PRICE_IDS = (
    load_paddle_prices_from_csv()
)


def resolve_paddle_price(
    plan: str,
    months: int,
    legacy_env_name: str | None = None,
):
    env_name = (
        f"PADDLE_PRICE_{plan.upper()}_{months}M"
    )

    value = os.getenv(
        env_name
    )

    if (
        not value
        and months == 1
        and legacy_env_name
    ):
        value = os.getenv(
            legacy_env_name
        )

    if value:
        return value

    return (
        CSV_PADDLE_PRICE_IDS
        .get(plan, {})
        .get(months)
    )


PADDLE_PRICE_IDS = {
    "starter": {
        1: resolve_paddle_price(
            "starter",
            1,
            "PADDLE_PRICE_STARTER",
        ),
        3: resolve_paddle_price(
            "starter",
            3,
        ),
        6: resolve_paddle_price(
            "starter",
            6,
        ),
        12: resolve_paddle_price(
            "starter",
            12,
        ),
    },

    "growth": {
        1: resolve_paddle_price(
            "growth",
            1,
            "PADDLE_PRICE_GROWTH",
        ),
        3: resolve_paddle_price(
            "growth",
            3,
        ),
        6: resolve_paddle_price(
            "growth",
            6,
        ),
        12: resolve_paddle_price(
            "growth",
            12,
        ),
    },

    "pro": {
        1: resolve_paddle_price(
            "pro",
            1,
            "PADDLE_PRICE_PRO",
        ),
        3: resolve_paddle_price(
            "pro",
            3,
        ),
        6: resolve_paddle_price(
            "pro",
            6,
        ),
        12: resolve_paddle_price(
            "pro",
            12,
        ),
    },

    "scale": {
        1: resolve_paddle_price(
            "scale",
            1,
            "PADDLE_PRICE_SCALE",
        ),
        3: resolve_paddle_price(
            "scale",
            3,
        ),
        6: resolve_paddle_price(
            "scale",
            6,
        ),
        12: resolve_paddle_price(
            "scale",
            12,
        ),
    },
}


PRICE_TO_PLAN = {
    price_id: plan
    for plan, periods in PADDLE_PRICE_IDS.items()
    for period, price_id in periods.items()
    if price_id
}


PRICE_TO_PERIOD = {
    price_id: period
    for plan, periods in PADDLE_PRICE_IDS.items()
    for period, price_id in periods.items()
    if price_id
}


def get_paddle_price_id(
    plan: str,
    billing_period_months: int = 1,
) -> str:
    normalized_plan = (
        plan
        .strip()
        .lower()
    )

    try:
        normalized_period = int(
            billing_period_months
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Invalid billing period"
        ) from exc

    if normalized_period not in VALID_BILLING_PERIODS:
        raise ValueError(
            "Billing period must be "
            "1, 3, 6 or 12 months"
        )

    plan_prices = PADDLE_PRICE_IDS.get(
        normalized_plan
    )

    if not plan_prices:
        raise ValueError(
            f"Invalid plan: {normalized_plan}"
        )

    price_id = plan_prices.get(
        normalized_period
    )

    if not price_id:
        raise ValueError(
            "No Paddle price configured for "
            f"{normalized_plan} "
            f"{normalized_period}M"
        )

    return price_id


def get_plan_from_price_id(
    price_id: str,
) -> str | None:
    return PRICE_TO_PLAN.get(
        price_id
    )


def get_billing_period_from_price_id(
    price_id: str,
) -> int | None:
    return PRICE_TO_PERIOD.get(
        price_id
    )


import hashlib
import hmac
import time


def verify_paddle_signature(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> None:
    if not signature_header:
        raise ValueError(
            "Paddle-Signature missing"
        )

    parts = {}

    for component in signature_header.split(";"):
        if "=" not in component:
            continue

        key, value = component.split(
            "=",
            1,
        )

        parts.setdefault(
            key,
            [],
        ).append(value)

    timestamps = parts.get(
        "ts",
        [],
    )

    signatures = parts.get(
        "h1",
        [],
    )

    if not timestamps or not signatures:
        raise ValueError(
            "Invalid Paddle-Signature"
        )

    timestamp = timestamps[0]

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise ValueError(
            "Invalid Paddle timestamp"
        ) from exc

    age = abs(
        int(time.time())
        - timestamp_int
    )

    if age > tolerance_seconds:
        raise ValueError(
            "Paddle webhook timestamp outside tolerance"
        )

    signed_payload = (
        timestamp.encode("utf-8")
        + b":"
        + raw_body
    )

    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(
        hmac.compare_digest(
            expected,
            signature,
        )
        for signature in signatures
    ):
        raise ValueError(
            "Invalid Paddle webhook signature"
        )


def get_subscription_price_id(
    data: dict,
) -> str | None:
    items = data.get("items") or []

    for item in items:
        price = item.get("price") or {}

        price_id = price.get("id")

        if price_id:
            return price_id

        price_id = item.get("price_id")

        if price_id:
            return price_id

    return None


# ============================================================
# PLAN PRICES (USD, source of truth for local fallback)
# ============================================================

PLAN_PERIOD_PRICES: dict[str, dict[int, Decimal]] = {
    "starter": {
        1: Decimal("19.00"),
        3: Decimal("54.00"),
        6: Decimal("103.00"),
        12: Decimal("190.00"),
    },
    "growth": {
        1: Decimal("49.00"),
        3: Decimal("140.00"),
        6: Decimal("265.00"),
        12: Decimal("490.00"),
    },
    "pro": {
        1: Decimal("99.00"),
        3: Decimal("282.00"),
        6: Decimal("535.00"),
        12: Decimal("990.00"),
    },
    "scale": {
        1: Decimal("199.00"),
        3: Decimal("570.00"),
        6: Decimal("1075.00"),
        12: Decimal("1990.00"),
    },
}

PLAN_MONTHLY_PRICES: dict[str, Decimal] = {
    plan: periods[1]
    for plan, periods in PLAN_PERIOD_PRICES.items()
}


def add_billing_months(value: datetime, months: int) -> datetime:
    """Advance by calendar months while clamping end-of-month dates."""
    from calendar import monthrange

    months = int(months)
    if months <= 0:
        raise ValueError("Billing period must be positive")

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def resolve_billing_period(
    anchor: datetime,
    billing_period_months: int,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Resolve the local fallback period containing ``now`` from an anchor."""
    if anchor > now:
        return anchor, add_billing_months(anchor, billing_period_months)

    period_start = anchor
    period_end = add_billing_months(period_start, billing_period_months)

    while period_end <= now:
        period_start = period_end
        period_end = add_billing_months(period_start, billing_period_months)

    return period_start, period_end


# ============================================================
# LOCAL PRORATION CALCULATION
# ============================================================

def calculate_local_proration(
    current_plan: str,
    target_plan: str,
    billing_period_months: int,
    current_period_start: datetime,
    current_period_end: datetime,
    now: datetime | None = None,
) -> dict:
    """Prorate an upgrade inside the current paid billing cycle.

    Both the unused current-plan credit and the target-plan charge are limited
    to the remaining fraction of the existing period. The upgrade therefore
    changes the plan immediately without moving the renewal date:

        amount due = prorated target charge - unused current-plan credit

    At the existing renewal date the customer is charged the full target-plan
    period price. Decimal arithmetic and ROUND_HALF_UP are used for money.
    """
    from math import ceil

    if now is None:
        now = datetime.utcnow()

    billing_period_months = int(billing_period_months or 1)

    total_seconds = max(
        (current_period_end - current_period_start).total_seconds(),
        1.0,
    )
    elapsed_seconds = min(
        max((now - current_period_start).total_seconds(), 0.0),
        total_seconds,
    )
    remaining_seconds = max(total_seconds - elapsed_seconds, 0.0)

    remaining_ratio = Decimal(str(remaining_seconds)) / Decimal(str(total_seconds))

    current_monthly = PLAN_MONTHLY_PRICES.get(current_plan, Decimal("0"))
    target_monthly = PLAN_MONTHLY_PRICES.get(target_plan, Decimal("0"))

    current_period_total = PLAN_PERIOD_PRICES.get(current_plan, {}).get(
        billing_period_months,
        Decimal("0"),
    )
    target_period_total = PLAN_PERIOD_PRICES.get(target_plan, {}).get(
        billing_period_months,
        Decimal("0"),
    )

    credit_current = (current_period_total * remaining_ratio).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if current_plan == target_plan:
        charge_new = Decimal("0.00")
        net = Decimal("0.00")
    else:
        charge_new = (target_period_total * remaining_ratio).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        net = charge_new - credit_current

    amount_due_now = max(net, Decimal("0.00")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    days_total = max(int(ceil(total_seconds / 86400.0)), 1)
    days_elapsed = max(min(int(elapsed_seconds // 86400.0), days_total), 0)
    days_remaining = max(int(ceil(remaining_seconds / 86400.0)), 0)

    return {
        "current_plan": current_plan,
        "target_plan": target_plan,
        "currency": "USD",
        "current_price": str(current_monthly.quantize(Decimal("0.01"))),
        "target_price": str(target_monthly.quantize(Decimal("0.01"))),
        "billing_period_months": billing_period_months,
        "days_total": days_total,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "credit": str(credit_current),
        "charge": str(charge_new),
        "net_proration_amount": str(
            net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ),
        "amount_due_now": str(amount_due_now),
        "next_full_charge": str(
            target_period_total.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        ),
        "next_billed_at": current_period_end.isoformat(),
        "effective_date": now.isoformat(),
        "source": "local",
    }