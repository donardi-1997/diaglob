"""Prepare privacy-webhook subscriptions in an EXISTING Shopify app config.

Dry-run by default. Never creates an app, deploys a version, or touches customer data.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import tomli

from .shopify_app_config_audit import (
    COMPLIANCE_URI,
    MANDATORY_TOPICS,
    audit_shopify_app_config,
)
from .shopify_oauth import SHOPIFY_SCOPES


class ShopifyConfigPreparationError(ValueError):
    """Existing Shopify configuration cannot be patched safely."""


def prepare_compliance_subscriptions(
    raw: str,
    *,
    expected_client_id: str,
    expected_app_url: str,
    expected_embedded: bool,
) -> tuple[str, tuple[str, ...]]:
    """Add only missing mandatory topics while preserving the existing TOML."""
    if len(raw.encode("utf-8")) > 256 * 1024:
        raise ShopifyConfigPreparationError("OVERSIZED_EXISTING_TOML")
    try:
        config = tomli.loads(raw)
    except (tomli.TOMLDecodeError, ValueError, TypeError) as exc:
        raise ShopifyConfigPreparationError("INVALID_EXISTING_TOML") from exc

    webhooks = config.get("webhooks")
    if not isinstance(webhooks, dict):
        raise ShopifyConfigPreparationError("WEBHOOK_SECTION_MISSING")

    before = audit_shopify_app_config(
        raw,
        expected_client_id=expected_client_id,
        expected_application_url=expected_app_url,
        expected_embedded=expected_embedded,
        expected_scopes=SHOPIFY_SCOPES,
    )
    allowed_failures = {
        "COMPLIANCE_SUBSCRIPTIONS_MISSING",
        "COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED",
    }
    if set(before.failures) - allowed_failures:
        raise ShopifyConfigPreparationError("EXISTING_CONFIG_HAS_OTHER_FAILURES")

    subscriptions = webhooks.get("subscriptions") or []
    if not isinstance(subscriptions, list):
        raise ShopifyConfigPreparationError("INVALID_EXISTING_SUBSCRIPTIONS")

    found: set[str] = set()
    for item in subscriptions:
        topics = item.get("compliance_topics") if isinstance(item, dict) else None
        if topics is None:
            continue
        if item.get("uri") != COMPLIANCE_URI or not isinstance(topics, list):
            raise ShopifyConfigPreparationError("CONFLICTING_COMPLIANCE_SUBSCRIPTION")
        for topic in topics:
            if topic not in MANDATORY_TOPICS or topic in found:
                raise ShopifyConfigPreparationError("UNKNOWN_OR_DUPLICATE_TOPIC")
            found.add(topic)

    missing = tuple(sorted(MANDATORY_TOPICS - found))
    if not missing:
        if not before.static_valid:
            raise ShopifyConfigPreparationError("EXISTING_CONFIG_NOT_VALID")
        return raw, ()

    # Adding a new nested TOML array-of-tables at EOF preserves other settings.
    # No client ID, OAuth settings, scopes or existing webhooks are modified.
    updated = raw.rstrip("\n") + (
        "\n\n[[webhooks.subscriptions]]\n"
        f"compliance_topics = {json.dumps(list(missing))}\n"
        f"uri = {json.dumps(COMPLIANCE_URI)}\n"
    )
    after = audit_shopify_app_config(
        updated,
        expected_client_id=expected_client_id,
        expected_application_url=expected_app_url,
        expected_embedded=expected_embedded,
        expected_scopes=SHOPIFY_SCOPES,
    )
    if not after.static_valid:
        raise ShopifyConfigPreparationError("PREPARED_CONFIG_FAILED_AUDIT")
    return updated, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Existing linked shopify.app.toml")
    parser.add_argument("--expected-app-url", required=True)
    parser.add_argument("--expected-mode", choices=("standalone", "embedded"), required=True)
    parser.add_argument("--apply", action="store_true", help="Update local TOML; never deploy")
    args = parser.parse_args()
    location = Path(args.path)
    try:
        if location.is_symlink() or not location.is_file() or location.stat().st_size > 256 * 1024:
            raise ShopifyConfigPreparationError("SOURCE_MISSING_OR_UNSAFE")
        raw = location.read_text(encoding="utf-8")
        updated, topics = prepare_compliance_subscriptions(
            raw,
            expected_client_id=os.environ.get("SHOPIFY_CLIENT_ID", "").strip(),
            expected_app_url=args.expected_app_url,
            expected_embedded=args.expected_mode == "embedded",
        )
        if args.apply and updated != raw:
            mode = location.stat().st_mode & 0o777
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=location.parent,
                prefix=".shopify-config-", delete=False,
            ) as output:
                temp_path = Path(output.name)
                output.write(updated)
            try:
                temp_path.chmod(mode)
                os.replace(temp_path, location)
            finally:
                temp_path.unlink(missing_ok=True)
        print(json.dumps({
            "valid_local_config": True,
            "missing_topics_prepared": list(topics),
            "local_file_updated": bool(args.apply and updated != raw),
            "deployed_to_shopify": False,
        }, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ShopifyConfigPreparationError) as exc:
        code = str(exc) if isinstance(exc, ShopifyConfigPreparationError) else "FILE_ACCESS_FAILED"
        print(json.dumps({"valid_local_config": False, "error": code, "deployed_to_shopify": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
