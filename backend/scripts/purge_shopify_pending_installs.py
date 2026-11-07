"""Operator-gated purge of unclaimed Shopify OAuth grants.

A signed ``shop/redact`` receipt for a shop that never reached tenant selection
still leaves ``shopify_pending_installs`` rows with encrypted access and refresh
tokens. This script is the reviewed, auditable way to remove them.

Run from ``backend/`` with production env securely loaded::

    python -m scripts.purge_shopify_pending_installs \
        --request-id <SHOP_REDACT_REQUEST_ID>

Dry-run is the default and prints counts only. Add ``--confirm`` to write::

    python -m scripts.purge_shopify_pending_installs \
        --request-id <SHOP_REDACT_REQUEST_ID> --confirm

Scheduled cleanup of expired unclaimed grants (safe to run repeatedly)::

    python -m scripts.purge_shopify_pending_installs \
        --expired-only --grace-hours 24 --confirm

The script never prints a shop domain, a token, a request payload or a claim
code. A purge is recorded as a PII-free audit event on the receipt.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import timedelta

from app.db import SessionLocal
from app.services.shopify_pending_install_retention import (
    DEFAULT_EXPIRED_GRACE,
    ShopifyPendingInstallRetentionError,
    preview_expired_unclaimed_pending_installs,
    preview_pending_installs_for_privacy_receipt,
    purge_expired_unclaimed_pending_installs,
    purge_pending_installs_for_privacy_receipt,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Purge unclaimed Shopify pending-install grants. Dry-run unless "
            "--confirm is provided."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--request-id",
        help="64-hex shop/redact receipt id to purge for.",
    )
    mode.add_argument(
        "--expired-only",
        action="store_true",
        help="Purge every expired, unclaimed grant after the grace period.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually write. Without it the script only reports counts.",
    )
    parser.add_argument(
        "--grace-hours",
        type=int,
        default=int(DEFAULT_EXPIRED_GRACE.total_seconds() // 3600),
        help="Grace period for --expired-only (default: 24 hours).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.request_id is not None and not _REQUEST_ID.fullmatch(args.request_id):
        print(json.dumps({"error": "INVALID_PRIVACY_REQUEST_ID"}, sort_keys=True))
        return 2
    if not 0 <= args.grace_hours <= 720:
        print(json.dumps({"error": "INVALID_GRACE_HOURS"}, sort_keys=True))
        return 2

    with SessionLocal() as db:
        try:
            if args.request_id is not None:
                if not args.confirm:
                    report = preview_pending_installs_for_privacy_receipt(
                        db, request_id=args.request_id,
                    )
                    report["dry_run"] = True
                else:
                    report = purge_pending_installs_for_privacy_receipt(
                        db, request_id=args.request_id, commit=True,
                    )
                    report["dry_run"] = False
            else:
                grace = timedelta(hours=args.grace_hours)
                if not args.confirm:
                    report = preview_expired_unclaimed_pending_installs(
                        db, grace=grace,
                    )
                    report["grace_hours"] = args.grace_hours
                    report["dry_run"] = True
                else:
                    report = purge_expired_unclaimed_pending_installs(
                        db, grace=grace, commit=True,
                    )
                    report["grace_hours"] = args.grace_hours
                    report["dry_run"] = False
        except ShopifyPendingInstallRetentionError as exc:
            db.rollback()
            print(json.dumps({"error": str(exc)}, sort_keys=True))
            return 2
        except Exception as exc:
            db.rollback()
            print(json.dumps(
                {"error": "PURGE_FAILED", "error_type": type(exc).__name__},
                sort_keys=True,
            ))
            return 3

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
