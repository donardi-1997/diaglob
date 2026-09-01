"""Tests for isolated Bedrock and S3 Vectors provisioning."""

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bedrock_knowledge_base as provisioning
from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    KnowledgeBase,
    KnowledgeSource,
    Organization,
    OrganizationMembership,
    User,
)


VECTOR_BUCKET_NAME = "diaglob-vectors-test"
VECTOR_BUCKET_ARN = (
    "arn:aws:s3vectors:us-east-2:123456789012:bucket/"
    f"{VECTOR_BUCKET_NAME}"
)
ROLE_ARN = "arn:aws:iam::123456789012:role/DiaglobBedrockKnowledgeBaseRole"
MODEL_ARN = (
    "arn:aws:bedrock:us-east-2::foundation-model/"
    "amazon.titan-embed-text-v2:0"
)
KNOWLEDGE_BUCKET = "diaglob-knowledge-test"
BEDROCK_KB_ID = "ABCDEFGHIJ"
BEDROCK_DS_ID = "KLMNOPQRST"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

TEST_DATABASE_URL = "sqlite:///./test_bedrock_knowledge_base.db"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def _index_name(kb_id: int = 1) -> str:
    return f"diaglob-prod-kb-{kb_id}"


def _index_arn(kb_id: int = 1) -> str:
    return f"{VECTOR_BUCKET_ARN}/index/{_index_name(kb_id)}"


def _tags(org_id: int = 1, kb_id: int = 1) -> dict[str, str]:
    return {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": "production",
        "diaglob:organization_id": str(org_id),
        "diaglob:knowledge_base_id": str(kb_id),
    }


def _index(org_id: int = 1, kb_id: int = 1, dimension: int = 1024):
    return {
        "vectorBucketName": VECTOR_BUCKET_NAME,
        "indexName": _index_name(kb_id),
        "indexArn": _index_arn(kb_id),
        "creationTime": NOW,
        "dataType": "float32",
        "dimension": dimension,
        "distanceMetric": "cosine",
        "metadataConfiguration": {
            "nonFilterableMetadataKeys": [
                "AMAZON_BEDROCK_TEXT",
                "AMAZON_BEDROCK_METADATA",
            ]
        },
    }


def _kb_name(org_id: int = 1, kb_id: int = 1) -> str:
    return f"diaglob-prod-org-{org_id}-kb-{kb_id}"


def _kb_arn(kb_id: str = BEDROCK_KB_ID) -> str:
    return f"arn:aws:bedrock:us-east-2:123456789012:knowledge-base/{kb_id}"


def _kb_configuration():
    return {
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": MODEL_ARN,
            "embeddingModelConfiguration": {
                "bedrockEmbeddingModelConfiguration": {
                    "dimensions": 1024,
                    "embeddingDataType": "FLOAT32",
                }
            },
        },
    }


def _storage_configuration(kb_id: int = 1):
    return {
        "type": "S3_VECTORS",
        "s3VectorsConfiguration": {
            "vectorBucketArn": VECTOR_BUCKET_ARN,
            "indexArn": _index_arn(kb_id),
        },
    }


def _bedrock_kb(
    org_id: int = 1,
    kb_id: int = 1,
    status: str = "ACTIVE",
):
    return {
        "knowledgeBaseId": BEDROCK_KB_ID,
        "name": _kb_name(org_id, kb_id),
        "knowledgeBaseArn": _kb_arn(),
        "description": f"Diaglob Knowledge Base for organization {org_id}, KB {kb_id}",
        "roleArn": ROLE_ARN,
        "knowledgeBaseConfiguration": _kb_configuration(),
        "storageConfiguration": _storage_configuration(kb_id),
        "status": status,
        "createdAt": NOW,
        "updatedAt": NOW,
    }


