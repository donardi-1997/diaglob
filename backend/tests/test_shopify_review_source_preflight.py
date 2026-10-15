"""Shopify review source preflight: synthetic source and current tracked config."""
from pathlib import Path

from app.shopify_oauth import SHOPIFY_SCOPES
from tools.shopify_review_source_preflight import (
    REQUIRES_INDEPENDENT_EVIDENCE,
    inspect_review_source,
)

CLIENT = "a" * 32
APP_HOME = "https://api.diaglob.tech/api/shopify/embedded"


def config(scopes: str = SHOPIFY_SCOPES, *, embedded="true", uri=None,
           topics=None, callback=None, app_home=APP_HOME) -> str:
    if uri is None:
        uri = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
    if topics is None:
        topics = '["customers/data_request", "customers/redact", "shop/redact"]'
    if callback is None:
        callback = "https://api.diaglob.tech/api/shopify/callback"
    return f'''
name = "DIAGLOB"
client_id = "{CLIENT}"
application_url = "{app_home}"
embedded = {embedded}
[access_scopes]
scopes = "{scopes}"
[auth]
redirect_urls = ["{callback}"]
[webhooks]
api_version = "2026-07"
[[webhooks.subscriptions]]
compliance_topics = {topics}
uri = "{uri}"
'''


def test_synthetic_source_parity_is_not_shopify_approval():
    review = inspect_review_source(config(), backend_scopes=SHOPIFY_SCOPES)
    assert review.source_consistent
    assert review.blockers == ()
    assert review.release_authorized is False
    assert review.shopify_approval_verified is False
    assert review.independent_evidence_required == REQUIRES_INDEPENDENT_EVIDENCE
    assert review.as_dict()["mode"] == "repository_source_only"


def test_current_tracked_config_matches_implemented_oauth_scopes_only():
    raw = (Path(__file__).resolve().parents[2] / "shopify.app.toml").read_text(
        encoding="utf-8"
    )
    review = inspect_review_source(raw, backend_scopes=SHOPIFY_SCOPES)
    assert review.source_consistent
    assert review.blockers == ()
    assert review.scopes_requested_but_not_declared == ()
    assert review.scopes_declared_but_not_requested == ()
    # Static source consistency is not evidence of active Shopify version,
    # shop installation, merchant authorization or App Store approval.
    assert review.release_authorized is False
    assert review.shopify_approval_verified is False
    assert "PARTNER_ACTIVE_APP_VERSION_AND_DISTRIBUTION" in review.independent_evidence_required


def test_tracked_config_rejects_unneeded_product_write_scope():
    raw = (Path(__file__).resolve().parents[2] / "shopify.app.toml").read_text(
        encoding="utf-8"
    )
    changed = raw.replace(
        "write_merchant_managed_fulfillment_orders",
        "write_merchant_managed_fulfillment_orders,write_products",
    )
    report = inspect_review_source(changed, backend_scopes=SHOPIFY_SCOPES)
    assert report.source_consistent is False
    assert report.scopes_declared_but_not_requested == ("write_products",)
    assert "SHOPIFY_OAUTH_SCOPE_DRIFT" in report.blockers


def test_denies_missing_or_duplicate_compliance_topics():
    missing = config(topics='["customers/data_request", "shop/redact"]')
    result = inspect_review_source(missing, backend_scopes=SHOPIFY_SCOPES)
    assert "COMPLIANCE_TOPICS_MISSING_OR_DUPLICATED" in result.blockers
    duplicate = config(topics='["customers/data_request", "customers/redact", "customers/redact", "shop/redact"]')
    result = inspect_review_source(duplicate, backend_scopes=SHOPIFY_SCOPES)
    assert "COMPLIANCE_SUBSCRIPTION_URI_OR_TOPICS_INVALID" in result.blockers


def test_rejects_unapproved_webhook_and_oauth_callback():
    result = inspect_review_source(
        config(uri="https://untrusted.example/receive", callback="https://untrusted.example/oauth"),
        backend_scopes=SHOPIFY_SCOPES,
    )
    assert "SHOPIFY_REDIRECTS_MISSING_OR_UNSAFE" in result.blockers
    assert "COMPLIANCE_SUBSCRIPTION_URI_OR_TOPICS_INVALID" in result.blockers


def test_rejects_embedded_app_home_drift():
    changed = config(embedded="false", app_home="https://diaglob.tech/")
    result = inspect_review_source(changed, backend_scopes=SHOPIFY_SCOPES)
    assert "APP_EMBEDDED_MODE_MISMATCH" in result.blockers
    assert "APP_URL_MISMATCH" in result.blockers


def test_rejects_invalid_scopes_and_invalid_toml():
    malformed = inspect_review_source(
        config(scopes="read_products,,read_orders"), backend_scopes=SHOPIFY_SCOPES
    )
    assert "SHOPIFY_SCOPE_SET_MALFORMED" in malformed.blockers
    invalid = inspect_review_source("client_id = [", backend_scopes=SHOPIFY_SCOPES)
    assert invalid.blockers == ("SHOPIFY_CONFIG_INVALID_TOML",)
    huge = inspect_review_source("X" * (257 * 1024), backend_scopes=SHOPIFY_SCOPES)
    assert huge.blockers == ("SHOPIFY_CONFIG_MISSING_OR_OVERSIZED",)


def test_diagnostics_do_not_return_app_client_id_or_customer_data():
    review = inspect_review_source(config(), backend_scopes=SHOPIFY_SCOPES)
    data = str(review.as_dict())
    assert CLIENT not in data
    assert "diaglob-poc.myshopify.com" not in data
    assert review.as_dict()["release_authorized"] is False
