"""Fail-closed standard-library preflight for DIAGLOB Shopify app version staging.

This tool has NO Shopify/Admin/Partner API calls. It does NOT stage, release,
install, authorize or edit anything. It validates the existing app's local
version candidate before an operator uses Shopify CLI with --no-release.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGLOB_PUBLIC_CLIENT_ID = "c5fc9aed710462d41767477fa9e595c0"
EXPECTED_SCOPES = frozenset({
    "read_products",
    "read_inventory",
    "read_orders",
    "write_orders",
    "write_draft_orders",
    "read_merchant_managed_fulfillment_orders",
    "write_merchant_managed_fulfillment_orders",
})
LEGACY_FORBIDDEN = frozenset({"read_customers", "write_products"})
REQUIRED_COMPLIANCE = frozenset({
    "customers/data_request", "customers/redact", "shop/redact",
})
APP_URL = "https://api.diaglob.tech/api/shopify/embedded"
CALLBACK = "https://api.diaglob.tech/api/shopify/callback"
COMPLIANCE_URL = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_scopes(value: Any) -> set[str]:
    if not isinstance(value, str) or not value:
        raise ValueError("INVALID_SCOPE_CONFIGURATION")
    raw = [scope.strip() for scope in value.split(",")]
    if not raw or any(_SCOPE_RE.fullmatch(s) is None for s in raw):
        raise ValueError("INVALID_SCOPE_CONFIGURATION")
    if len(raw) != len(set(raw)):
        raise ValueError("DUPLICATE_SCOPES")
    return set(raw)


def _read_backend_scopes(path: Path) -> set[str]:
    """Evaluate ONLY the constant string literal, never import the backend."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SHOPIFY_SCOPES"
            for target in node.targets
        ):
            try:
                return _parse_scopes(ast.literal_eval(node.value))
            except (ValueError, TypeError, SyntaxError, MemoryError):
                raise ValueError("BACKEND_SCOPES_NOT_LITERAL") from None
    raise ValueError("BACKEND_SCOPES_NOT_FOUND")