def _data_source_configuration(org_id: int = 1, kb_id: int = 1):
    return {
        "type": "S3",
        "s3Configuration": {
            "bucketArn": f"arn:aws:s3:::{KNOWLEDGE_BUCKET}",
            "inclusionPrefixes": [
                f"organizations/{org_id}/knowledge-bases/{kb_id}/documents/"
            ],
        },
    }


def _ingestion_configuration():
    return {
        "chunkingConfiguration": {
            "chunkingStrategy": "FIXED_SIZE",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 300,
                "overlapPercentage": 20,
            },
        }
    }


def _bedrock_ds(
    org_id: int = 1,
    kb_id: int = 1,
    status: str = "AVAILABLE",
    prefix: str | None = None,
):
    configuration = _data_source_configuration(org_id, kb_id)
    if prefix is not None:
        configuration["s3Configuration"]["inclusionPrefixes"] = [prefix]
    return {
        "knowledgeBaseId": BEDROCK_KB_ID,
        "dataSourceId": BEDROCK_DS_ID,
        "name": f"diaglob-prod-kb-{kb_id}-s3",
        "status": status,
        "description": f"Diaglob S3 Data Source for org {org_id}, KB {kb_id}",
        "dataSourceConfiguration": configuration,
        "vectorIngestionConfiguration": _ingestion_configuration(),
        "dataDeletionPolicy": "DELETE",
        "createdAt": NOW,
        "updatedAt": NOW,
    }


def _s3vectors_client():
    return boto3.client(
        "s3vectors",
        region_name="us-east-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _bedrock_client():
    return boto3.client(
        "bedrock-agent",
        region_name="us-east-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture(autouse=True)
def configured_provisioning(monkeypatch):
    monkeypatch.setattr(provisioning, "ENVIRONMENT", "production")
    monkeypatch.setattr(provisioning, "VECTOR_BUCKET_ARN", VECTOR_BUCKET_ARN)
    monkeypatch.setattr(
        provisioning, "BEDROCK_SERVICE_ROLE_ARN", ROLE_ARN
    )
    monkeypatch.setattr(provisioning, "EMBEDDING_MODEL_ARN", MODEL_ARN)
    monkeypatch.setattr(provisioning, "KNOWLEDGE_BUCKET", KNOWLEDGE_BUCKET)
    monkeypatch.setattr(provisioning, "RECOVERY_ATTEMPTS", 1)
    monkeypatch.setattr(provisioning, "WAIT_ATTEMPTS", 1)
    monkeypatch.setattr(provisioning, "POLL_INTERVAL_SECONDS", 0)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_org(db, slug: str = "bedrock-test"):
    org = Organization(
        name="Bedrock Test",
        slug=slug,
        plan="starter",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    return org


def _make_membership(db, org):
    user = User(
        email=f"{org.slug}@test.com",
        name="Provisioning Tester",
        external_auth_id=f"sub-{org.slug}",
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role="owner",
    )
    db.add(membership)
    db.flush()
    return membership


def _make_local_kb(
    db,
    org,
    status="pending",
    external_id=None,
    data_source_id=None,
):
    kb = KnowledgeBase(
        organization_id=org.id,
        name="Local KB",
        scope="organization",
        external_status=status,
        external_id=external_id,
        external_data_source_id=data_source_id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@pytest.fixture
def api_client(db):
    org = _make_org(db)
    membership = _make_membership(db, org)
    db.commit()
    original = dict(app.dependency_overrides)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: membership.user
    app.dependency_overrides[get_current_membership] = lambda: membership
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, org, membership
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_build_vector_index_name_uses_environment_without_pii():
    assert provisioning.build_vector_index_name("production", 42) == (
        "diaglob-prod-kb-42"
    )
    assert provisioning.build_vector_index_name("staging", 42) == (
        "diaglob-staging-kb-42"
    )


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("prod", "production"),
        ("production", "production"),
        ("dev", "development"),
        ("development", "development"),
        ("local", "development"),
        ("staging", "staging"),
        ("stage", "staging"),
        ("test", "test"),
        ("testing", "test"),
        ("  Production  ", "production"),
        ("  DEV  ", "development"),
    ],
)
def test_normalize_environment_maps_aliases(raw, canonical):
    assert provisioning.normalize_environment(raw) == canonical


def test_normalize_environment_rejects_none_and_empty():
    with pytest.raises(provisioning.BedrockProvisioningError) as exc:
        provisioning.normalize_environment(None)
    assert exc.value.code == "invalid_environment"
    with pytest.raises(provisioning.BedrockProvisioningError):
        provisioning.normalize_environment("")
    with pytest.raises(provisioning.BedrockProvisioningError):
        provisioning.normalize_environment("   ")


def test_normalize_environment_rejects_unknown_values():
    with pytest.raises(provisioning.BedrockProvisioningError) as exc:
        provisioning.normalize_environment("banana")
    assert exc.value.code == "invalid_environment"
    with pytest.raises(provisioning.BedrockProvisioningError):
        provisioning.normalize_environment("productionn")


def test_make_tags_use_canonical_environment():
    tags = provisioning._make_tags(1, 1)
    assert tags["diaglob:environment"] == "production"


def test_client_tokens_satisfy_bedrock_shape_constraints():
    token = provisioning._make_client_token("kb", 1, 1)
    assert 33 <= len(token) <= 256
    assert token[0].isalnum() and token[-1].isalnum()


def test_create_vector_index_success_uses_valid_stubber_payload():
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "create_index",
            {"indexArn": _index_arn()},
            {
                "vectorBucketArn": VECTOR_BUCKET_ARN,
                "indexName": _index_name(),
                "dataType": "float32",
                "dimension": 1024,
                "distanceMetric": "cosine",
                "metadataConfiguration": {
                    "nonFilterableMetadataKeys": [
                        "AMAZON_BEDROCK_TEXT",
                        "AMAZON_BEDROCK_METADATA",
                    ]
                },
                "tags": _tags(),
            },
        )
        stubber.add_response(
            "get_index", {"index": _index()}, {"indexArn": _index_arn()}
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _index_arn()},
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            result = provisioning.create_s3_vectors_index(1, 1)
    assert result["indexArn"] == _index_arn()


def test_create_vector_index_conflict_safely_reuses_owned_index():
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_index",
            service_error_code="ConflictException",
            http_status_code=409,
        )
        stubber.add_response(
            "get_index", {"index": _index()}, {"indexArn": _index_arn()}
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _index_arn()},
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            result = provisioning.create_s3_vectors_index(1, 1)
    assert result["indexName"] == _index_name()


