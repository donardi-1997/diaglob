"""Generate a DISABLED S3 lifecycle proposal from an approved retention decision.

Never imports boto3, invokes AWS, or enables a destructive expiration rule.
The user must review the full bucket configuration before an operator can apply.
"""
from __future__ import annotations

import argparse
import json
import re


_ALLOWED_PREFIX = re.compile(r"^organizations/[1-9][0-9]*/knowledge-bases/[1-9][0-9]*/documents/$")


def make_disabled_lifecycle_rule(
    *, prefix: str, noncurrent_days: int, approval_reference: str,
) -> dict:
    """Propose retention for one explicit tenant KB source prefix, disabled."""
    if not isinstance(prefix, str) or not _ALLOWED_PREFIX.fullmatch(prefix):
        raise ValueError("APPROVED_EXACT_KNOWLEDGE_PREFIX_REQUIRED")
    if type(noncurrent_days) is not int or not 1 <= noncurrent_days <= 3650:
        raise ValueError("APPROVED_NONCURRENT_RETENTION_DAYS_REQUIRED")
    if not isinstance(approval_reference, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{5,63}", approval_reference
    ):
        raise ValueError("RETENTION_APPROVAL_REFERENCE_REQUIRED")
    return {
        "ID": "PCD-REVIEW-NONCURRENT-" + prefix.strip("/").replace("/", "-"),
        "Status": "Disabled",
        "Filter": {"Prefix": prefix},
        "NoncurrentVersionExpiration": {"NoncurrentDays": noncurrent_days},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print only a disabled S3 lifecycle policy candidate; no AWS calls"
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--noncurrent-days", type=int, required=True)
    parser.add_argument("--approval-reference", required=True)
    args = parser.parse_args()
    rule = make_disabled_lifecycle_rule(
        prefix=args.prefix,
        noncurrent_days=args.noncurrent_days,
        approval_reference=args.approval_reference,
    )
    print(json.dumps({
        "proposal_only": True,
        "aws_modified": False,
        "approval_reference": args.approval_reference,
        "warning": "DISABLED RULE ONLY; existing bucket rules must be merged safely",
        "candidate_rule": rule,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
