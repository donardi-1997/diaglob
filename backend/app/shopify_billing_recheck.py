"""Explicit batch recheck for Shopify App Pricing subscription state.

Run with a trusted scheduler and service environment, for example
  cd backend && python -m app.shopify_billing_recheck --limit 50 --after-id 0
Do not run against production before the Shopify billing go/no-go approval.
No tokens or raw provider responses are logged.
"""
from __future__ import annotations

import argparse
import logging
import os

from .db import SessionLocal
from .models import Organization
from .services.shopify_billing_lifecycle import refresh_shopify_billing_status

logger = logging.getLogger(__name__)
_PAID = ("starter", "growth", "pro", "scale")


def main() -> int:
    parser = argparse.ArgumentParser(description="Recheck Shopify-managed paid plans")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--after-id", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 200 or args.after_id < 0:
        parser.error("limit must be 1..200 and after-id >= 0")
    if os.getenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "").lower() != "true":
        logger.warning("Shopify entitlement refresh is disabled; no operation performed")
        return 2

    with SessionLocal() as db:
        ids = [
            row[0] for row in db.query(Organization.id).filter(
                Organization.id > args.after_id,
                Organization.billing_provider == "shopify",
                Organization.plan.in_(_PAID),
                Organization.active.is_(True),
            ).order_by(Organization.id).limit(args.limit).all()
        ]

    ok = 0
    failed = 0
    for organization_id in ids:
        with SessionLocal() as db:
            try:
                refresh_shopify_billing_status(
                    db, organization_id=organization_id
                )
                ok += 1
            except Exception:
                db.rollback()
                failed += 1
                # Avoid exposing exceptions that could include provider secrets.
                logger.error("Shopify billing recheck failed for organization_id=%d", organization_id)

    logger.info(
        "Shopify billing batch: checked=%d success=%d failed=%d next_after_id=%s",
        len(ids), ok, failed, ids[-1] if ids else args.after_id,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