def test_create_vector_index_failure_is_sanitized():
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_index",
            service_error_code="AccessDeniedException",
            service_message="provider detail and request id",
            http_status_code=403,
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            with pytest.raises(provisioning.BedrockProvisioningError) as exc:
                provisioning.create_s3_vectors_index(1, 1)
    assert exc.value.code == "vector_index_create_failed"
    assert "request" not in str(exc.value)


def test_vector_index_create_failure_logs_safe_aws_diagnostics(caplog):
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_index",
            service_error_code="AccessDeniedException",
            service_message="TagResource permission is required",
            http_status_code=403,
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            with pytest.raises(provisioning.BedrockProvisioningError):
                provisioning.create_s3_vectors_index(1, 1)
    assert "stage=vector_index_create" in caplog.text
    assert "organization_id=1" in caplog.text
    assert "knowledge_base_id=1" in caplog.text
    assert "aws_error_code=AccessDeniedException" in caplog.text
    assert "aws_error_message=TagResource permission is required" in caplog.text


def test_production_policy_allows_tagging_new_vector_indexes():
    policy_path = Path(__file__).parents[1] / "diaglob-prod-knowledge-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    statement = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "CreateManagedS3VectorIndexes"
    )
    assert set(statement["Action"]) == {
        "s3vectors:CreateIndex",
        "s3vectors:TagResource",
    }


