"""Safety regression tests for existing Shopify app configuration preparation."""

import pytest

from app.shopify_app_config_audit import COMPLIANCE_URI
from app.shopify_compliance_config_prepare import (
    ShopifyConfigPreparationError,
    prepare_compliance_subscriptions,
)
from app.shopify_oauth import SHOPIFY_SCOPES

CLIENT_ID = "synthetic-existing-app"
URL = "https://api.diaglob.tech/api/shopify/install"


def config(extra: str = "", *, client_id: str = CLIENT_ID, embedded: str = "false") -> str:
    return f'''client_id = "{client_id}"
application_url = "{URL}"
embedded = {embedded}
[auth]
redirect_urls = ["https://api.diaglob.tech/api/shopify/callback"]
[access_scopes]
scopes = "{SHOPIFY_SCOPES}"
[webhooks]
api_version = "2026-07"
{extra}
'''


def prepare(raw: str):
    return prepare_compliance_subscriptions(
        raw, expected_client_id=CLIENT_ID,
        expected_app_url=URL, expected_embedded=False,
    )


def test_missing_all_added_once_and_idempotent():
    initial = config()
    updated, missing = prepare(initial)
    assert missing == ("customers/data_request", "customers/redact", "shop/redact")
    assert updated.startswith(initial.rstrip("\n"))
    assert f'uri = "{COMPLIANCE_URI}"' in updated
    assert prepare(updated) == (updated, ())


def test_partial_config_preserves_existing_subscriptions():
    original = config(f'''[[webhooks.subscriptions]]
compliance_topics = ["shop/redact"]
uri = "{COMPLIANCE_URI}"

[[webhooks.subscriptions]]
topics = ["orders/create"]
uri = "/api/webhooks/shopify"
''')
    updated, missing = prepare(original)
    assert missing == ("customers/data_request", "customers/redact")
    assert 'topics = ["orders/create"]' in updated
    assert updated.count("compliance_topics =") == 2


@pytest.mark.parametrize("raw", [
    config('''[[webhooks.subscriptions]]
compliance_topics = ["shop/redact"]
uri = "https://invalid.example/webhooks"
'''),
    config(f'''[[webhooks.subscriptions]]
compliance_topics = ["shop/redact", "shop/redact"]
uri = "{COMPLIANCE_URI}"
'''),
    config(client_id="wrong-shopify-app"),
    config(embedded="true"),
    config().replace('api_version = "2026-07"', ""),
    config().replace('[webhooks]\napi_version = "2026-07"', ""),
])
def test_inconsistent_app_config_fails_closed(raw):
    with pytest.raises(ShopifyConfigPreparationError):
        prepare(raw)


def test_existing_config_with_all_topics_is_not_modified():
    initial = config(f'''[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "{COMPLIANCE_URI}"
''')
    assert prepare(initial) == (initial, ())
