"""Purge expired real local export ciphertext only after operator opt-in.

This does not process buyer records, sign permits, or mark GDPR complete.
Run from a restricted scheduler after deployment and operational authorization.
"""
from __future__ import annotations

import json

from app.services.shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, require_execution_policy,
)


def main() -> int:
    try:
        require_execution_policy()  # Before opening any production DB session.
    except ShopifyPrivacyExecutionError as exc:
        print(json.dumps({"purged": False, "code": str(exc), "fulfillment_complete": False}))
        return 2
    from app.db import SessionLocal
    from app.services.shopify_privacy_live_delivery import purge_expired_local_privacy_deliveries
    with SessionLocal() as db:
        count = purge_expired_local_privacy_deliveries(db)
    print(json.dumps({"purged_expired_local_artifacts": count, "fulfillment_complete": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
