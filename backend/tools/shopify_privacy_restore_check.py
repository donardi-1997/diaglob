"""Operator-only tombstone checkpoint utility.

Capture a checkpoint BEFORE backup/restore and store the resulting HMAC +
row count in an independently access-controlled, append-only location.
After restoration, provide that external checkpoint for validation before
resuming customer ingestion. Never source the expected checkpoint from the
database snapshot being evaluated.

Run from backend/: python -m tools.shopify_privacy_restore_check snapshot
or python -m tools.shopify_privacy_restore_check verify --expected-HMAC ...
 --minimum-records ...
"""
from __future__ import annotations

import argparse
import json

from app.db import SessionLocal
from app.services.shopify_privacy_restore import (
    create_shopify_suppression_checkpoint,
    verify_shopify_suppression_restore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Shopify privacy restore checkpoint")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="Print opaque keyed checkpoint for offline ledger")
    verify = sub.add_parser("verify", help="Compare restored data with offsite checkpoint")
    verify.add_argument("--expected-hmac", required=True)
    verify.add_argument("--minimum-records", required=True, type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "snapshot":
            result = create_shopify_suppression_checkpoint(db)
        else:
            result = verify_shopify_suppression_restore(
                db, externally_stored_hmac=args.expected_hmac,
                minimum_records=args.minimum_records,
            )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
