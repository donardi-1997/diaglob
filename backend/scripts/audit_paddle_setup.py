"""Read-only Paddle configuration audit. Never creates a transaction.

Run from backend/:
    PADDLE_ENVIRONMENT=production PADDLE_API_KEY=... python -m scripts.audit_paddle_setup

Requires Paddle price.read and notification_setting.read permissions.
Do not paste API keys into chat or commit them.
"""
from __future__ import annotations

import json
import os
import sys

import httpx

from app.billing import PADDLE_PRODUCTION_PRICE_IDS, PLAN_PERIOD_PRICES

WEBHOOK_URL = "https://api.diaglob.tech/api/billing/webhook"
EXPECTED_EVENTS = {
    "subscription.created",
    "subscription.trialing",
    "subscription.activated",
    "subscription.updated",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.canceled",
    "transaction.completed",
}

def audit() -> dict:
    env = (os.getenv("PADDLE_ENVIRONMENT") or "").strip().lower()
    key = (os.getenv("PADDLE_API_KEY") or "").strip()
    report = {"environment": env or "unset", "prices": [], "webhook": {}, "ready": False}
    if env not in {"production", "sandbox"}:
        report["blocker"] = "Set PADDLE_ENVIRONMENT explicitly to production or sandbox"
        return report
    if not key:
        report["blocker"] = "PADDLE_API_KEY is missing (supply securely as env secret)"
        return report
    expected_prefix = "pdl_live_apikey_" if env == "production" else "pdl_sdbx_apikey_"
    if not key.startswith(expected_prefix):
        report["blocker"] = "PADDLE_API_KEY prefix does not match the environment"
        return report

    base = "https://api.paddle.com" if env == "production" else "https://sandbox-api.paddle.com"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    with httpx.Client(base_url=base, headers=headers, timeout=12) as client:
        for plan, months_prices in PLAN_PERIOD_PRICES.items():
            for months, expected in months_prices.items():
                variable = f"PADDLE_PRICE_{plan.upper()}_{months}M"
                price_id = os.getenv(variable) or (
                    PADDLE_PRODUCTION_PRICE_IDS[plan][months] if env == "production" else None
                )
                row = {"plan": plan, "months": months, "expected_usd": str(expected)}
                if not price_id:
                    row["result"] = "missing_price_id"
                    report["prices"].append(row)
                    continue
                row["price_id"] = price_id
                try:
                    response = client.get(f"/prices/{price_id}", params={"include": "product"})
                    row["http_status"] = response.status_code
                    if response.status_code != 200:
                        row["result"] = "api_error"
                        report["prices"].append(row)
                        continue
                    data = response.json().get("data") or {}
                    product = data.get("product") or {}
                    cycle = data.get("billing_cycle") or {}
                    trial = data.get("trial_period") or {}
                    amount_minor = data.get("unit_price") or {}
                    trial_price = trial.get("unit_price")
                    checks = {
                        "price_id": data.get("id") == price_id,
                        "active": data.get("status") == "active",
                        "currency_usd": amount_minor.get("currency_code") == "USD",
                        "amount": amount_minor.get("amount") == str(int(expected * 100)),
                        "cycle": cycle.get("interval") == ("month" if months == 1 else "year")
                                  and cycle.get("frequency") == 1,
                        "trial_3days": trial.get("interval") == "day"
                                       and trial.get("frequency") == 3,
                        "trial_free": trial_price is None,
                        "product": product.get("name", "").lower() == f"diaglob {plan}",
                        "product_active": product.get("status") == "active",
                        "product_saas": product.get("tax_category") == "saas",
                        # Only an explicit inclusive mode proves tax inclusion
                        # from the price object alone. An account-level default
                        # must be independently checked in the Paddle dashboard.
                        "tax_included": data.get("tax_mode") == "internal",
                        "card_required_for_trial": trial.get("requires_payment_method") is True,
                    }
                    row["checks"] = checks
                    row["tax_mode"] = data.get("tax_mode")
                    row["requires_payment_method"] = trial.get("requires_payment_method")
                    row["result"] = "pass" if all(checks.values()) else "mismatch"
                except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                    row["result"] = "request_failed"
                report["prices"].append(row)

        try:
            response = client.get("/notification-settings", params={"per_page": 200})
            report["webhook"]["http_status"] = response.status_code
            if response.status_code == 200:
                endpoints = [
                    item for item in response.json().get("data", [])
                    if item.get("type") == "url"
                    and item.get("destination", "").rstrip("/") == WEBHOOK_URL
                    and item.get("active") is True
                    and item.get("traffic_source") in ("all", "platform")
                ]
                good = []
                for item in endpoints:
                    events = {e.get("name") for e in item.get("subscribed_events", [])}
                    good.append({
                        "id": item.get("id"),
                        "traffic_source": item.get("traffic_source"),
                        "missing_events": sorted(EXPECTED_EVENTS - events),
                    })
                report["webhook"]["destinations"] = good
                report["webhook"]["configured"] = any(not v["missing_events"] for v in good)
            else:
                report["webhook"]["error"] = "Cannot read notification settings or permission denied"
        except (httpx.HTTPError, ValueError):
            report["webhook"]["error"] = "Could not reach notifications API"

    report["ready"] = (
        len(report["prices"]) == 8
        and all(row.get("result") == "pass" for row in report["prices"])
        and report["webhook"].get("configured") is True
    )
    # Live account approval and real checkout still require independent proof.
    # Account-default tax mode is deliberately not assumed to be tax-inclusive.
    return report


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ready"] else 1)
