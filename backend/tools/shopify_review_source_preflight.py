"""Fail-closed, read-only Shopify App Store source configuration preflight.

This only checks the committed TOML against the committed backend; it does not
read Shopify Partner state, access customer data, or authorize a submission.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import tomli

from app.shopify_app_config_audit import audit_shopify_app_config

# These checks are external to the repository and cannot be passed by CI.
REQUIRES_INDEPENDENT_EVIDENCE = (
    "PARTNER_ACTIVE_APP_VERSION_AND_DISTRIBUTION",
    "LIVE_COMPLIANCE_WEBHOOK_SUBSCRIPTIONS_AND_HMAC_DELIVERIES",
    "PROTECTED_CUSTOMER_DATA_FIELD_APPROVAL",
    "OAUTH_INSTALL_REINSTALL_AND_EMBEDDED_SESSION_E2E",
    "PRIVACY_ACCESS_REDACTION_RETENTION_AND_PROCESSORS",
    "SHOPIFY_APP_PRICING_AND_BILLING_TEST",
    "FUNCTIONAL_REVIEWER_ACCOUNT_AND_REAL_SCREENCAST",
    "LISTING_FIELDS_SUPPORT_CONTACTS_AND_REVIEW_INSTRUCTIONS",
)
CONFIGURED_APP_HOME = "https://api.diaglob.tech/api/shopify/embedded"
MAX_FILE_BYTES = 256 * 1024


@dataclass(frozen=True)
class ReviewPreflight:
    source_consistent: bool
    blockers: tuple[str, ...]
    scopes_requested_but_not_declared: tuple[str, ...]
    scopes_declared_but_not_requested: tuple[str, ...]
    independent_evidence_required: tuple[str, ...] = REQUIRES_INDEPENDENT_EVIDENCE
    release_authorized: bool = False
    shopify_approval_verified: bool = False

    def as_dict(self) -> dict:
        return {
            "mode": "repository_source_only",
            "source_consistent": self.source_consistent,
            "blockers": list(self.blockers),
            "scopes_requested_but_not_declared": list(
                self.scopes_requested_but_not_declared
            ),
            "scopes_declared_but_not_requested": list(
                self.scopes_declared_but_not_requested
            ),
            "independent_evidence_required": list(self.independent_evidence_required),
            "release_authorized": False,
            "shopify_approval_verified": False,
        }


def _scope_set(value: object) -> set[str] | None:
    if not isinstance(value, str):
        return None
    raw = [name.strip() for name in value.split(",")]
    if (
        not raw or any(re.fullmatch(r"[a-z][a-z0-9_]*", x) is None for x in raw)
        or len(set(raw)) != len(raw)
    ):
        return None
    return set(raw)


def inspect_review_source(raw_toml: str, *, backend_scopes: str) -> ReviewPreflight:
    """Compare effective backend OAuth request with committed Shopify config."""
    errors: list[str] = []
    empty = ((), ())
    if (
        not isinstance(raw_toml, str)
        or len(raw_toml.encode("utf-8")) > MAX_FILE_BYTES
    ):
        errors.append("SHOPIFY_CONFIG_MISSING_OR_OVERSIZED")
        return ReviewPreflight(False, tuple(errors), *empty)
    try:
        app = tomli.loads(raw_toml)
    except (tomli.TOMLDecodeError, ValueError, TypeError):
        errors.append("SHOPIFY_CONFIG_INVALID_TOML")
        return ReviewPreflight(False, tuple(errors), *empty)
    if not isinstance(app, dict):
        return ReviewPreflight(False, ("SHOPIFY_CONFIG_INVALID_TOML",), *empty)

    client_id = app.get("client_id")
    if not isinstance(client_id, str) or re.fullmatch(r"[a-fA-F0-9]{32}", client_id) is None:
        errors.append("SHOPIFY_CLIENT_ID_MISSING_OR_INVALID")

    declared = app.get("access_scopes")
    declared_scopes = _scope_set(declared.get("scopes")) if isinstance(declared, dict) else None
    requested_scopes = _scope_set(backend_scopes)
    if declared_scopes is None or requested_scopes is None:
        errors.append("SHOPIFY_SCOPE_SET_MALFORMED")
    source_only = tuple(sorted((requested_scopes or set()) - (declared_scopes or set())))
    config_only = tuple(sorted((declared_scopes or set()) - (requested_scopes or set())))
    if source_only or config_only:
        errors.append("SHOPIFY_OAUTH_SCOPE_DRIFT")

    # This invokes the existing strict compliance-topic, callback, API version,
    # app URL and embedded-mode checks. App identity is SOURCE-LOCAL ONLY:
    # passing it does not prove Shopify's active version has the same ID.
    audit = audit_shopify_app_config(
        raw_toml,
        expected_client_id=client_id if isinstance(client_id, str) else "",
        expected_application_url=CONFIGURED_APP_HOME,
        expected_embedded=True,
        expected_scopes=backend_scopes,
    )
    errors.extend(audit.failures)
    return ReviewPreflight(
        source_consistent=not errors,
        blockers=tuple(dict.fromkeys(errors)),
        scopes_requested_but_not_declared=source_only,
        scopes_declared_but_not_requested=config_only,
    )


def main() -> int:
    from app.shopify_oauth import SHOPIFY_SCOPES

    parser = argparse.ArgumentParser(
        description="Audit committed Shopify source only; NEVER deploy or approve."
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.config.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("oversized")
        raw = args.config.read_text(encoding="utf-8")
        result = inspect_review_source(raw, backend_scopes=SHOPIFY_SCOPES)
    except (OSError, UnicodeError, ValueError):
        result = ReviewPreflight(
            False, ("SHOPIFY_CONFIG_NOT_READABLE",), (), (),
        )
    print(json.dumps(result.as_dict(), sort_keys=True))
    # CI can verify this tool with synthetic configs without declaring that
    # Shopify submission is ready. Source drift is non-zero intentionally.
    return 0 if result.source_consistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
