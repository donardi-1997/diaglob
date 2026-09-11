"""Boundary tests for the legacy shared Knowledge cleanup path."""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import bedrock_knowledge_base as facade
from app.db import Base
from app.knowledge_provisioning.errors import BedrockProvisioningError
from app.knowledge_provisioning.legacy import (
    LEGACY_KNOWLEDGE_INFRASTRUCTURE,
    LegacyCleanupOperations,
    cleanup_verified_legacy_resources,
    is_verified_legacy_parent,
    validate_legacy_data_source_ownership,
)
from app.models import KnowledgeBase, KnowledgeSource, Organization


LEGACY_KB_ID = LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"]
KNOWLEDGE_BUCKET = "diaglob-knowledge-test"

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_legacy_kb(db):
    organization = Organization(
        name="Legacy Boundary Org",
        slug="legacy-boundary-org",
        plan="starter",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()
    knowledge_base = KnowledgeBase(
        organization_id=organization.id,
        name="Legacy KB",
        scope="organization",
        external_status="deleting",
        external_id=LEGACY_KB_ID,
        external_data_source_id="LEGACYDS1",
        active=True,
    )
    db.add(knowledge_base)
    db.flush()
    source = KnowledgeSource(
        organization_id=organization.id,
        knowledge_base_id=knowledge_base.id,
        name="Legacy source",
        source_type="file",
    )
    db.add(source)
    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base, source.id


def _remote_kb():
    return {"knowledgeBaseId": LEGACY_KB_ID}


def _remote_ds(org_id: int, kb_id: int):
    return {
        "knowledgeBaseId": LEGACY_KB_ID,
        "dataSourceId": "LEGACYDS1",
        "status": "AVAILABLE",
        "dataSourceConfiguration": {
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{KNOWLEDGE_BUCKET}",
                "inclusionPrefixes": [
                    f"organizations/{org_id}/knowledge-bases/{kb_id}/documents/"
                ],
            },
        },
    }


def test_legacy_parent_match_is_exact():
    assert is_verified_legacy_parent(LEGACY_KB_ID) is True
    assert is_verified_legacy_parent("OTHER") is False
    assert is_verified_legacy_parent("") is False


def test_legacy_ownership_accepts_exact_tenant_scope():
    validate_legacy_data_source_ownership(
        _remote_ds(7, 11),
        _remote_kb(),
        7,
        11,
        legacy_kb_id=LEGACY_KB_ID,
        knowledge_bucket=KNOWLEDGE_BUCKET,
        expected_prefix="organizations/7/knowledge-bases/11/documents/",
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda ds, kb: kb.update(knowledgeBaseId="OTHER"),
        lambda ds, kb: ds.update(knowledgeBaseId="OTHER"),
        lambda ds, kb: ds["dataSourceConfiguration"].update(type="WEB"),
        lambda ds, kb: ds["dataSourceConfiguration"]["s3Configuration"].update(
            bucketArn="arn:aws:s3:::other-bucket"
        ),
        lambda ds, kb: ds["dataSourceConfiguration"]["s3Configuration"].update(
            inclusionPrefixes=["organizations/7/"]
        ),
    ],
)
def test_legacy_ownership_rejects_any_scope_mismatch(mutator):
    remote_ds = _remote_ds(7, 11)
    remote_kb = _remote_kb()
    mutator(remote_ds, remote_kb)

    with pytest.raises(BedrockProvisioningError) as exc:
        validate_legacy_data_source_ownership(
            remote_ds,
            remote_kb,
            7,
            11,
            legacy_kb_id=LEGACY_KB_ID,
            knowledge_bucket=KNOWLEDGE_BUCKET,
            expected_prefix="organizations/7/knowledge-bases/11/documents/",
        )

    assert exc.value.code == "resource_ownership_mismatch"


def test_cleanup_deletes_only_verified_ds_prefix_and_local_rows(db):
    knowledge_base, source_id = _make_legacy_kb(db)
    remote_kb = _remote_kb()
    remote_ds = _remote_ds(knowledge_base.organization_id, knowledge_base.id)

    get_data_source = MagicMock(side_effect=[remote_ds, None])
    delete_data_source = MagicMock()
    validate_ownership = MagicMock()
    delete_prefix = MagicMock()

    operations = LegacyCleanupOperations(
        get_knowledge_base=MagicMock(return_value=remote_kb),
        get_data_source=get_data_source,
        delete_data_source=delete_data_source,
        validate_data_source_ownership=validate_ownership,
        delete_knowledge_prefix=delete_prefix,
        commit_state=lambda session, *_args: session.commit(),
        sleep_between_attempts=MagicMock(),
        client_error_code=lambda _error: None,
        log_aws_error=MagicMock(),
        aws_provisioning_error=MagicMock(),
    )

    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id
    cleanup_verified_legacy_resources(
        db,
        knowledge_base,
        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,
        wait_attempts=2,
        operations=operations,
    )

    validate_ownership.assert_called_once_with(remote_ds, remote_kb, org_id, kb_id)
    delete_data_source.assert_called_once_with(LEGACY_KB_ID, "LEGACYDS1")
    delete_prefix.assert_called_once_with(org_id, kb_id)
    assert db.get(KnowledgeBase, kb_id) is None
    assert db.get(KnowledgeSource, source_id) is None


def test_cleanup_tolerates_provider_already_missing_on_delete(db):
    knowledge_base, _ = _make_legacy_kb(db)
    remote_kb = _remote_kb()
    remote_ds = _remote_ds(knowledge_base.organization_id, knowledge_base.id)
    missing = ClientError(
        {
            "Error": {
                "Code": "ResourceNotFoundException",
                "Message": "already absent",
            }
        },
        "DeleteDataSource",
    )
    operations = LegacyCleanupOperations(
        get_knowledge_base=MagicMock(return_value=remote_kb),
        get_data_source=MagicMock(side_effect=[remote_ds, None]),
        delete_data_source=MagicMock(side_effect=missing),
        validate_data_source_ownership=MagicMock(),
        delete_knowledge_prefix=MagicMock(),
        commit_state=lambda session, *_args: session.commit(),
        sleep_between_attempts=MagicMock(),
        client_error_code=lambda error: error.response["Error"]["Code"],
        log_aws_error=MagicMock(),
        aws_provisioning_error=MagicMock(),
    )

    kb_id = knowledge_base.id
    cleanup_verified_legacy_resources(
        db,
        knowledge_base,
        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,
        wait_attempts=1,
        operations=operations,
    )

    assert db.get(KnowledgeBase, kb_id) is None
    operations.log_aws_error.assert_not_called()
    operations.aws_provisioning_error.assert_not_called()


def test_facade_captures_legacy_dependencies_at_invocation_time(monkeypatch):
    get_kb = MagicMock()
    get_ds = MagicMock()
    validate = MagicMock()
    delete_prefix = MagicMock()

    monkeypatch.setattr(facade, "get_bedrock_knowledge_base", get_kb)
    monkeypatch.setattr(facade, "get_bedrock_data_source", get_ds)
    monkeypatch.setattr(facade, "validate_legacy_data_source_ownership", validate)
    monkeypatch.setattr(facade, "delete_knowledge_prefix", delete_prefix)

    operations = facade._legacy_cleanup_operations()

    assert operations.get_knowledge_base is get_kb
    assert operations.get_data_source is get_ds
    assert operations.validate_data_source_ownership is validate
    assert operations.delete_knowledge_prefix is delete_prefix
