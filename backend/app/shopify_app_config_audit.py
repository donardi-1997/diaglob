"""Read-only audit of the *linked, existing* Shopify app configuration.

This tool never creates a Shopify application or deploys an app version.
A passing local TOML check does NOT establish that Shopify Dev Dashboard has
the same active version, App Pricing plans, or that GDPR is fulfilled.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import tomli

MANDATORY_TOPICS = frozenset((
    "customers/data_request", "customers/redact", "shop/redact",
))
COMPLIANCE_URI = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
CALLBACK_URI = "https://api.diaglob.tech/api/shopify/callback"
MAX_TOML_BYTES = 256 * 1024


@dataclass(frozen=True)
class ShopifyConfigAudit:
    static_valid: bool
    failures: tuple[str, ...]
    # The installed Shopify Dev Dashboard app version must be checked separately.
    deployed_version_verified: bool = False


def _safe_https_address(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https" and parsed.hostname is not None
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
            and not parsed.fragment
        )
    except ValueError:
        return False


def audit_shopify_app_config(
    raw_toml: str,
    *,
    expected_client_id: str,
    expected_application_url: str,
    expected_embedded: bool,
    expected_scopes: str,
) -> ShopifyConfigAudit:
    """Check linked app identity, scopes, OAuth, and all privacy callbacks.

    An explicit expected app URL and mode is mandatory: do not guess whether
    an existing app is embedded or standalone. No secrets or TOML values
    are returned in errors, to keep CLI/CI logs safe.
    """
    failures: list[str] = []

    if (
        not expected_client_id or not expected_client_id.strip()
        or not _safe_https_address(expected_application_url)
        or type(expected_embedded) is not bool
        or not expected_scopes.strip()
    ):
        return ShopifyConfigAudit(False, ("EXPECTED_APP_IDENTITY_INCOMPLETE",))

    if type(raw_toml) is not str or len(raw_toml.encode("utf-8")) > MAX_TOML_BYTES:
        return ShopifyConfigAudit(False, ("APP_CONFIG_MISSING_OR_OVERSIZED",))

    try:
        app = tomli.loads(raw_toml)
    except (tomli.TOMLDecodeError, ValueError, TypeError):
        return ShopifyConfigAudit(False, ("APP_CONFIG_INVALID_TOML",))

    if not isinstance(app, dict):
        return ShopifyConfigAudit(False, ("APP_CONFIG_INVALID_TOML",))
    if app.get("client_id") != expected_client_id:
        failures.append("APP_CLIENT_ID_MISMATCH")
    if app.get("application_url") != expected_application_url:
        failures.append("APP_URL_MISMATCH")
    if type(app.get("embedded")) is not bool or app["embedded"] != expected_embedded:
        failures.append("APP_EMBEDDED_MODE_MISMATCH")

    auth = app.get("auth")
    urls = auth.get("redirect_urls") if isinstance(auth, dict) else None
    if (
        not isinstance(urls, list) or len(urls) != len(set(map(str, urls)))
        or set(urls) != {CALLBACK_URI}
        or any(not _safe_https_address(url) for url in urls)
    ):
        failures.append("SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE")

    scopes = app.get("access_scopes")
    scope_text = scopes.get("scopes") if isinstance(scopes, dict) else None
    if not isinstance(scope_text, str):
        failures.append("SHOPIFY_SCOPES_MISSING")
    else:
        actual = [scope.strip() for scope in scope_text.split(",")]
        expected = [scope.strip() for scope in expected_scopes.split(",")]
        if (
            any(not re.fullmatch(r"[a-z][a-z0-9_]*", scope) for scope in actual)
            or len(set(actual)) != len(actual)
            or set(actual) != set(expected)
        ):
            failures.append("SHOPIFY_SCOPES_DO_NOT_MATCH_BACKEND")

    webhooks = app.get("webhooks")
    api_version = webhooks.get("api_version") if isinstance(webhooks, dict) else None
    if not isinstance(api_version, str) or not re.fullmatch(
        r"20[0-9]{2}-(?:01|04|07|10)", api_version
    ):
        failures.append("WEBHOOK_API_VERSION_MISSING")

    subscriptions = (
        webhooks.get("subscriptions") if isinstance(webhooks, dict) else None
    )
    if not isinstance(subscriptions, list):
        failures.append("COMPLIANCE_SUBSCRIPTIONS_MISSING")
    else:
        counts = {topic: 0 for topic in MANDATORY_TOPICS}
        for entry in subscriptions:
            if not isinstance(entry, dict):
                failures.append("COMPLIANCE_SUBSCRIPTION_INVALID")
                continue
            topics = entry.get("compliance_topics")
            if topics is None:
                # Other non-compliance app webhook subscriptions are allowed.
                continue
            if not isinstance(topics, list) or not topics:
                failures.append("COMPLIANCE_SUBSCRIPTION_INVALID")
                continue
            if (
                entry.get("uri") != COMPLIANCE_URI
                or entry.get("topics") is not None
                or len(set(map(str, topics))) != len(topics)
            ):
                failures.append("COMPLIANCE_SUBSCRIPTION_URI_OR_TOPICS_INVALID")
            for topic in topics:
                if topic not in counts:
                    failures.append("COMPLIANCE_UNKNOWN_TOPIC")
                else:
                    counts[topic] += 1
        if any(value != 1 for value in counts.values()):
            failures.append("COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED")

    return ShopifyConfigAudit(not failures, tuple(dict.fromkeys(failures)))


def main() -> int:
    from .shopify_oauth import SHOPIFY_SCOPES

    parser = argparse.ArgumentParser(
        description="Audit a linked existing Shopify app TOML; no Shopify writes."
    )
    parser.add_argument("--path", required=True)
    parser.add_argument("--expected-app-url", required=True)
    parser.add_argument("--expected-mode", choices=("embedded", "standalone"), required=True)
    args = parser.parse_args()
    expected_client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
    location = Path(args.path)
    try:
        if not location.is_file() or location.stat().st_size > MAX_TOML_BYTES:
            raise ValueError("Invalid local config file")
        raw = location.read_text(encoding="utf-8")
        result = audit_shopify_app_config(
            raw,
            expected_client_id=expected_client_id,
            expected_application_url=args.expected_app_url,
            expected_embedded=args.expected_mode == "embedded",
            expected_scopes=SHOPIFY_SCOPES,
        )
    except (OSError, UnicodeError, ValueError):
        result = ShopifyConfigAudit(False, ("APP_CONFIG_NOT_READABLE",))
    print(json.dumps({
        "static_valid": result.static_valid,
        "deployed_version_verified": False,
        "failures": list(result.failures),
    }, sort_keys=True))
    return 0 if result.static_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