def test_get_vector_index_rejects_incompatible_configuration():
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "get_index",
            {"index": _index(dimension=512)},
            {"indexArn": _index_arn()},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _index_arn()},
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            with pytest.raises(provisioning.BedrockProvisioningError) as exc:
                provisioning._recover_s3_vectors_index(1, 1)
    assert exc.value.code == "vector_index_configuration_mismatch"


def test_delete_vector_index_confirms_absence():
    client = _s3vectors_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "get_index", {"index": _index()}, {"indexArn": _index_arn()}
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _index_arn()},
        )
        stubber.add_response("delete_index", {}, {"indexArn": _index_arn()})
        stubber.add_client_error(
            "get_index",
            service_error_code="NotFoundException",
            http_status_code=404,
            expected_params={"indexArn": _index_arn()},
        )
        with patch.object(
            provisioning, "_get_s3_vectors_client", return_value=client
        ):
            provisioning.delete_s3_vectors_index(_index_arn(), 1, 1)


def test_bedrock_create_and_get_payloads_validate_with_stubber():
    client = _bedrock_client()
    kb = _bedrock_kb()
    ds = _bedrock_ds()
    with Stubber(client) as stubber:
        stubber.add_response(
            "create_knowledge_base",
            {"knowledgeBase": kb},
            {
                "name": _kb_name(),
                "description": "Diaglob Knowledge Base for organization 1, KB 1",
                "roleArn": ROLE_ARN,
                "knowledgeBaseConfiguration": _kb_configuration(),
                "storageConfiguration": _storage_configuration(),
                "clientToken": provisioning._make_client_token("kb", 1, 1),
                "tags": _tags(),
            },
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": kb},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        stubber.add_response(
            "create_data_source",
            {"dataSource": ds},
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "name": "diaglob-prod-kb-1-s3",
                "description": "Diaglob S3 Data Source for org 1, KB 1",
                "dataSourceConfiguration": _data_source_configuration(),
                "vectorIngestionConfiguration": _ingestion_configuration(),
                "dataDeletionPolicy": "DELETE",
                "clientToken": provisioning._make_client_token("ds", 1, 1),
            },
        )
        stubber.add_response(
            "get_data_source",
            {"dataSource": ds},
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            created_kb = provisioning.create_bedrock_knowledge_base(
                1, 1, _index_arn()
            )
            provisioning.wait_for_bedrock_knowledge_base(
                BEDROCK_KB_ID, 1, 1, _index_arn()
            )
            created_ds = provisioning.create_bedrock_data_source(
                BEDROCK_KB_ID, 1, 1
            )
            provisioning.wait_for_bedrock_data_source(
                BEDROCK_KB_ID, BEDROCK_DS_ID, 1, 1
            )
    assert created_kb["knowledgeBaseId"] == BEDROCK_KB_ID
    assert created_ds["dataSourceId"] == BEDROCK_DS_ID


def test_lost_kb_response_recovers_by_name_configuration_and_tags():
    client = _bedrock_client()
    kb = _bedrock_kb()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_knowledge_base",
            service_error_code="ConflictException",
            http_status_code=409,
        )
        stubber.add_response(
            "list_knowledge_bases",
            {
                "knowledgeBaseSummaries": [
                    {
                        "knowledgeBaseId": BEDROCK_KB_ID,
                        "name": _kb_name(),
                        "status": "ACTIVE",
                        "updatedAt": NOW,
                    }
                ]
            },
            {"maxResults": 1000},
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": kb},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            recovered = provisioning.create_bedrock_knowledge_base(
                1, 1, _index_arn()
            )
    assert recovered["knowledgeBaseId"] == BEDROCK_KB_ID


