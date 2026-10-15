"""New DIAGLOB price IDs are exact, unique and live-environment scoped.

Price IDs are not credentials; checkout still requires real Paddle API and
webhook credentials in the corresponding environment.
"""
import re

import pytest

from app import billing


EXPECTED_PRICE_IDS = {
    ("starter", 1): "pri_01m50gxt8wr6cqgndwk271zbs2",
    ("starter", 12): "pri_01m50gz7anwanpkww0sgp1f9nz",
    ("growth", 1): "pri_01m50h13qwafmqfqcnsmykzrfz",
    ("growth", 12): "pri_01m50h2054mvwjynacwrs1g122",
    ("pro", 1): "pri_01m50h3z0mtsjj4vnzs5c7z164",
    ("pro", 12): "pri_01m50h4wa2m3tgbdy1q18448v0",
    ("scale", 1): "pri_01m50h5z54txa8zsepx3nfyr35",
    ("scale", 12): "pri_01m50h6r57qvj1pr80czvjnev4",
}


def test_production_price_catalog_has_exactly_eight_unique_ids():
    actual = {
        (plan, months): price_id
        for plan, periods in billing.PADDLE_PRODUCTION_PRICE_IDS.items()
        for months, price_id in periods.items()
    }
    assert actual == EXPECTED_PRICE_IDS
    assert len(set(actual.values())) == 8
    assert all(re.fullmatch(r"pri_[0-9a-z]{26}", value) for value in actual.values())
    assert billing.VALID_BILLING_PERIODS == {1, 12}


@pytest.mark.parametrize("plan,months", EXPECTED_PRICE_IDS)
def test_live_price_ids_resolve_only_when_explicitly_production(
    monkeypatch, plan, months,
):
    monkeypatch.setattr(billing, "CSV_PADDLE_PRICE_IDS", {})
    monkeypatch.delenv(f"PADDLE_PRICE_{plan.upper()}_{months}M", raising=False)
    if months == 1:
        monkeypatch.delenv(f"PADDLE_PRICE_{plan.upper()}", raising=False)

    monkeypatch.setenv("PADDLE_ENVIRONMENT", "sandbox")
    assert billing.resolve_paddle_price(plan, months) is None

    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    assert billing.resolve_paddle_price(plan, months) == EXPECTED_PRICE_IDS[plan, months]


def test_live_environment_explicit_price_override_is_still_supported(monkeypatch):
    monkeypatch.setattr(billing, "CSV_PADDLE_PRICE_IDS", {})
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.setenv("PADDLE_PRICE_STARTER_1M", "pri_override_from_deployment")
    assert billing.resolve_paddle_price("starter", 1) == "pri_override_from_deployment"


def test_unknown_environment_never_loads_live_fallback(monkeypatch):
    monkeypatch.setattr(billing, "CSV_PADDLE_PRICE_IDS", {})
    monkeypatch.delenv("PADDLE_PRICE_SCALE_12M", raising=False)
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "unknown")
    assert billing.resolve_paddle_price("scale", 12) is None
