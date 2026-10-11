"""Bounded, resumable reconciliation for Shopify-managed subscriptions.

Use a trusted scheduler to run all pages. Emit a nonzero status for *any*
failed merchant check or a partial scan. Never log credentials or provider text.
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


def recheck_all(*, page_size: int = 50, max_pages: int = 1000) -> dict:
    """Scan every paid Shopify organization by primary key, each at most once.

    Keyset pagination is resilient to deletions and does not silently abandon
    tenants beyond the first page. A hard page bound causes an incomplete
    result and a nonzero process exit, not a success report.
    """
    if not 1 <= page_size <= 200 or not 1 <= max_pages <= 10000:
        raise ValueError("SHOPIFY_BILLING_INVALID_BATCH_CONFIG")
    if os.getenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "").lower() != "true":
        return {"enabled": False, "complete": False, "checked": 0, "succeeded": 0, "failed": 0}

    checked = succeeded = failed = 0
    cursor = 0
    pages = 0
    while pages < max_pages:
        with SessionLocal() as db:
            ids = [
                row[0] for row in db.query(Organization.id).filter(
                    Organization.id > cursor,
                    Organization.billing_provider == "shopify",
                    Organization.plan.in_(_PAID),
                    Organization.active.is_(True),
                ).order_by(Organization.id).limit(page_size).all()
            ]
        if not ids:
            return {"enabled": True, "complete": True, "checked": checked,
                    "succeeded": succeeded, "failed": failed, "pages": pages}
        pages += 1
        for organization_id in ids:
            with SessionLocal() as db:
                try:
                    refresh_shopify_billing_status(db, organization_id=organization_id)
                    succeeded += 1
                except Exception:
                    db.rollback()
                    failed += 1
                    logger.error("Shopify billing recheck failed organization_id=%d", organization_id)
                checked += 1
        cursor = ids[-1]
        if len(ids) < page_size:
            return {"enabled": True, "complete": True, "checked": checked,
                    "succeeded": succeeded, "failed": failed, "pages": pages}
    # Even when the final page has exactly page_size records, inspect whether
    # another page exists. Never silently report a truncated scan as success.
    with SessionLocal() as db:
        has_more = db.query(Organization.id).filter(
            Organization.id > cursor,
            Organization.billing_provider == "shopify",
            Organization.plan.in_(_PAID),
            Organization.active.is_(True),
        ).first() is not None
    return {"enabled": True, "complete": not has_more, "checked": checked,
            "succeeded": succeeded, "failed": failed, "pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser(description="Recheck all Shopify paid plans")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()
    try:
        result = recheck_all(page_size=args.page_size, max_pages=args.max_pages)
    except ValueError:
        logger.error("Invalid Shopify billing reconciliation configuration")
        return 2
    logger.info(
        "Shopify billing recheck enabled=%s complete=%s checked=%d succeeded=%d failed=%d",
        result["enabled"], result["complete"], result["checked"],
        result["succeeded"], result["failed"],
    )
    return 0 if result["enabled"] and result["complete"] and result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