def test_lost_data_source_response_recovers_verified_prefix():
    client = _bedrock_client()
    ds = _bedrock_ds()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_data_source",
            service_error_code="ConflictException",
            http_status_code=409,
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": _bedrock_kb()},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        stubber.add_response(
            "list_data_sources",
            {
                "dataSourceSummaries": [
                    {
                        "knowledgeBaseId": BEDROCK_KB_ID,
                        "dataSourceId": BEDROCK_DS_ID,
                        "name": "diaglob-prod-kb-1-s3",
                        "status": "AVAILABLE",
                        "updatedAt": NOW,
                    }
                ]
            },
            {"knowledgeBaseId": BEDROCK_KB_ID, "maxResults": 1000},
        )
        stubber.add_response(
            "get_data_source",
            {"dataSource": ds},
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            recovered = provisioning.create_bedrock_data_source(
                BEDROCK_KB_ID, 1, 1
            )
    assert recovered["dataSourceId"] == BEDROCK_DS_ID


def test_recovery_rejects_same_kb_name_with_wrong_ownership_tags():
    client = _bedrock_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_knowledge_base",
            service_error_code="ConflictException",
            http_status_code=409,
        )
        stubber.add_response(
            "list_knowledge_bases",
            {
                "knowledgeBaseSummaries": [
                    {
                        "knowledgeBaseId": BEDROCK_KB_ID,
                        "name": _kb_name(),
                        "status": "ACTIVE",
                        "updatedAt": NOW,
                    }
                ]
            },
            {"maxResults": 1000},
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": _bedrock_kb()},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": {**_tags(), "diaglob:organization_id": "999"}},
            {"resourceArn": _kb_arn()},
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            with pytest.raises(provisioning.BedrockProvisioningError) as exc:
                provisioning.create_bedrock_knowledge_base(
                    1, 1, _index_arn()
                )
    assert exc.value.code == "resource_ownership_mismatch"


