"""Boundary tests for the physically extracted Messaging model domain."""

from sqlalchemy import inspect

from app.db import Base
from app.model_domains import messaging
from app import models as legacy


def test_legacy_model_surface_reexports_messaging_models():
    assert legacy.Conversation is messaging.Conversation
    assert legacy.Message is messaging.Message
    assert legacy.WhatsAppConnection is messaging.WhatsAppConnection
    assert legacy.WhatsAppMessageTemplate is messaging.WhatsAppMessageTemplate


def test_messaging_models_are_physically_owned_by_domain_module():
    assert messaging.Conversation.__module__ == "app.model_domains.messaging"
    assert messaging.Message.__module__ == "app.model_domains.messaging"
    assert messaging.WhatsAppConnection.__module__ == "app.model_domains.messaging"
    assert (
        messaging.WhatsAppMessageTemplate.__module__
        == "app.model_domains.messaging"
    )


def test_messaging_tables_are_registered_once_in_shared_metadata():
    expected = {
        "conversations": messaging.Conversation.__table__,
        "messages": messaging.Message.__table__,
        "whatsapp_connections": messaging.WhatsAppConnection.__table__,
        "whatsapp_message_templates": messaging.WhatsAppMessageTemplate.__table__,
    }

    for table_name, table in expected.items():
        assert Base.metadata.tables[table_name] is table


def test_conversation_relationship_contract_is_preserved():
    conversation_relationships = inspect(messaging.Conversation).relationships
    agent_relationships = inspect(legacy.Agent).relationships

    assert conversation_relationships.organization.back_populates == "conversations"
    assert conversation_relationships.store.back_populates == "conversations"
    assert conversation_relationships.customer.back_populates == "conversations"
    assert conversation_relationships.assigned_agent.back_populates == "conversations"
    assert conversation_relationships.messages.back_populates == "conversation"
    assert "delete-orphan" in conversation_relationships.messages.cascade
    assert agent_relationships.conversations.back_populates == "assigned_agent"


def test_conversation_and_message_defaults_and_delete_semantics_are_preserved():
    conversation_columns = messaging.Conversation.__table__.c
    message_columns = messaging.Message.__table__.c

    assert conversation_columns.channel.default.arg == "internal"
    assert conversation_columns.preview.default.arg == ""
    assert conversation_columns.unread.default.arg == 0
    assert conversation_columns.mode.default.arg == "ai"
    assert conversation_columns.tags.default.arg == ""

    assert message_columns.provider.default.arg == "internal"
    assert message_columns.delivery_status.default.arg == "delivered"

    conversation_agent_fk = next(iter(conversation_columns.agent_id.foreign_keys))
    message_agent_fk = next(iter(message_columns.agent_id.foreign_keys))
    message_conversation_fk = next(
        iter(message_columns.conversation_id.foreign_keys)
    )

    assert conversation_agent_fk.target_fullname == "agents.id"
    assert conversation_agent_fk.ondelete == "SET NULL"
    assert message_agent_fk.target_fullname == "agents.id"
    assert message_agent_fk.ondelete == "SET NULL"
    assert message_conversation_fk.target_fullname == "conversations.id"
    assert message_conversation_fk.ondelete == "CASCADE"


def test_messaging_unique_constraint_names_are_preserved():
    message_constraints = {
        constraint.name for constraint in messaging.Message.__table__.constraints
    }
    connection_constraints = {
        constraint.name
        for constraint in messaging.WhatsAppConnection.__table__.constraints
    }
    template_constraints = {
        constraint.name
        for constraint in messaging.WhatsAppMessageTemplate.__table__.constraints
    }

    assert "uq_message_provider_external" in message_constraints
    assert "uq_whatsapp_connection_store" in connection_constraints
    assert "uq_whatsapp_phone_number" in connection_constraints
    assert (
        "uq_whatsapp_template_connection_name_language"
        in template_constraints
    )


def test_whatsapp_model_contract_is_preserved():
    connection_columns = messaging.WhatsAppConnection.__table__.c
    template_columns = messaging.WhatsAppMessageTemplate.__table__.c

    assert connection_columns.status.default.arg == "connected"
    assert connection_columns.store_id.unique is True
    assert connection_columns.phone_number_id.unique is True
    assert connection_columns.access_token_encrypted.nullable is False
    assert connection_columns.verify_token.nullable is False

    assert template_columns.components.default.arg is dict
    assert template_columns.components.nullable is False
    assert template_columns.provider_template_name.type.length == 512
    assert template_columns.language_code.type.length == 32

    template_connection_fk = next(
        iter(template_columns.whatsapp_connection_id.foreign_keys)
    )
    assert template_connection_fk.target_fullname == "whatsapp_connections.id"
    assert template_connection_fk.ondelete == "CASCADE"
