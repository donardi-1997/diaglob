"""Boundary tests for the physically extracted Knowledge model domain."""

from sqlalchemy import DateTime, inspect

from app.db import Base
from app.model_domains import knowledge
from app.model_domains import tenancy
from app import models as legacy


def test_legacy_model_surface_reexports_knowledge_models():
    assert legacy.KnowledgeBase is knowledge.KnowledgeBase
    assert legacy.KnowledgeSource is knowledge.KnowledgeSource
    assert legacy.agent_knowledge_bases is knowledge.agent_knowledge_bases


def test_knowledge_models_are_physically_owned_by_domain_module():
    assert knowledge.KnowledgeBase.__module__ == "app.model_domains.knowledge"
    assert knowledge.KnowledgeSource.__module__ == "app.model_domains.knowledge"


def test_knowledge_tables_are_registered_once_in_shared_metadata():
    assert Base.metadata.tables["knowledge_bases"] is knowledge.KnowledgeBase.__table__
    assert Base.metadata.tables["knowledge_sources"] is knowledge.KnowledgeSource.__table__
    assert (
        Base.metadata.tables["agent_knowledge_bases"]
        is knowledge.agent_knowledge_bases
    )


def test_knowledge_relationship_secondaries_keep_same_table_identity():
    knowledge_relationships = inspect(knowledge.KnowledgeBase).relationships
    agent_relationships = inspect(legacy.Agent).relationships

    assert (
        knowledge_relationships.stores.secondary
        is tenancy.knowledge_base_stores
    )
    assert (
        knowledge_relationships.agents.secondary
        is knowledge.agent_knowledge_bases
    )
    assert (
        agent_relationships.knowledge_bases.secondary
        is knowledge.agent_knowledge_bases
    )


def test_knowledge_base_provisioning_column_contract_is_preserved():
    columns = knowledge.KnowledgeBase.__table__.c

    assert columns.external_id.type.length == 150
    assert columns.external_data_source_id.type.length == 150
    assert columns.external_status.type.length == 30
    assert columns.external_status.default.arg == "pending"
    assert str(columns.external_status.server_default.arg) == "pending"
    assert columns.external_status.nullable is True
    assert columns.external_last_error.nullable is True
    assert columns.provisioning_stage.type.length == 50

    assert isinstance(columns.provisioning_started_at.type, DateTime)
    assert columns.provisioning_started_at.type.timezone is True
    assert isinstance(columns.provisioning_stage_started_at.type, DateTime)
    assert columns.provisioning_stage_started_at.type.timezone is True


def test_knowledge_source_sync_and_parent_contract_is_preserved():
    columns = knowledge.KnowledgeSource.__table__.c

    assert columns.source_type.default.arg == "file"
    assert columns.status.default.arg == "uploaded"
    assert columns.sync_generation.default.arg == 0
    assert columns.s3_bucket.nullable is False
    assert columns.s3_key.nullable is False
    assert columns.external_size.nullable is True
    assert columns.parent_source_id.nullable is True
    assert columns.parent_source_id.index is True

    parent_fk = next(iter(columns.parent_source_id.foreign_keys))
    assert parent_fk.target_fullname == "knowledge_sources.id"
    assert parent_fk.ondelete == "SET NULL"


def test_knowledge_foreign_keys_keep_tenant_and_parent_delete_semantics():
    kb_columns = knowledge.KnowledgeBase.__table__.c
    source_columns = knowledge.KnowledgeSource.__table__.c

    org_fk = next(iter(kb_columns.organization_id.foreign_keys))
    source_org_fk = next(iter(source_columns.organization_id.foreign_keys))
    source_kb_fk = next(iter(source_columns.knowledge_base_id.foreign_keys))

    assert org_fk.target_fullname == "organizations.id"
    assert org_fk.ondelete == "CASCADE"
    assert source_org_fk.target_fullname == "organizations.id"
    assert source_org_fk.ondelete == "CASCADE"
    assert source_kb_fk.target_fullname == "knowledge_bases.id"
    assert source_kb_fk.ondelete == "CASCADE"
