from app import models
from app.model_domains.knowledge import KnowledgeBase, KnowledgeSource
from app.model_domains.messaging import (
    Conversation,
    Message,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
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
    ]

    for model in exported_models:
        assert model.__table__ is models.Base.metadata.tables[model.__tablename__]