def test_recovery_rejects_data_source_with_wrong_prefix():
    client = _bedrock_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "create_data_source",
            service_error_code="ConflictException",
            http_status_code=409,
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": _bedrock_kb()},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        stubber.add_response(
            "list_data_sources",
            {
                "dataSourceSummaries": [
                    {
                        "knowledgeBaseId": BEDROCK_KB_ID,
                        "dataSourceId": BEDROCK_DS_ID,
                        "name": "diaglob-prod-kb-1-s3",
                        "status": "AVAILABLE",
                        "updatedAt": NOW,
                    }
                ]
            },
            {"knowledgeBaseId": BEDROCK_KB_ID, "maxResults": 1000},
        )
        stubber.add_response(
            "get_data_source",
            {"dataSource": _bedrock_ds(prefix="organizations/999/documents/")},
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            with pytest.raises(provisioning.BedrockProvisioningError) as exc:
                provisioning.create_bedrock_data_source(BEDROCK_KB_ID, 1, 1)
    assert exc.value.code == "resource_ownership_mismatch"


def test_bedrock_delete_payloads_validate_and_confirm_absence():
    client = _bedrock_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": _bedrock_kb()},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        stubber.add_response(
            "get_data_source",
            {"dataSource": _bedrock_ds()},
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        stubber.add_response(
            "delete_data_source",
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
                "status": "DELETING",
            },
            {
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        stubber.add_client_error(
            "get_data_source",
            service_error_code="ResourceNotFoundException",
            http_status_code=404,
            expected_params={
                "knowledgeBaseId": BEDROCK_KB_ID,
                "dataSourceId": BEDROCK_DS_ID,
            },
        )
        stubber.add_response(
            "get_knowledge_base",
            {"knowledgeBase": _bedrock_kb()},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_response(
            "list_tags_for_resource",
            {"tags": _tags()},
            {"resourceArn": _kb_arn()},
        )
        stubber.add_response(
            "delete_knowledge_base",
            {"knowledgeBaseId": BEDROCK_KB_ID, "status": "DELETING"},
            {"knowledgeBaseId": BEDROCK_KB_ID},
        )
        stubber.add_client_error(
            "get_knowledge_base",
            service_error_code="ResourceNotFoundException",
            http_status_code=404,
            expected_params={"knowledgeBaseId": BEDROCK_KB_ID},
        )
        with patch.object(
            provisioning, "_get_bedrock_agent_client", return_value=client
        ):
            provisioning.delete_bedrock_data_source(
                BEDROCK_KB_ID,
                BEDROCK_DS_ID,
                1,
                1,
                _index_arn(),
            )
            provisioning.delete_bedrock_knowledge_base(
                BEDROCK_KB_ID, 1, 1, _index_arn()
            )


def _successful_remote_patches():
    return (
        patch.object(
            provisioning,
            "create_s3_vectors_index",
            return_value={"indexArn": _index_arn()},
        ),
        patch.object(
            provisioning,
            "create_bedrock_knowledge_base",
            return_value={"knowledgeBaseId": BEDROCK_KB_ID},
        ),
        patch.object(
            provisioning, "wait_for_bedrock_knowledge_base", return_value={}
        ),
        patch.object(
            provisioning,
            "create_bedrock_data_source",
            return_value={"dataSourceId": BEDROCK_DS_ID},
        ),
        patch.object(
            provisioning, "wait_for_bedrock_data_source", return_value={}
        ),
    )


def test_full_provisioning_success_sets_ready(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    patches = _successful_remote_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = provisioning.provision_diaglob_knowledge_base(db, kb)
    assert result == (BEDROCK_KB_ID, BEDROCK_DS_ID)
    assert kb.external_status == "ready"
    assert kb.external_last_error is None


def test_kb_create_failure_cleans_vector_index_and_marks_failed(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        side_effect=provisioning.BedrockProvisioningError(
            "bedrock_kb_create_failed"
        ),
    ), patch.object(provisioning, "delete_s3_vectors_index") as delete_index:
        with pytest.raises(provisioning.BedrockProvisioningError):
            provisioning.provision_diaglob_knowledge_base(db, kb)
    delete_index.assert_called_once()
    assert kb.external_status == "failed"
    assert kb.external_last_error == "bedrock_kb_create_failed"


def test_data_source_failure_cleans_kb_then_index(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    events = []
    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        return_value={"knowledgeBaseId": BEDROCK_KB_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_knowledge_base", return_value={}
    ), patch.object(
        provisioning,
        "create_bedrock_data_source",
        side_effect=provisioning.BedrockProvisioningError(
            "bedrock_data_source_create_failed"
        ),
    ), patch.object(
        provisioning,
        "delete_bedrock_knowledge_base",
        side_effect=lambda *args: events.append("kb"),
    ), patch.object(
        provisioning,
        "delete_s3_vectors_index",
        side_effect=lambda *args: events.append("index"),
    ):
        with pytest.raises(provisioning.BedrockProvisioningError):
            provisioning.provision_diaglob_knowledge_base(db, kb)
    assert events == ["kb", "index"]
    assert kb.external_id is None
    assert kb.external_status == "failed"


def test_cleanup_failure_retains_known_external_id(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        return_value={"knowledgeBaseId": BEDROCK_KB_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_knowledge_base", return_value={}
    ), patch.object(
        provisioning,
        "create_bedrock_data_source",
        side_effect=provisioning.BedrockProvisioningError(
            "bedrock_data_source_create_failed"
        ),
    ), patch.object(
        provisioning,
        "delete_bedrock_knowledge_base",
        side_effect=provisioning.BedrockProvisioningError(
            "bedrock_kb_delete_unconfirmed"
        ),
    ), patch.object(provisioning, "delete_s3_vectors_index") as delete_index:
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.provision_diaglob_knowledge_base(db, kb)
    assert exc.value.code == "cleanup_failed"
    assert kb.external_id == BEDROCK_KB_ID
    assert kb.external_status == "failed"
    assert kb.external_last_error == "cleanup_failed"
    delete_index.assert_not_called()


def test_database_commit_failure_triggers_cleanup_and_failed_state(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    original_commit = db.commit
    commit_count = 0

    def flaky_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("database unavailable")
        return original_commit()

    with patch.object(db, "commit", side_effect=flaky_commit), patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        return_value={"knowledgeBaseId": BEDROCK_KB_ID},
    ), patch.object(
        provisioning, "delete_bedrock_knowledge_base"
    ) as delete_kb, patch.object(
        provisioning, "delete_s3_vectors_index"
    ) as delete_index:
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.provision_diaglob_knowledge_base(db, kb)
    assert exc.value.code == "database_state_persist_failed"
    delete_kb.assert_called_once()
    delete_index.assert_called_once()
    assert kb.external_status == "failed"
    assert kb.external_id is None


def test_existing_ready_kb_performs_no_aws_calls(db):
    org = _make_org(db)
    kb = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    with patch.object(provisioning, "create_s3_vectors_index") as create_index:
        assert provisioning.provision_diaglob_knowledge_base(db, kb) == (
            BEDROCK_KB_ID,
            BEDROCK_DS_ID,
        )
    create_index.assert_not_called()


def test_partial_retry_reuses_existing_kb_and_creates_data_source(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, external_id=BEDROCK_KB_ID)
    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning,
        "get_bedrock_knowledge_base",
        return_value={"knowledgeBaseId": BEDROCK_KB_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_knowledge_base", return_value={}
    ), patch.object(
        provisioning, "create_bedrock_knowledge_base"
    ) as create_kb, patch.object(
        provisioning,
        "create_bedrock_data_source",
        return_value={"dataSourceId": BEDROCK_DS_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_data_source", return_value={}
    ):
        provisioning.provision_diaglob_knowledge_base(db, kb)
    create_kb.assert_not_called()
    assert kb.external_status == "ready"


def test_provisioning_status_prevents_second_attempt(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="provisioning")
    with patch.object(provisioning, "create_s3_vectors_index") as create_index:
        with pytest.raises(provisioning.ProvisioningInProgressError):
            provisioning.provision_diaglob_knowledge_base(db, kb)
    create_index.assert_not_called()


def test_retry_endpoint_rejects_ready_and_provisioning(api_client, db):
    client, org, _ = api_client
    ready = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    in_progress = _make_local_kb(db, org, status="provisioning")
    ready_response = client.post(
        f"/api/knowledge-bases/{ready.id}/retry-provisioning"
    )
    progress_response = client.post(
        f"/api/knowledge-bases/{in_progress.id}/retry-provisioning"
    )
    assert ready_response.status_code == 400
    assert progress_response.status_code == 409
    assert progress_response.json()["detail"]["code"] == (
        "PROVISIONING_IN_PROGRESS"
    )


def test_retry_endpoint_is_tenant_scoped(api_client, db):
    client, _, _ = api_client
    other_org = _make_org(db, "other-bedrock-test")
    other_kb = _make_local_kb(db, other_org)
    response = client.post(
        f"/api/knowledge-bases/{other_kb.id}/retry-provisioning"
    )
    assert response.status_code == 404


def test_pending_retry_endpoint_provisions_once(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(db, org)

    def complete(_db, knowledge_base):
        knowledge_base.external_status = "ready"
        knowledge_base.external_id = BEDROCK_KB_ID
        knowledge_base.external_data_source_id = BEDROCK_DS_ID
        _db.commit()
        return BEDROCK_KB_ID, BEDROCK_DS_ID

    with patch("app.main.provision_diaglob_knowledge_base", side_effect=complete) as call:
        response = client.post(
            f"/api/knowledge-bases/{kb.id}/retry-provisioning"
        )
    assert response.status_code == 200
    assert response.json()["external_status"] == "ready"
    call.assert_called_once()


READINESS_CASES = [
    (
        "post",
        "/api/knowledge-bases/{kb}/sources",
        {"files": {"file": ("test.txt", b"text", "text/plain")}},
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/google-sheet",
        {
            "json": {
                "spreadsheet_id": "sheet-id",
                "spreadsheet_name": "Sheet",
                "sheet_name": "Tab",
            }
        },
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/999/sync",
        {},
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/google-doc",
        {
            "json": {
                "file_id": "doc-id",
                "file_name": "Doc",
                "mime_type": "application/vnd.google-apps.document",
            }
        },
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/google-drive-file",
        {
            "json": {
                "file_id": "file-id",
                "file_name": "File.pdf",
                "mime_type": "application/pdf",
            }
        },
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/google-drive-folder",
        {"json": {"folder_id": "folder-id", "folder_name": "Folder"}},
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/999/sync-folder",
        {},
    ),
    (
        "post",
        "/api/knowledge-bases/{kb}/sources/999/sync-drive-file",
        {},
    ),
    (
        "delete",
        "/api/knowledge-bases/{kb}/sources/999",
        {},
    ),
]


@pytest.mark.parametrize("method,path,kwargs", READINESS_CASES)
def test_pending_kb_blocks_every_source_mutation(
    api_client, db, method, path, kwargs
):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status="pending")
    response = getattr(client, method)(path.format(kb=kb.id), **kwargs)
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "KNOWLEDGE_BASE_NOT_READY",
        "message": "Knowledge Base provisioning is not ready.",
        "status": "pending",
    }


def test_failed_kb_blocks_file_upload(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status="failed")
    response = client.post(
        f"/api/knowledge-bases/{kb.id}/sources",
        files={"file": ("test.txt", b"text", "text/plain")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "failed"


def test_ready_kb_file_upload_remains_allowed(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    with patch(
        "app.main.upload_knowledge_file",
        return_value={"bucket": KNOWLEDGE_BUCKET, "key": "safe/test.txt"},
    ):
        response = client.post(
            f"/api/knowledge-bases/{kb.id}/sources",
            files={"file": ("test.txt", b"text", "text/plain")},
        )
    assert response.status_code == 200
    assert response.json()["knowledge_base_id"] == kb.id


# ============================================================
# R2 — Ingestion status readiness gate
# ============================================================


def _make_source(db, kb, sync_status="indexing", ingestion_job_id="job-123"):
    source = KnowledgeSource(
        organization_id=kb.organization_id,
        knowledge_base_id=kb.id,
        name="Test Source",
        source_type="file",
        s3_bucket="test-bucket",
        s3_key="test-key",
        status="uploaded",
        sync_status=sync_status,
        ingestion_job_id=ingestion_job_id,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


INGESTION_STATUS_CASES = [
    ("pending", "pending"),
    ("provisioning", "provisioning"),
    ("failed", "failed"),
]


@pytest.mark.parametrize("kb_status,label", INGESTION_STATUS_CASES)
def test_ingestion_status_rejects_non_ready_kb(
    api_client, db, kb_status, label
):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status=kb_status)
    source = _make_source(db, kb)
    response = client.get(
        f"/api/knowledge-bases/{kb.id}/sources/{source.id}/ingestion-status"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sync_status"] == "indexing"


def test_ingestion_status_ready_kb_with_missing_ids_returns_indexing(
    api_client, db
):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status="ready")
    source = _make_source(db, kb)
    response = client.get(
        f"/api/knowledge-bases/{kb.id}/sources/{source.id}/ingestion-status"
    )
    assert response.status_code == 200
    assert response.json()["sync_status"] == "indexing"


def test_ingestion_status_ready_kb_with_ids_calls_bedrock(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    source = _make_source(db, kb)
    with patch(
        "app.main.get_ingestion_status", return_value="synced"
    ) as mock_status:
        response = client.get(
            f"/api/knowledge-bases/{kb.id}/sources/{source.id}/ingestion-status"
        )
    assert response.status_code == 200
    assert response.json()["sync_status"] == "synced"
    mock_status.assert_called_once_with(
        BEDROCK_KB_ID, BEDROCK_DS_ID, "job-123"
    )
