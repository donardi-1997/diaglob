"""Source-only Shopify release staging safety tests. No Shopify credentials."""
from pathlib import Path

import pytest

from tools.shopify_scope_release_preflight import (
    CALLBACK, COMPLIANCE_URL, DIAGLOB_PUBLIC_CLIENT_ID, EXPECTED_SCOPES,
    inspect_repository, inspect_version_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / "shopify.app.toml").read_text(encoding="utf-8")


def check(raw: str, *, scopes=None):
    return inspect_version_candidate(
        raw, backend_scopes=set(EXPECTED_SCOPES) if scopes is None else scopes
    )


def test_committed_main_candidate_is_safe_for_staging_but_not_for_release():
    report = inspect_repository(ROOT)
    assert report["candidate_safe_to_stage_without_release"] is True
    assert report["blockers"] == []
    assert report["expected_client_id"] == DIAGLOB_PUBLIC_CLIENT_ID
    assert report["candidate_scopes"] == sorted(EXPECTED_SCOPES)
    for flag in (
        "new_version_created", "existing_app_version_released",
        "shopify_active_config_verified", "shopify_scope_grants_verified",
        "protected_customer_data_approval_verified",
        "merchant_installation_e2e_verified",
    ):
        assert report[flag] is False


@pytest.mark.parametrize("old,new,code", [
    (DIAGLOB_PUBLIC_CLIENT_ID, "a" * 32,
     "EXISTING_DIAGLOB_APP_IDENTITY_MISMATCH"),
    ('embedded = true', 'embedded = false',
     "APP_BRIDGE_EMBEDDED_URL_MISMATCH"),
    ('https://api.diaglob.tech/api/shopify/embedded',
     'https://evil.example.test/home',
     "APP_BRIDGE_EMBEDDED_URL_MISMATCH"),
    (CALLBACK, "https://evil.example.test/callback",
     "APP_OAUTH_CALLBACK_MISMATCH"),
    (COMPLIANCE_URL, "https://evil.example.test/collect",
     "PRIVACY_WEBHOOK_SUBSCRIPTIONS_CHANGED"),
    ('"customers/data_request"', '"customers/fake"',
     "PRIVACY_WEBHOOK_SUBSCRIPTIONS_CHANGED"),
    ('api_version = "2026-07"', 'api_version = "2024-01"',
     "SHOPIFY_WEBHOOK_API_VERSION_MISMATCH"),
    ("automatically_update_urls_on_dev = false",
     "automatically_update_urls_on_dev = true",
     "SHOPIFY_BUILD_CONFIGURATION_CHANGED"),
])
def test_source_identity_and_compliance_drift_blocks_version_candidate(old, new, code):
    assert old in RAW
    report = check(RAW.replace(old, new))
    assert code in report["blockers"]
    assert report["candidate_safe_to_stage_without_release"] is False


def test_legacy_customer_and_product_write_scopes_are_blocked():
    raw = RAW.replace(
        "scopes = \"read_products,", "scopes = \"read_customers,write_products,read_products,"
    )
    report = check(raw)
    assert "LEGACY_SCOPES_STILL_REQUESTED" in report["blockers"]
    assert "DECLARED_SCOPES_NOT_APPROVED_SEVEN" in report["blockers"]


def test_optional_scope_configuration_must_be_reviewed_separately():
    raw = RAW.replace("[auth]", 'optional_scopes = ["read_customers"]\n\n[auth]')
    report = check(raw)
    assert "OPTIONAL_SCOPES_REQUIRE_SEPARATE_APPROVAL" in report["blockers"]


def test_backend_and_local_config_must_match_exactly():
    report = check(RAW, scopes=EXPECTED_SCOPES - {"write_orders"})
    assert "BACKEND_SCOPES_NOT_APPROVED_SEVEN" in report["blockers"]
    assert "BACKEND_TOML_SCOPE_DRIFT" in report["blockers"]


def test_duplicate_scopes_fail_closed():
    raw = RAW.replace("scopes = \"read_products,", "scopes = \"read_products,read_products,")
    with pytest.raises(ValueError, match="DUPLICATE_SCOPES"):
        check(raw)


def test_wrong_app_or_malformed_toml_never_returns_success():
    with pytest.raises(ValueError, match="INVALID_SHOPIFY_CONFIG"):
        check('invalid = "unterminated')


def test_compliance_topic_duplicate_rejected():
    raw = RAW.replace('"shop/redact"]', '"customers/redact"]')
    assert "PRIVACY_WEBHOOK_SUBSCRIPTIONS_CHANGED" in check(raw)["blockers"]


def test_missing_expected_repository_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="EXPECTED_SOURCE_FILES_MISSING"):
        inspect_repository(tmp_path)


def test_source_preflight_never_reads_credentials(monkeypatch):
    # Only filesystem + static config are inspected; ensure no token values leak.
    monkeypatch.setenv("SHOPIFY_APP_AUTOMATION_TOKEN", "synthetic_private_token")
    assert "synthetic_private_token" not in str(inspect_repository(ROOT))


@pytest.mark.parametrize("tail,blocker", [
    ('\n[app_proxy]\nurl = "https://other.example.test"\n',
     "UNREVIEWED_SHOPIFY_CONFIG_KEYS"),
    ('\n[access_scopes]\nscopes = "read_products"\n', None),
])
def test_unknown_version_components_do_not_get_automatic_staging(tail, blocker):
    if blocker is None:
        # Duplicate sections must fail before authorization can be implied.
        with pytest.raises(ValueError, match="INVALID_SHOPIFY_CONFIG"):
            check(RAW + tail)
    else:
        result = check(RAW + tail)
        assert blocker in result["blockers"]
        assert result["candidate_safe_to_stage_without_release"] is False


def test_staging_workflow_is_manual_and_never_releases_a_version():
    source = (ROOT / ".github" / "workflows" / "shopify-stage-scopes.yml").read_text()
    assert "workflow_dispatch:" in source
    assert "\n  push:" not in source
    assert "\n  schedule:" not in source
    assert "\n  pull_request:" not in source
    assert "--no-release" in source
    assert "--no-input" in source
    assert "SHOPIFY_APP_AUTOMATION_TOKEN" in source
    assert "STAGE-DIAGLOB-NO-RELEASE" in source
    assert "\n          shopify app release " not in source
    assert "shopify app config link" not in source
    assert "shopify app init" not in source
