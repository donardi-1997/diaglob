"""Synthetic signed-identity lifecycle: connected, uninstalled and unresolved."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CommerceConnection, Organization, ShopifyPrivacyRequest,
    ShopifyPrivacyShopIdentity, Store,
)
from app.services.shopify_compliance_webhooks import (
    process_shopify_compliance_webhook,
)
from app.services.shopify_privacy_installation_identity import (
    ShopifyPrivacyShopIdentityError,
    bind_signed_shopify_privacy_identity,
)
from app.services.shopify_uninstall import process_shopify_uninstall


SHOP = "historical-shop.myshopify.com"


@pytest.fixture
def database(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Privacy identity", slug="privacy-identity",
                           plan="starter")
        db.add(org)
        db.flush()
        store = Store(
            name="Original", slug="original", organization_id=org.id,
            country_code="CO", currency="COP", timezone="America/Bogota",
            shopify_domain=SHOP,
        )
        db.add(store)
        db.flush()
        connection = CommerceConnection(
            organization_id=org.id, store_id=store.id,
            provider="shopify", external_store_url=SHOP,
            status="connected", scopes="", access_token_encrypted="SYNTHETIC_TOKEN",
            connected_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(connection)
        db.commit()
        yield db, connection
    engine.dispose()


def _privacy(db, *, shop_id=321, domain=SHOP, delivery="receipt-1",
             topic="customers/data_request"):
    return process_shopify_compliance_webhook(
        db, topic=topic, webhook_id=delivery,
        payload={
            "shop_id": shop_id, "shop_domain": domain,
            "customer": {"id": 9001},
        },
        header_shop_domain=domain,
    )


def _uninstall(db):
    return process_shopify_uninstall(
        db, topic="app/uninstalled", header_shop_domain=SHOP,
        triggered_at=datetime.utcnow().isoformat() + "Z",
        payload={"id": 321, "myshopify_domain": SHOP},
    )


def test_signed_uninstall_first_creates_mapping_for_later_gdpr_request(database):
    db, connection = database
    org_id, store_id = connection.organization_id, connection.store_id
    assert db.query(ShopifyPrivacyShopIdentity).count() == 0
    assert _uninstall(db)["action"] == "revoked"
    db.refresh(connection)
    assert connection.status == "revoked"
    assert connection.access_token_encrypted is None
    ledger = db.query(ShopifyPrivacyShopIdentity).one()
    assert (ledger.shop_id, ledger.shop_domain) == ("321", SHOP)
    assert (ledger.organization_id, ledger.store_id) == (org_id, store_id)
    assert ledger.provenance == "hmac_uninstall"
    assert ledger.uninstalled_at is not None
    result = _privacy(db, delivery="after-uninstall", topic="shop/redact")
    assert result["store_connected"] is False
    assert result["store_identity_resolved"] is True
    receipt = db.query(ShopifyPrivacyRequest).one()
    assert (receipt.organization_id, receipt.store_id) == (org_id, store_id)
    assert receipt.completed_at is None
    assert receipt.status == "pending_policy_review"
    assert db.query(ShopifyPrivacyShopIdentity).count() == 1
    assert connection.status == "revoked"


def test_compliance_while_connected_remains_bound_after_uninstall(database):
    db, connection = database
    first = _privacy(db, delivery="before-uninstall")
    assert first["store_connected"] is True
    assert db.query(ShopifyPrivacyShopIdentity).one().provenance == "hmac_compliance"
    assert _uninstall(db)["action"] == "revoked"
    second = _privacy(db, delivery="after-uninstall")
    assert second["store_connected"] is False
    assert second["store_identity_resolved"] is True
    receipts = db.query(ShopifyPrivacyRequest).order_by(
        ShopifyPrivacyRequest.id,
    ).all()
    assert len(receipts) == 2
    assert {(x.organization_id, x.store_id) for x in receipts} == {
        (connection.organization_id, connection.store_id),
    }
    assert db.query(ShopifyPrivacyShopIdentity).count() == 1


@pytest.mark.parametrize("shop_id,domain", [
    (322, SHOP),
    (321, "wrong-historical.myshopify.com"),
])
def test_conflicting_signed_shop_id_or_domain_never_inherits_tenant(
    database, shop_id, domain,
):
    db, connection = database
    _uninstall(db)
    result = _privacy(db, shop_id=shop_id, domain=domain, delivery="conflict")
    assert result["store_connected"] is False
    receipt = db.query(ShopifyPrivacyRequest).one()
    assert (receipt.organization_id, receipt.store_id) == (None, None)
    assert receipt.last_error_code == "SIGNED_SHOP_IDENTITY_CONFLICT"
    assert db.query(ShopifyPrivacyShopIdentity).count() == 1
    assert connection.status == "revoked"


def test_unknown_shop_after_uninstall_remains_unbound(database):
    db, _ = database
    _uninstall(db)
    result = _privacy(
        db, shop_id=555, domain="completely-new.myshopify.com",
        delivery="unknown",
    )
    assert result["store_connected"] is False
    receipt = db.query(ShopifyPrivacyRequest).one()
    assert receipt.organization_id is None
    assert receipt.last_error_code is None
    assert db.query(ShopifyPrivacyShopIdentity).count() == 1


def test_rebinding_same_signed_shop_to_other_tenant_is_not_allowed(database):
    db, connection = database
    _privacy(db, delivery="original")
    original = (connection.organization_id, connection.store_id)
    other_org = Organization(name="Different", slug="different", plan="starter")
    db.add(other_org)
    db.flush()
    other_store = Store(
        organization_id=other_org.id, name="Other", slug="other",
        country_code="CO", currency="COP", timezone="UTC",
        shopify_domain=SHOP,
    )
    db.add(other_store)
    db.flush()
    connection.organization_id = other_org.id
    connection.store_id = other_store.id
    db.commit()
    result = _privacy(db, delivery="attempt-rebind")
    assert result["store_connected"] is False
    receipts = db.query(ShopifyPrivacyRequest).order_by(
        ShopifyPrivacyRequest.id,
    ).all()
    assert (receipts[0].organization_id, receipts[0].store_id) == original
    assert (receipts[1].organization_id, receipts[1].store_id) == (None, None)
    assert receipts[1].last_error_code == "SIGNED_SHOP_TENANT_REBOUND"
    identity = db.query(ShopifyPrivacyShopIdentity).one()
    assert (identity.organization_id, identity.store_id) == original


def test_unverified_identity_or_wrong_connection_rejected_without_new_mapping(database):
    db, connection = database
    with pytest.raises(
        ShopifyPrivacyShopIdentityError, match="INVALID_SIGNED_SHOP_ID",
    ):
        bind_signed_shopify_privacy_identity(
            db, shop_id="not-numeric", shop_domain=SHOP, connection=connection,
        )
    connection.status = "revoked"
    with pytest.raises(
        ShopifyPrivacyShopIdentityError, match="SHOPIFY_CONNECTION_IDENTITY_INVALID",
    ):
        bind_signed_shopify_privacy_identity(
            db, shop_id="321", shop_domain=SHOP, connection=connection,
        )
    assert db.query(ShopifyPrivacyShopIdentity).count() == 0


def test_receipt_deduplication_does_not_duplicate_identity_ledger(database):
    db, _ = database
    before = _privacy(db, delivery="same-delivery")
    after = _privacy(db, delivery="same-delivery")
    assert before["action"] == "recorded"
    assert after["action"] == "duplicate"
    assert db.query(ShopifyPrivacyRequest).count() == 1
    assert db.query(ShopifyPrivacyShopIdentity).count() == 1
