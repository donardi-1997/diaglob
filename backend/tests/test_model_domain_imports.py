from app import models
from app.model_domains.google import GoogleConnection, GoogleOAuthState
from app.model_domains.knowledge import KnowledgeBase, KnowledgeSource
from app.model_domains.messaging import (
    Conversation,
    Message,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from app.model_domains.oauth import NuvemshopOAuthState, ShopifyOAuthState
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
