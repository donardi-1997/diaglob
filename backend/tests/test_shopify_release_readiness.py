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