def inspect_version_candidate(raw: str, *, backend_scopes: set[str]) -> dict:
    """Report only non-secret source metadata. Never affirm live Shopify state."""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 256_000:
        raise ValueError("INVALID_SHOPIFY_CONFIG")
    try:
        cfg = tomllib.loads(raw)
    except (tomllib.TOMLDecodeError, ValueError, TypeError):
        raise ValueError("INVALID_SHOPIFY_CONFIG") from None

    blockers: list[str] = []
    # Fail closed on unreviewed CLI config/extension keys; releasing a CLI
    # version snapshots more than scopes and may omit remote extensions.
    expected_top_level = {
        "name", "client_id", "application_url", "embedded",
        "access_scopes", "auth", "webhooks", "build",
    }
    if set(cfg) != expected_top_level:
        blockers.append("UNREVIEWED_SHOPIFY_CONFIG_KEYS")
    if cfg.get("name") != "DIAGLOB" or cfg.get("client_id") != DIAGLOB_PUBLIC_CLIENT_ID:
        blockers.append("EXISTING_DIAGLOB_APP_IDENTITY_MISMATCH")
    if cfg.get("embedded") is not True or cfg.get("application_url") != APP_URL:
        blockers.append("APP_BRIDGE_EMBEDDED_URL_MISMATCH")
    auth = cfg.get("auth")
    if not isinstance(auth, dict) or auth.get("redirect_urls") != [CALLBACK]:
        blockers.append("APP_OAUTH_CALLBACK_MISMATCH")
    webhooks = cfg.get("webhooks")
    if not isinstance(webhooks, dict) or webhooks.get("api_version") != "2026-07":
        blockers.append("SHOPIFY_WEBHOOK_API_VERSION_MISMATCH")
        webhooks = {}
    subscriptions = webhooks.get("subscriptions", [])
    if not isinstance(subscriptions, list) or len(subscriptions) != 1:
        blockers.append("PRIVACY_WEBHOOK_SUBSCRIPTIONS_CHANGED")
    else:
        entry = subscriptions[0]
        if (
            not isinstance(entry, dict)
            or entry.get("uri") != COMPLIANCE_URL
            or entry.get("topics") is not None
            or not isinstance(entry.get("compliance_topics"), list)
            or len(entry["compliance_topics"]) != len(REQUIRED_COMPLIANCE)
            or set(entry["compliance_topics"]) != REQUIRED_COMPLIANCE
        ):
            blockers.append("PRIVACY_WEBHOOK_SUBSCRIPTIONS_CHANGED")
    scopes = cfg.get("access_scopes")
    if not isinstance(scopes, dict):
        raise ValueError("INVALID_SCOPE_CONFIGURATION")
    declared = _parse_scopes(scopes.get("scopes"))
    if set(scopes) != {"scopes"}:
        blockers.append("UNREVIEWED_SCOPE_CONFIG_KEYS")
    if scopes.get("optional_scopes"):
        blockers.append("OPTIONAL_SCOPES_REQUIRE_SEPARATE_APPROVAL")
    if declared != EXPECTED_SCOPES:
        blockers.append("DECLARED_SCOPES_NOT_APPROVED_SEVEN")
    if backend_scopes != EXPECTED_SCOPES:
        blockers.append("BACKEND_SCOPES_NOT_APPROVED_SEVEN")
    if declared != backend_scopes:
        blockers.append("BACKEND_TOML_SCOPE_DRIFT")
    if declared & LEGACY_FORBIDDEN:
        blockers.append("LEGACY_SCOPES_STILL_REQUESTED")
    if isinstance(auth, dict) and set(auth) != {"redirect_urls"}:
        blockers.append("UNREVIEWED_AUTH_CONFIG_KEYS")
    if isinstance(webhooks, dict) and set(webhooks) != {"api_version", "subscriptions"}:
        blockers.append("UNREVIEWED_WEBHOOK_CONFIG_KEYS")
    if (
        isinstance(subscriptions, list) and len(subscriptions) == 1
        and isinstance(subscriptions[0], dict)
        and set(subscriptions[0]) != {"compliance_topics", "uri"}
    ):
        blockers.append("UNREVIEWED_SUBSCRIPTION_CONFIG_KEYS")
    if cfg.get("build") != {"automatically_update_urls_on_dev": False}:
        blockers.append("SHOPIFY_BUILD_CONFIGURATION_CHANGED")
    return {
        "operation": "source_only_preflight",
        "target_app": "DIAGLOB",
        "expected_client_id": DIAGLOB_PUBLIC_CLIENT_ID,
        "candidate_scopes": sorted(declared),
        "backend_scopes": sorted(backend_scopes),
        "blockers": sorted(set(blockers)),
        "candidate_safe_to_stage_without_release": not blockers,
        "new_version_created": False,
        "existing_app_version_released": False,
        "shopify_active_config_verified": False,
        "shopify_scope_grants_verified": False,
        "protected_customer_data_approval_verified": False,
        "merchant_installation_e2e_verified": False,
    }


def inspect_repository(root: Path = REPO_ROOT) -> dict:
    config = root / "shopify.app.toml"
    backend = root / "backend" / "app" / "shopify_oauth.py"
    if (
        not config.is_file() or not backend.is_file()
        or config.stat().st_size > 256_000
        or backend.stat().st_size > 256_000
    ):
        raise ValueError("EXPECTED_SOURCE_FILES_MISSING")
    return inspect_version_candidate(
        config.read_text(encoding="utf-8"),
        backend_scopes=_read_backend_scopes(backend),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify DIAGLOB's existing Shopify app candidate without deploying"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        report = inspect_repository(args.repository_root)
    except (OSError, ValueError, TypeError, SyntaxError):
        print(json.dumps({"candidate_safe_to_stage_without_release": False,
                          "error": "SHOPIFY_VERSION_CANDIDATE_INVALID"}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["candidate_safe_to_stage_without_release"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
