from app import models
from app.model_domains.commerce import CommerceConnection
from app.model_domains.google import GoogleConnection, GoogleOAuthState
from app.model_domains.knowledge import KnowledgeBase, KnowledgeSource
from app.model_domains.messaging import (
    Conversation,
    Message,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from app.model_domains.oauth import NuvemshopOAuthState, ShopifyOAuthState
from app.model_domains.payments import PaymentConnection, PaymentTransaction
from app.model_domains.tenancy import (
    MembershipStore,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Store,
    User,
)


def test_tenancy_domain_exports_legacy_model_classes():
    assert Organization is models.Organization
    assert Store is models.Store
    assert User is models.User
    assert OrganizationInvitation is models.OrganizationInvitation
    assert OrganizationMembership is models.OrganizationMembership
    assert MembershipStore is models.MembershipStore


def test_knowledge_domain_exports_legacy_model_classes():
    assert KnowledgeBase is models.KnowledgeBase
    assert KnowledgeSource is models.KnowledgeSource


def test_messaging_domain_exports_legacy_model_classes():
    assert Conversation is models.Conversation
    assert Message is models.Message
    assert WhatsAppConnection is models.WhatsAppConnection
    assert WhatsAppMessageTemplate is models.WhatsAppMessageTemplate


def test_oauth_domain_exports_legacy_model_classes():
    assert ShopifyOAuthState is models.ShopifyOAuthState
    assert NuvemshopOAuthState is models.NuvemshopOAuthState


def test_oauth_models_are_physically_defined_in_domain_module():
    assert ShopifyOAuthState.__module__ == "app.model_domains.oauth"
    assert NuvemshopOAuthState.__module__ == "app.model_domains.oauth"


def test_google_domain_exports_legacy_model_classes():
    assert GoogleOAuthState is models.GoogleOAuthState
    assert GoogleConnection is models.GoogleConnection


def test_google_models_are_physically_defined_in_domain_module():
    assert GoogleOAuthState.__module__ == "app.model_domains.google"
    assert GoogleConnection.__module__ == "app.model_domains.google"


def test_payment_domain_exports_legacy_model_classes():
    assert PaymentConnection is models.PaymentConnection
    assert PaymentTransaction is models.PaymentTransaction


def test_payment_models_are_physically_defined_in_domain_module():
    assert PaymentConnection.__module__ == "app.model_domains.payments"
    assert PaymentTransaction.__module__ == "app.model_domains.payments"


def test_commerce_domain_exports_legacy_model_class():
    assert CommerceConnection is models.CommerceConnection


def test_commerce_model_is_physically_defined_in_domain_module():
    assert CommerceConnection.__module__ == "app.model_domains.commerce"


def test_domain_imports_do_not_duplicate_sqlalchemy_tables():
    exported_models = [
        Organization,
        Store,
        User,
        OrganizationInvitation,
        OrganizationMembership,
        MembershipStore,
        KnowledgeBase,
        KnowledgeSource,
        Conversation,
        Message,
        WhatsAppConnection,
        WhatsAppMessageTemplate,
        ShopifyOAuthState,
        NuvemshopOAuthState,
        GoogleOAuthState,
        GoogleConnection,
        PaymentConnection,
        PaymentTransaction,
        CommerceConnection,
    ]

    for model in exported_models:
        assert model.__table__ is models.Base.metadata.tables[model.__tablename__]


def test_oauth_table_contracts_are_preserved():
    shopify = ShopifyOAuthState.__table__
    nuvemshop = NuvemshopOAuthState.__table__

    assert shopify.name == "shopify_oauth_states"
    assert nuvemshop.name == "nuvemshop_oauth_states"
    assert set(shopify.columns.keys()) == {
        "id",
        "state",
        "organization_id",
        "store_id",
        "user_id",
        "shop_domain",
        "expires_at",
        "used",
        "created_at",
    }
    assert set(nuvemshop.columns.keys()) == {
        "id",
        "state",
        "organization_id",
        "store_id",
        "user_id",
        "expires_at",
        "used",
        "created_at",
    }


def test_google_table_contracts_are_preserved():
    oauth = GoogleOAuthState.__table__
    connection = GoogleConnection.__table__

    assert oauth.name == "google_oauth_states"
    assert connection.name == "google_connections"
    assert set(oauth.columns.keys()) == {
        "id",
        "state_token",
        "organization_id",
        "user_id",
        "scopes",
        "expires_at",
        "used",
        "created_at",
    }
    assert set(connection.columns.keys()) == {
        "id",
        "organization_id",
        "user_id",
        "email",
        "access_token_encrypted",
        "refresh_token_encrypted",
        "token_expiry",
        "scopes",
        "status",
        "connected_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }


def test_payment_table_contracts_are_preserved():
    connection = PaymentConnection.__table__
    transaction = PaymentTransaction.__table__

    assert connection.name == "payment_connections"
    assert transaction.name == "payment_transactions"
    assert set(connection.columns.keys()) == {
        "id",
        "organization_id",
        "store_id",
        "provider",
        "status",
        "environment",
        "client_id_encrypted",
        "client_secret_encrypted",
        "webhook_secret_encrypted",
        "merchant_reference",
        "last_event_id",
        "last_event_at",
        "last_error",
        "connected_at",
        "created_at",
        "updated_at",
    }
    assert set(transaction.columns.keys()) == {
        "id",
        "organization_id",
        "store_id",
        "order_id",
        "provider",
        "provider_transaction_id",
        "merchant_reference",
        "idempotency_key",
        "amount",
        "currency",
        "status",
        "payment_method",
        "customer_phone",
        "provider_status",
        "provider_error_code",
        "provider_error_message",
        "expires_at",
        "paid_at",
        "reversed_at",
        "created_at",
        "updated_at",
    }
    assert any(
        constraint.name == "uq_payment_connection_store_provider"
        for constraint in connection.constraints
    )
    assert any(
        constraint.name == "uq_payment_txn_org_idempotency"
        for constraint in transaction.constraints
    )
    assert any(
        index.name == "ix_payment_txn_provider_txn_id"
        for index in transaction.indexes
    )


def test_commerce_table_contract_is_preserved():
    connection = CommerceConnection.__table__

    assert connection.name == "commerce_connections"
    assert set(connection.columns.keys()) == {
        "id",
        "organization_id",
        "store_id",
        "provider",
        "external_store_url",
        "access_token_encrypted",
        "refresh_token_encrypted",
        "api_key_encrypted",
        "api_secret_encrypted",
        "access_token_expires_at",
        "refresh_token_expires_at",
        "scopes",
        "status",
        "connected_at",
        "last_sync_at",
        "last_error",
        "created_at",
        "updated_at",
    }
    constraint_names = {constraint.name for constraint in connection.constraints}
    assert "uq_commerce_connection_store" in constraint_names
    assert "uq_commerce_provider_store_url" in constraint_names
