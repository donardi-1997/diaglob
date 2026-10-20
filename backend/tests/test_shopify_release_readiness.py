"""Safety regressions for Shopify App Store release-readiness evidence."""
import pytest

from app.services.shopify_release_readiness import (
    REQUIRED_GATES,
    evaluate_shopify_release_readiness,
)


def test_missing_evidence_fails_closed():
    result = evaluate_shopify_release_readiness()
    assert result.ready is False
    assert result.missing == REQUIRED_GATES


def test_partial_privacy_and_billing_evidence_does_not_allow_release():
    result = evaluate_shopify_release_readiness({
        "release_head_ci": True,
        "shopify_billing_entitlements": True,
        "privacy_export_and_redaction": False,
    })
    assert result.ready is False
    assert "privacy_export_and_redaction" in result.missing
    assert "external_processors_and_backups" in result.missing


@pytest.mark.parametrize("untrusted", [1, "true", None, [], {}])
def test_truthy_or_untrusted_values_are_not_evidence(untrusted):
    result = evaluate_shopify_release_readiness({
        **dict.fromkeys(REQUIRED_GATES, True),
        "retention_and_legal_holds": untrusted,
    })
    assert result.ready is False
    assert result.missing == ("retention_and_legal_holds",)


def test_all_gates_are_required():
    evidence = dict.fromkeys(REQUIRED_GATES, True)
    assert evaluate_shopify_release_readiness(evidence).ready is True
    for gate in REQUIRED_GATES:
        result = evaluate_shopify_release_readiness({**evidence, gate: False})
        assert result.ready is False
        assert result.missing == (gate,)


def test_unrecognized_keys_cannot_replace_missing_evidence():
    assert evaluate_shopify_release_readiness(
        {"all_complete": True}
    ).missing == REQUIRED_GATES


def test_legacy_complete_evidence_is_not_enough_for_shopify_submission():
    """A previous ten-gate green report must not bypass new Shopify external gates."""
    old_gates = {
        "privacy_export_and_redaction",
        "retention_and_legal_holds",
        "external_processors_and_backups",
        "anti_reingestion",
        "shopify_billing_entitlements",
        "oauth_install_uninstall_e2e",
        "protected_customer_data_scopes",
        "checkout_order_policy_review",
        "listing_and_partner_dashboard",
        "release_head_ci",
    }
    report = evaluate_shopify_release_readiness(dict.fromkeys(old_gates, True))
    assert report.ready is False
    assert {
        "shopify_active_version_matches_source",
        "shopify_requested_scope_parity",
        "shopify_installed_scope_grant_parity",
        "shopify_pcd_level2_field_selection_and_review",
        "shopify_dev_store_e2e_evidence",
        "pcd_level2_security_controls_operational",
    }.issubset(report.missing)


@pytest.mark.parametrize("gate", [
    "shopify_active_version_matches_source",
    "shopify_requested_scope_parity",
    "shopify_installed_scope_grant_parity",
    "shopify_pcd_level2_field_selection_and_review",
    "shopify_dev_store_e2e_evidence",
    "pcd_level2_security_controls_operational",
])
def test_live_shopify_external_evidence_is_independent(gate):
    report = evaluate_shopify_release_readiness({
        **dict.fromkeys(REQUIRED_GATES, True), gate: False,
    })
    assert report.ready is False
    assert report.missing == (gate,)
