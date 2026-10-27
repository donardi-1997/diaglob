from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.billing_channel_policy import external_app_billing_block_reason


def test_direct_paddle_account_with_non_revoked_shopify_install_uses_shopify_pricing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=7)
    organization = SimpleNamespace(
        id=42,
        billing_provider="paddle",
        billing_onboarding_channel="direct",
    )

    reason = external_app_billing_block_reason(db, organization)

    assert reason == "SHOPIFY_APP_PRICING_REQUIRED"


def test_revoked_shopify_install_does_not_block_direct_web_billing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    organization = SimpleNamespace(
        id=42,
        billing_provider="paddle",
        billing_onboarding_channel="direct",
    )

    reason = external_app_billing_block_reason(db, organization)

    assert reason is None
