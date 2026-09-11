"""
Tests for billing proration calculations.

Covers:
- Starter → Growth
- Growth → Pro
- Pro → Scale
- Upgrade on day 1
- Upgrade mid-period
- Upgrade last day
- Same plan (no-op)
- Decimal precision
- Edge cases
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.billing import (
    PLAN_MONTHLY_PRICES,
    calculate_local_proration,
)


class TestLocalProrationCalculation:
    """Test the local proration calculation engine."""

    def test_starter_to_growth_mid_period(self):
        now = datetime(2026, 8, 15, 12, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["current_plan"] == "starter"
        assert result["target_plan"] == "growth"
        assert result["currency"] == "USD"
        assert result["source"] == "local"

        assert float(result["current_price"]) == 19.00
        assert float(result["target_price"]) == 49.00

        assert result["days_total"] == 30
        assert result["days_elapsed"] == 14
        assert result["days_remaining"] == 16

        credit = Decimal(result["credit"])
        charge = Decimal(result["charge"])

        assert credit > 0
        assert charge > 0
        assert charge > credit

        amount_due = Decimal(result["amount_due_now"])
        assert amount_due > 0

    def test_growth_to_pro_mid_period(self):
        now = datetime(2026, 8, 16, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="growth",
            target_plan="pro",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert float(result["current_price"]) == 49.00
        assert float(result["target_price"]) == 99.00

        credit = Decimal(result["credit"])
        charge = Decimal(result["charge"])

        assert charge > credit

        net = Decimal(result["net_proration_amount"])
        assert net > 0

    def test_pro_to_scale_mid_period(self):
        now = datetime(2026, 8, 20, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="pro",
            target_plan="scale",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert float(result["current_price"]) == 99.00
        assert float(result["target_price"]) == 199.00

        amount_due = Decimal(result["amount_due_now"])
        assert amount_due > 0

    def test_upgrade_day_1(self):
        now = datetime(2026, 8, 1, 1, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="pro",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["days_remaining"] == 30
        assert result["days_elapsed"] == 0

        amount_due = Decimal(result["amount_due_now"])

        credit = Decimal(result["credit"])
        charge = Decimal(result["charge"])

        assert charge > credit
        assert amount_due > Decimal("70.00")

    def test_upgrade_last_day(self):
        now = datetime(2026, 8, 30, 12, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["days_remaining"] == 1

        amount_due = Decimal(result["amount_due_now"])
        assert amount_due == Decimal("0.50")

    def test_same_plan_returns_zero(self):
        now = datetime(2026, 8, 15, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="growth",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["amount_due_now"] == "0.00"

    def test_decimal_precision(self):
        now = datetime(2026, 8, 10, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 9, 1, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        for key in [
            "credit",
            "charge",
            "net_proration_amount",
            "amount_due_now",
            "next_full_charge",
        ]:
            value = Decimal(result[key])
            assert value == value.quantize(Decimal("0.01"))

    def test_unknown_plan_returns_zero_credit(self):
        now = datetime(2026, 8, 15, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="unknown",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["credit"] == "0.00"

        charge = Decimal(result["charge"])
        assert charge > 0

    def test_3_month_billing_period(self):
        now = datetime(2026, 9, 15, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 11, 1, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="growth",
            billing_period_months=3,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["billing_period_months"] == 3
        assert result["days_total"] == 92

        credit = Decimal(result["credit"])
        assert credit > 0

    def test_12_month_billing_period(self):
        now = datetime(2027, 6, 15, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2027, 8, 1, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="growth",
            target_plan="scale",
            billing_period_months=12,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        assert result["billing_period_months"] == 12
        assert result["days_total"] == 365

    def test_output_fields_complete(self):
        now = datetime(2026, 8, 15, 0, 0, 0)
        period_start = datetime(2026, 8, 1, 0, 0, 0)
        period_end = datetime(2026, 8, 31, 0, 0, 0)

        result = calculate_local_proration(
            current_plan="starter",
            target_plan="growth",
            billing_period_months=1,
            current_period_start=period_start,
            current_period_end=period_end,
            now=now,
        )

        expected_keys = {
            "current_plan",
            "target_plan",
            "currency",
            "current_price",
            "target_price",
            "billing_period_months",
            "days_total",
            "days_elapsed",
            "days_remaining",
            "credit",
            "charge",
            "net_proration_amount",
            "amount_due_now",
            "next_full_charge",
            "next_billed_at",
            "effective_date",
            "source",
        }

        assert expected_keys == set(result.keys())


class TestPlanPrices:
    """Verify plan prices are correctly defined."""

    def test_all_plans_have_prices(self):
        assert "starter" in PLAN_MONTHLY_PRICES
        assert "growth" in PLAN_MONTHLY_PRICES
        assert "pro" in PLAN_MONTHLY_PRICES
        assert "scale" in PLAN_MONTHLY_PRICES

    def test_prices_are_correct(self):
        assert PLAN_MONTHLY_PRICES["starter"] == Decimal("19.00")
        assert PLAN_MONTHLY_PRICES["growth"] == Decimal("49.00")
        assert PLAN_MONTHLY_PRICES["pro"] == Decimal("99.00")
        assert PLAN_MONTHLY_PRICES["scale"] == Decimal("199.00")

    def test_prices_are_ordered(self):
        assert (
            PLAN_MONTHLY_PRICES["starter"]
            < PLAN_MONTHLY_PRICES["growth"]
            < PLAN_MONTHLY_PRICES["pro"]
            < PLAN_MONTHLY_PRICES["scale"]
        )



def test_upgrade_credit_charge_and_amount_due_decrease_over_time():
    period_start = datetime(2026, 8, 1, 0, 0, 0)
    period_end = datetime(2026, 8, 31, 0, 0, 0)

    early = calculate_local_proration(
        "starter", "growth", 1, period_start, period_end,
        datetime(2026, 8, 1, 1, 0, 0),
    )
    middle = calculate_local_proration(
        "starter", "growth", 1, period_start, period_end,
        datetime(2026, 8, 15, 12, 0, 0),
    )
    late = calculate_local_proration(
        "starter", "growth", 1, period_start, period_end,
        datetime(2026, 8, 30, 12, 0, 0),
    )

    assert Decimal(early["credit"]) > Decimal(middle["credit"]) > Decimal(late["credit"])
    assert Decimal(early["charge"]) > Decimal(middle["charge"]) > Decimal(late["charge"])
    assert Decimal(early["amount_due_now"]) > Decimal(middle["amount_due_now"]) > Decimal(late["amount_due_now"])


def test_multi_month_upgrade_prorates_discounted_target_period_price():
    result = calculate_local_proration(
        current_plan="starter",
        target_plan="growth",
        billing_period_months=3,
        current_period_start=datetime(2026, 8, 1, 0, 0, 0),
        current_period_end=datetime(2026, 11, 1, 0, 0, 0),
        now=datetime(2026, 9, 15, 0, 0, 0),
    )

    assert Decimal(result["charge"]) == Decimal("71.52")
    assert Decimal(result["credit"]) == Decimal("27.59")
    assert Decimal(result["amount_due_now"]) == Decimal("43.93")
    assert Decimal(result["next_full_charge"]) == Decimal("140.00")
    assert result["next_billed_at"] == "2026-11-01T00:00:00"
