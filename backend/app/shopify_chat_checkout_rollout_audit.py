"""Read-only, PII-free production audit for the Shopify chat checkout pilot.

Only prints an effective status; never prints the target tenant IDs, tokens,
shop URL or environment values. This is an observation, not an enablement.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from .db import SessionLocal
from .services.conversational_checkout_service import _poc_checkout_connection


def effective_pilot_status() -> str:
    if os.getenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", "").strip().lower() not in (
        "1", "true", "yes",
    ):
        return "disabled"

    org_id = os.getenv("SHOPIFY_CHAT_CHECKOUT_POC_ORGANIZATION_ID", "").strip()
    store_id = os.getenv("SHOPIFY_CHAT_CHECKOUT_POC_STORE_ID", "").strip()
    if not all(
        value.isascii() and value.isdecimal() and int(value) > 0
        for value in (org_id, store_id)
    ):
        return "blocked_missing_scope"

    try:
        with SessionLocal() as db:
            checkout = SimpleNamespace(
                organization_id=int(org_id), store_id=int(store_id)
            )
            connection = _poc_checkout_connection(db, checkout)
            return "scoped_poc_ready" if connection is not None else "blocked"
    except Exception:
        # Never print exception text: it may contain SQL or shop identifiers.
        return "blocked_unverified_connection"


if __name__ == "__main__":
    print("SHOPIFY_CHAT_CHECKOUT_PILOT_STATUS=" + effective_pilot_status())
