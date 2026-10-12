"""Shopify App Store linked configuration audit (static, synthetic TOML)."""
from app.shopify_oauth import SHOPIFY_SCOPES
from app.shopify_app_config_audit import (
    CALLBACK_URI,
    COMPLIANCE_URI,
    audit_shopify_app_config,
)

APP_URL = "https://api.diaglob.tech/api/shopify/install"
CLIENT_ID = "synthetic-existing-diaglob-app"


def _config(
    *,
    client_id: str = CLIENT_ID,
    app_url: str = APP_URL,
    embedded: str = "false",
    scopes: str = SHOPIFY_SCOPES,
    redirects: str = f'["{CALLBACK_URI}"]',
    subscriptions: str = "",
) -> str:
    if not subscriptions:
        subscriptions = f'''
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "{COMPLIANCE_URI}"
'''
    return f'''
client_id = "{client_id}"
application_url = "{app_url}"
embedded = {embedded}

[access_scopes]
scopes = "{scopes}"

[auth]
redirect_urls = {redirects}

[webhooks]
api_version = "2026-07"

{subscriptions}
'''


def _audit(raw: str, **overrides):
    kwargs = {
        "expected_client_id": CLIENT_ID,
        "expected_application_url": APP_URL,
        "expected_embedded": False,
        "expected_scopes": SHOPIFY_SCOPES,
    }
    kwargs.update(overrides)
    return audit_shopify_app_config(raw, **kwargs)


def test_exact_existing_app_fields_and_all_three_compliance_topics():
    result = _audit(_config())
    assert result.static_valid is True
    assert result.failures == ()
    # A local TOML is NEVER proof of a deployed version or actual fulfillment.
    assert result.deployed_version_verified is False


def test_wrong_app_identity_or_unverified_install_mode_fails_closed():
    assert "APP_CLIENT_ID_MISMATCH" in _audit(_config(client_id="other-app")).failures
    assert "APP_URL_MISMATCH" in _audit(_config(app_url="https://evil.example")).failures
    assert "APP_EMBEDDED_MODE_MISMATCH" in _audit(_config(embedded="true")).failures
    assert "EXPECTED_APP_IDENTITY_INCOMPLETE" in _audit(
        _config(), expected_client_id=""
    ).failures


def test_reject_missing_callback_extra_unsafe_redirect_and_scope_mismatch():
    assert "SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE" in _audit(
        _config(redirects='["https://evil.example/oauth"]')
    ).failures
    assert "SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE" in _audit(
        _config(redirects=f'["{CALLBACK_URI}", "http://evil.example"]')
    ).failures
    assert "SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE" in _audit(
        _config(redirects=f'["{CALLBACK_URI}", "https://evil.example/oauth"]')
    ).failures
    assert "SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE" in _audit(
        _config(redirects=f'["{CALLBACK_URI}", 24]')
    ).failures
    assert "SHOPIFY_SCOPES_DO_NOT_MATCH_BACKEND" in _audit(
        _config(scopes="read_products")
    ).failures
    assert "SHOPIFY_SCOPES_DO_NOT_MATCH_BACKEND" in _audit(
        _config(scopes=SHOPIFY_SCOPES + ",read_products")
    ).failures


def test_compliance_topic_must_be_exactly_once_on_expected_endpoint():
    missing_redact = f'''
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "shop/redact"]
uri = "{COMPLIANCE_URI}"
'''
    assert "COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED" in _audit(
        _config(subscriptions=missing_redact)
    ).failures

    wrong_destination = '''
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "https://evil.example/receive"
'''
    assert "COMPLIANCE_SUBSCRIPTION_URI_OR_TOPICS_INVALID" in _audit(
        _config(subscriptions=wrong_destination)
    ).failures

    duplicate_topics = f'''
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "{COMPLIANCE_URI}"

[[webhooks.subscriptions]]
compliance_topics = ["customers/redact"]
uri = "{COMPLIANCE_URI}"
'''
    assert "COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED" in _audit(
        _config(subscriptions=duplicate_topics)
    ).failures


def test_allow_unrelated_regular_webhooks_without_granting_compliance():
    subscriptions = f'''
[[webhooks.subscriptions]]
topics = ["orders/create"]
uri = "/api/webhooks/shopify"

[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "{COMPLIANCE_URI}"
'''
    assert _audit(_config(subscriptions=subscriptions)).static_valid is True


def test_invalid_toml_invalid_expected_mode_and_oversized_input_fail_closed():
    assert _audit("client_id = [").failures == ("APP_CONFIG_INVALID_TOML",)
    assert "APP_CONFIG_MISSING_OR_OVERSIZED" in _audit(
        "A" * (257 * 1024)
    ).failures
    assert "EXPECTED_APP_IDENTITY_INCOMPLETE" in _audit(
        _config(), expected_embedded="false"
    ).failures


def test_nested_nonstring_topic_cannot_crash_the_auditor():
    malformed_topics = f'''
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", ["customers/redact"], "shop/redact"]
uri = "{COMPLIANCE_URI}"
'''
    result = _audit(_config(subscriptions=malformed_topics))
    assert result.static_valid is False
    assert "COMPLIANCE_UNKNOWN_TOPIC" in result.failures
    assert "COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED" in result.failures
