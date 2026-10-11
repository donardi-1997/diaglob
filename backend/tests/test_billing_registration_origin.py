"""Shopify install signup is provisional until an authorized OAuth callback.

No Partner tokens or live commerce calls; ORM tests operate only on SQLite.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.auth import RegistrationProvisionRequest
from app.db import Base
from app.models import CommerceConnection, Organization, Store
from app.services.billing_onboarding import (
    confirm_shopify_install_billing,
    registration_billing_channel,
)


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_connected(sandbox, *, origin="shopify_install", provider=None,
                   plan="trial", active=True):
    org = Organization(
        name="Synthetic Signup",
        slug="signup-origin-test",
        billing_provider=provider,
        billing_onboarding_channel=origin,
        plan=plan,
        active=active,
    )
    sandbox.add(org)
    sandbox.flush()
    store = Store(
        organization_id=org.id,
        name="Shopify Test",
        slug="shopify-test",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        active=True,
        deleted=False,
    )
    sandbox.add(store)
    sandbox.flush()
    connection = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url="verified-store.myshopify.com",
        access_token_encrypted="SYNTHETIC_ENCRYPTED_TOKEN",
        status="connected",
    )
    sandbox.add(connection)
    sandbox.commit()
    return org, store, connection


def test_direct_signup_has_explicit_paddle_billing_channel():
    assert registration_billing_channel("direct") == ("direct", "paddle")
    assert RegistrationProvisionRequest(name="Person").registration_channel == "direct"


def test_shopify_signup_stays_pending_until_authorized_oauth_callback():
    assert registration_billing_channel("shopify_install") == (
        "shopify_install", None
    )
    candidate = RegistrationProvisionRequest(
        name="Person", registration_channel="shopify_install",
    )
    assert candidate.registration_channel == "shopify_install"


@pytest.mark.parametrize("value", [
    "shopify", "paddle", "", "SHOPIFY_INSTALL", "shopify_install ",
    "../shopify", "admin",
])
def test_registration_cannot_set_paid_provider_or_unrecognized_source(value):
    with pytest.raises(ValueError, match="INVALID_REGISTRATION_BILLING_ORIGIN"):
        registration_billing_channel(value)


def test_verified_install_promotes_only_original_pending_organization(sandbox):
    org, store, connection = make_connected(sandbox)
    assert org.billing_provider is None
    assert confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    ) is True
    sandbox.expire_all()
    assert org.billing_provider == "shopify"
    assert org.billing_onboarding_channel == "shopify_install"
    assert org.plan == "trial"
    assert connection.access_token_encrypted == "SYNTHETIC_ENCRYPTED_TOKEN"


@pytest.mark.parametrize("origin,provider,plan", [
    ("direct", "paddle", "trial"),
    ("direct", None, "trial"),
    (None, None, "trial"),
    ("shopify_install", "paddle", "trial"),
    ("shopify_install", None, "starter"),
    ("shopify_install", None, "growth"),
])
def test_regular_shopify_commerce_connection_never_switches_billing(
    sandbox, origin, provider, plan,
):
    org, _, connection = make_connected(
        sandbox, origin=origin, provider=provider, plan=plan,
    )
    assert confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    ) is False
    sandbox.expire_all()
    assert org.billing_provider == provider
    assert org.plan == plan


@pytest.mark.parametrize("legacy_field", [
    "billing_customer_id", "billing_subscription_id",
    "billing_price_id", "pending_plan",
])
def test_legacy_contract_references_block_channel_takeover(sandbox, legacy_field):
    org, _, connection = make_connected(sandbox)
    setattr(org, legacy_field, "existing-contract")
    sandbox.commit()
    assert confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    ) is False
    assert org.billing_provider is None


def test_revoked_or_paused_install_cannot_confirm_shopify_channel(sandbox):
    org, store, connection = make_connected(sandbox)
    connection.status = "revoked"
    sandbox.commit()
    assert not confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    )
    connection.status = "connected"
    store.active = False
    sandbox.commit()
    assert not confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    )


def test_second_shopify_binding_prevents_organization_channel_conversion(sandbox):
    org, _, connection = make_connected(sandbox)
    second = Store(
        organization_id=org.id, name="Other Store", slug="other-shop",
        country_code="CO", currency="COP", timezone="UTC", active=False,
    )
    sandbox.add(second)
    sandbox.flush()
    sandbox.add(CommerceConnection(
        organization_id=org.id, store_id=second.id,
        provider="shopify", external_store_url="other-shop.myshopify.com",
        status="revoked",
    ))
    sandbox.commit()
    assert not confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id,
    )


def test_foreign_connection_id_cannot_switch_org(sandbox):
    org, _, connection = make_connected(sandbox)
    assert not confirm_shopify_install_billing(
        sandbox, organization_id=org.id, connection_id=connection.id + 998,
    )
    assert not confirm_shopify_install_billing(
        sandbox, organization_id=org.id + 998, connection_id=connection.id,
    )


def test_shopify_public_untrusted_url_cannot_claim_a_billing_channel(sandbox):
    org, _, connection = make_connected(sandbox)
    assert org.billing_provider is None
    # The public handoff does not invoke the privileged channel claim.
    from app.api.shopify import shopify_install_handoff
    with patch("app.api.shopify.svc_process_oauth_callback") as process:
        response = shopify_install_handoff(shop="verified-store.myshopify.com")
    assert response.status_code == 303
    process.assert_not_called()
    sandbox.expire_all()
    assert org.billing_provider is None



@pytest.mark.parametrize(
    "channel,expected_provider",
    [("direct", "paddle"), ("shopify_install", None)],
)
def test_provision_endpoint_assigns_channel_and_does_not_mutate_on_retry(
    sandbox, channel, expected_provider,
):
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request

    from app.api.auth import provision_registration
    from app.models import OrganizationMembership

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="synthetic-cognito-token",
    )
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/register/provision",
        "headers": [],
    })
    payload = RegistrationProvisionRequest(
        name="Merchant Owner",
        organization_name="Synthetic Merchant",
        registration_channel=channel,
    )
    with patch(
        "app.api.auth.verify_cognito_access_token",
        return_value={"sub": "synthetic-user-sub"},
    ), patch("boto3.client") as cognito_factory, patch(
        "app.services.product_analytics.track_signup_completed"
    ):
        cognito_factory.return_value.get_user.return_value = {
            "UserAttributes": [
                {"Name": "email", "Value": "merchant@example.com"},
                {"Name": "email_verified", "Value": "true"},
            ]
        }
        result = provision_registration(
            request=request, payload=payload, credentials=credentials,
            db=sandbox,
        )
        assert result["created"] is True
        org = sandbox.get(Organization, result["organization"]["id"])
        assert org.billing_provider == expected_provider
        assert org.billing_onboarding_channel == channel
        assert org.plan == "trial"
        assert sandbox.query(OrganizationMembership).count() == 1

        # A replay must never change the original billing origin, even if
        # the client now claims the opposite signup channel.
        retry_payload = RegistrationProvisionRequest(
            name="Merchant Owner",
            organization_name="Synthetic Merchant",
            registration_channel=(
                "shopify_install" if channel == "direct" else "direct"
            ),
        )
        repeated = provision_registration(
            request=request, payload=retry_payload, credentials=credentials,
            db=sandbox,
        )
    assert repeated["created"] is False
    sandbox.expire_all()
    assert org.billing_provider == expected_provider
    assert org.billing_onboarding_channel == channel
    assert sandbox.query(Organization).count() == 1
