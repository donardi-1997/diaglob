"""Operator-gated no-data determination for a signed Shopify privacy receipt.

Dry-run (default) prints the eligibility report with table/column names and
counts only::

    python -m scripts.close_shopify_privacy_no_data_case \
        --request-id <SHOP_REDACT_REQUEST_ID>

Write the determination only after legal/privacy review and evidence capture::

    python -m scripts.close_shopify_privacy_no_data_case \
        --request-id <SHOP_REDACT_REQUEST_ID> --confirm

This never sets ``completed_at``, never marks a task ``verified`` and never
authorizes erasure or export. It records that no tenant data was attributable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from app.db import SessionLocal
from app.services.shopify_privacy_no_data import (
    ShopifyPrivacyNoDataError,
    assess_no_data_attributable,
    close_shopify_privacy_case_as_no_data,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a no-data-attributable privacy determination.",
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the determination. Without it the script is read-only.",
    )
    args = parser.parse_args(argv)

    if not _REQUEST_ID.fullmatch(args.request_id):
        print(json.dumps({"error": "INVALID_PRIVACY_REQUEST_ID"}, sort_keys=True))
        return 2

    with SessionLocal() as db:
        try:
            if not args.confirm:
                report = assess_no_data_attributable(
                    db, request_id=args.request_id,
                )
                if report is None:
                    print(json.dumps(
                        {"error": "PRIVACY_RECEIPT_NOT_FOUND"}, sort_keys=True,
                    ))
                    return 2
                report["dry_run"] = True
            else:
                report = close_shopify_privacy_case_as_no_data(
                    db, request_id=args.request_id, commit=True,
                )
                if report is None:
                    print(json.dumps(
                        {"error": "PRIVACY_RECEIPT_NOT_FOUND"}, sort_keys=True,
                    ))
                    return 2
                report["dry_run"] = False
        except ShopifyPrivacyNoDataError as exc:
            db.rollback()
            print(json.dumps({"error": str(exc)}, sort_keys=True))
            return 2
        except Exception as exc:
            db.rollback()
            print(json.dumps(
                {
                    "error": "DETERMINATION_FAILED",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            ))
            return 3

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
