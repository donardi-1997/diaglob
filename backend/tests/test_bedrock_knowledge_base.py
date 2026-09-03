"""Tests for isolated Bedrock and S3 Vectors provisioning."""

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bedrock_knowledge_base as provisioning
from app import main as api_main
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
    active=True,
):
    kb = KnowledgeBase(
        organization_id=org.id,
        name="Local KB",
        scope="organization",
        external_status=status,
        external_id=external_id,
        external_data_source_id=data_source_id,
        active=active,
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
    assert "operation=CreateIndex" in caplog.text
    assert "aws_service=s3vectors" in caplog.text
    assert "provisioning_stage=creating_vector_index" in caplog.text
    assert "organization_id=1" in caplog.text
    assert "knowledge_base_id=1" in caplog.text
    assert "aws_error_code=AccessDeniedException" in caplog.text
    assert "aws_error_message=TagResource permission is required" in caplog.text
    assert "Traceback" in caplog.text


def test_tag_resource_access_denied_is_platform_configuration_error():
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "TagResource denied"}},
        "CreateIndex",
    )
    assert provisioning.classify_provisioning_aws_error(error) == (
        provisioning.ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
    )


def test_transient_provisioning_failure_retries_automatically():
    knowledge_base = MagicMock(id=1, organization_id=1, external_status="pending")
    db = MagicMock()
    db.get.return_value = knowledge_base
    transient = provisioning.BedrockProvisioningError(
        "vector_index_create_failed",
        classification=provisioning.ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE,
    )

    def succeed(_db, kb):
        kb.external_status = "ready"

    with patch.object(api_main, "SessionLocal", return_value=db), patch.object(
        api_main, "PROVISIONING_RETRY_DELAYS_SECONDS", (0, 0)
    ), patch.object(
        api_main, "provision_diaglob_knowledge_base", side_effect=[transient, succeed]
    ) as provision:
        api_main.run_knowledge_base_provisioning(1)
    assert provision.call_count == 2
    assert db.commit.called


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


def test_production_policy_allows_tagging_new_bedrock_knowledge_bases():
    policy_path = Path(__file__).parents[1] / "diaglob-prod-knowledge-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    statement = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "CreateManagedBedrockKnowledgeBases"
    )
    assert set(statement["Action"]) == {
        "bedrock:CreateKnowledgeBase",
        "bedrock:TagResource",
    }


def test_production_policy_can_poll_bedrock_kb_after_tags_disappear():
    policy_path = Path(__file__).parents[1] / "diaglob-prod-knowledge-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    read_statement = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "ReadManagedBedrockKnowledgeBasesForCleanup"
    )
    delete_statement = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "ManageOwnedBedrockKnowledgeBases"
    )
    assert read_statement["Action"] == "bedrock:GetKnowledgeBase"
    assert "Condition" not in read_statement
    assert "bedrock:GetKnowledgeBase" not in delete_statement["Action"]
    assert delete_statement["Condition"]["StringEquals"] == {
        "aws:ResourceTag/diaglob:managed-by": "diaglob-backend",
        "aws:ResourceTag/diaglob:environment": "production",
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


def test_bedrock_create_access_denied_is_diagnostic_and_logged(db, caplog):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    request_id = "bedrock-request-123"
    access_denied = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "bedrock:TagResource is not authorized",
            },
            "ResponseMetadata": {"RequestId": request_id},
        },
        "CreateKnowledgeBase",
    )
    client = MagicMock()
    client.create_knowledge_base.side_effect = access_denied

    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        return_value={"indexArn": _index_arn(kb.id)},
    ), patch.object(
        provisioning, "_get_bedrock_agent_client", return_value=client
    ), patch.object(provisioning, "delete_s3_vectors_index"):
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.provision_diaglob_knowledge_base(db, kb)

    assert exc.value.code == "bedrock_kb_create_failed"
    assert exc.value.classification == (
        provisioning.ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
    )
    assert kb.external_status == "failed"
    assert kb.provisioning_stage == "failed"
    assert kb.external_last_error == (
        "bedrock_kb_create_failed:AccessDeniedException"
    )
    assert "operation=CreateKnowledgeBase" in caplog.text
    assert "aws_service=bedrock-agent" in caplog.text
    assert "provisioning_stage=creating_knowledge_base" in caplog.text
    assert f"organization_id={org.id}" in caplog.text
    assert f"knowledge_base_id={kb.id}" in caplog.text
    assert "aws_error_code=AccessDeniedException" in caplog.text
    assert "aws_error_message=bedrock:TagResource is not authorized" in caplog.text
    assert f"aws_request_id={request_id}" in caplog.text
    assert f"vector_index_arn={_index_arn(kb.id)}" in caplog.text
    assert "Traceback" in caplog.text


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
        if commit_count == 3:
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


def test_delete_ready_kb_cleans_owned_resources_prefix_and_sources(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="ready", external_id=BEDROCK_KB_ID, data_source_id=BEDROCK_DS_ID)
    source = KnowledgeSource(
        organization_id=org.id,
        knowledge_base_id=kb.id,
        name="Uploaded file",
        source_type="file",
        s3_bucket=KNOWLEDGE_BUCKET,
        s3_key=f"organizations/{org.id}/knowledge-bases/{kb.id}/documents/file.txt",
    )
    db.add(source)
    db.commit()
    source_id = source.id
    with patch.object(provisioning, "_cleanup_remote_resources", return_value=provisioning.CleanupResult(True, None, None)) as cleanup, patch.object(provisioning, "delete_knowledge_prefix") as delete_prefix:
        provisioning.delete_diaglob_knowledge_base(db, kb)
    cleanup.assert_called_once()
    delete_prefix.assert_called_once_with(org.id, kb.id)
    assert db.get(KnowledgeBase, kb.id) is None
    assert db.query(KnowledgeSource).filter_by(id=source_id).first() is None


def test_delete_failed_kb_without_remote_resources_is_safe(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="failed")
    with patch.object(provisioning, "_cleanup_remote_resources", return_value=provisioning.CleanupResult(True, None, None)), patch.object(provisioning, "delete_knowledge_prefix"):
        provisioning.delete_diaglob_knowledge_base(db, kb)
    assert db.get(KnowledgeBase, kb.id) is None


def test_delete_failure_preserves_specific_cleanup_cause(db, caplog):
    org = _make_org(db)
    kb = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    ownership_error = provisioning.BedrockProvisioningError(
        "resource_ownership_mismatch",
        resource="knowledge_base",
    )
    cleanup = provisioning.CleanupResult(
        False,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
        ownership_error,
    )

    with patch.object(
        provisioning, "_cleanup_remote_resources", return_value=cleanup
    ):
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.delete_diaglob_knowledge_base(db, kb)

    assert exc.value.code == "resource_ownership_mismatch"
    assert kb.external_status == "deleting"
    assert kb.external_last_error == (
        "deletion_failed:resource_ownership_mismatch"
    )
    assert "knowledge_base_deletion_failed" in caplog.text
    assert "error_code=resource_ownership_mismatch" in caplog.text
    assert f"organization_id={org.id}" in caplog.text
    assert f"knowledge_base_id={kb.id}" in caplog.text


def test_delete_endpoint_hides_other_tenant_knowledge_base(api_client, db):
    client, _, _ = api_client
    other_org = _make_org(db, "other-delete-test")
    other_kb = _make_local_kb(db, other_org, status="failed")
    response = client.delete(f"/api/knowledge-bases/{other_kb.id}")
    assert response.status_code == 404
    assert db.get(KnowledgeBase, other_kb.id) is not None


def test_provisioning_cannot_claim_deleting_knowledge_base(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="deleting")
    with pytest.raises(provisioning.BedrockProvisioningError) as exc:
        provisioning.provision_diaglob_knowledge_base(db, kb)
    assert exc.value.code == "invalid_provisioning_state"


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


def test_retry_reuses_partial_vector_index_and_completes(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    vector_index_exists = False
    vector_index_calls = 0

    def create_or_reuse_vector_index(org_id, kb_id):
        nonlocal vector_index_exists, vector_index_calls
        assert org_id == org.id
        assert kb_id == kb.id
        vector_index_calls += 1
        if vector_index_calls == 1:
            vector_index_exists = True
        else:
            assert vector_index_exists
        return {"indexArn": _index_arn(kb.id)}

    access_denied = provisioning.BedrockProvisioningError(
        "bedrock_kb_create_failed",
        resource="knowledge_base",
        classification=(
            provisioning.ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
        ),
        aws_service="bedrock-agent",
        aws_operation="CreateKnowledgeBase",
        aws_error_code="AccessDeniedException",
    )
    cleanup_failure = provisioning.BedrockProvisioningError(
        "vector_index_delete_unconfirmed",
        resource="vector_index",
    )

    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        side_effect=create_or_reuse_vector_index,
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        side_effect=access_denied,
    ), patch.object(
        provisioning,
        "delete_s3_vectors_index",
        side_effect=cleanup_failure,
    ):
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.provision_diaglob_knowledge_base(db, kb)

    assert exc.value.code == "cleanup_failed"
    assert vector_index_exists
    assert kb.external_status == "failed"

    kb.external_status = "retrying"
    kb.external_last_error = None
    kb.provisioning_stage = "queued"
    db.commit()
    with patch.object(
        provisioning,
        "create_s3_vectors_index",
        side_effect=create_or_reuse_vector_index,
    ), patch.object(
        provisioning,
        "create_bedrock_knowledge_base",
        return_value={"knowledgeBaseId": BEDROCK_KB_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_knowledge_base", return_value={}
    ), patch.object(
        provisioning,
        "create_bedrock_data_source",
        return_value={"dataSourceId": BEDROCK_DS_ID},
    ), patch.object(
        provisioning, "wait_for_bedrock_data_source", return_value={}
    ):
        provisioning.provision_diaglob_knowledge_base(db, kb)

    assert vector_index_calls == 2
    assert kb.external_id == BEDROCK_KB_ID
    assert kb.external_data_source_id == BEDROCK_DS_ID
    assert kb.external_status == "ready"
    assert kb.provisioning_stage == "ready"
    assert kb.external_last_error is None


def test_provisioning_status_prevents_second_attempt(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="provisioning")
    with patch.object(provisioning, "create_s3_vectors_index") as create_index:
        with pytest.raises(provisioning.ProvisioningInProgressError):
            provisioning.provision_diaglob_knowledge_base(db, kb)
    create_index.assert_not_called()


def test_retry_endpoint_rejects_ready_and_active_or_deleting_states(api_client, db):
    client, org, _ = api_client
    ready = _make_local_kb(
        db,
        org,
        status="ready",
        external_id=BEDROCK_KB_ID,
        data_source_id=BEDROCK_DS_ID,
    )
    in_progress = _make_local_kb(db, org, status="provisioning")
    retrying = _make_local_kb(db, org, status="retrying")
    deleting = _make_local_kb(db, org, status="deleting")
    ready_response = client.post(
        f"/api/knowledge-bases/{ready.id}/retry-provisioning"
    )
    progress_response = client.post(
        f"/api/knowledge-bases/{in_progress.id}/retry-provisioning"
    )
    retrying_response = client.post(
        f"/api/knowledge-bases/{retrying.id}/retry-provisioning"
    )
    deleting_response = client.post(
        f"/api/knowledge-bases/{deleting.id}/retry-provisioning"
    )
    assert ready_response.status_code == 400
    assert progress_response.status_code == 409
    assert retrying_response.status_code == 409
    assert deleting_response.status_code == 400
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


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_retry_endpoint_schedules_provisioning(api_client, db, status):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status=status)

    with patch("app.main.run_knowledge_base_provisioning") as run, patch.object(
        api_main, "reconcile_knowledge_base_provisioning"
    ) as reconcile:
        response = client.post(
            f"/api/knowledge-bases/{kb.id}/retry-provisioning"
        )
    assert response.status_code == 200
    assert response.json()["external_status"] == "retrying"
    assert response.json()["provisioning_stage"] == "queued"
    run.assert_called_once_with(kb.id)
    reconcile.assert_not_called()


def test_manual_retry_worker_completes_provisioning(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status="failed")
    kb.external_last_error = "bedrock_kb_create_failed:AccessDeniedException"
    kb.provisioning_stage = "failed"
    db.commit()
    kb_id = kb.id
    patches = _successful_remote_patches()

    with patch.object(
        api_main, "SessionLocal", TestingSessionLocal
    ), patch.object(
        api_main, "PROVISIONING_RETRY_DELAYS_SECONDS", (0,)
    ), patches[0], patches[1], patches[2], patches[3], patches[4]:
        response = client.post(
            f"/api/knowledge-bases/{kb_id}/retry-provisioning"
        )

    assert response.status_code == 200
    assert response.json()["external_status"] == "retrying"
    assert response.json()["provisioning_stage"] == "queued"
    assert response.json()["external_last_error"] is None
    verify_db = TestingSessionLocal()
    try:
        retried = verify_db.get(KnowledgeBase, kb_id)
        assert retried.external_id == BEDROCK_KB_ID
        assert retried.external_data_source_id == BEDROCK_DS_ID
        assert retried.external_status == "ready"
        assert retried.provisioning_stage == "ready"
        assert retried.external_last_error is None
    finally:
        verify_db.close()


def test_duplicate_manual_retry_schedules_one_task(api_client, db):
    client, org, _ = api_client
    kb = _make_local_kb(db, org, status="failed")

    with patch("app.main.run_knowledge_base_provisioning") as run:
        first = client.post(f"/api/knowledge-bases/{kb.id}/retry-provisioning")
        second = client.post(f"/api/knowledge-bases/{kb.id}/retry-provisioning")

    assert first.status_code == 200
    assert second.status_code == 409
    run.assert_called_once_with(kb.id)


def test_retrying_status_is_claimable(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="retrying")

    provisioning._claim_provisioning(db, kb)

    assert kb.external_status == "provisioning"
    assert kb.provisioning_stage == "creating_vector_index"


def test_manual_retry_task_persists_aws_failure(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org, status="retrying")
    org_id = org.id
    kb_id = kb.id
    failure = provisioning.BedrockProvisioningError(
        "vector_index_create_failed",
        resource="vector_index",
        classification=(
            provisioning.ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
        ),
    )

    with patch.object(api_main, "SessionLocal", return_value=db), patch.object(
        api_main, "PROVISIONING_RETRY_DELAYS_SECONDS", (0,)
    ), patch.object(
        provisioning, "create_s3_vectors_index", side_effect=failure
    ) as create_index:
        api_main.run_knowledge_base_provisioning(kb_id)

    verify_db = TestingSessionLocal()
    try:
        failed = verify_db.get(KnowledgeBase, kb_id)
        assert failed.external_status == "failed"
        assert failed.provisioning_stage == "failed"
        assert failed.external_last_error == "vector_index_create_failed"
    finally:
        verify_db.close()
    create_index.assert_called_once_with(org_id, kb_id)


def test_provisioning_stages_are_persisted_and_classification_is_retained(db):
    org = _make_org(db)
    kb = _make_local_kb(db, org)
    transient = provisioning.BedrockProvisioningError(
        "vector_index_create_failed",
        resource="vector_index",
        classification=provisioning.ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE,
    )
    with patch.object(provisioning, "create_s3_vectors_index", side_effect=transient):
        with pytest.raises(provisioning.BedrockProvisioningError) as exc:
            provisioning.provision_diaglob_knowledge_base(db, kb)
    assert exc.value.classification == transient.classification
    assert kb.external_status == "failed"
    assert kb.provisioning_stage == "failed"
    assert kb.provisioning_started_at is not None
    assert kb.provisioning_stage_started_at is not None


def test_startup_reconciler_resumes_active_states_and_skips_deleting(db):
    org = _make_org(db)
    pending = _make_local_kb(db, org, status="pending")
    stale = _make_local_kb(db, org, status="provisioning")
    deleting = _make_local_kb(db, org, status="deleting")
    inactive = _make_local_kb(db, org, status="pending", active=False)
    pending_id, stale_id, deleting_id, inactive_id = (
        pending.id,
        stale.id,
        deleting.id,
        inactive.id,
    )

    with patch.object(api_main, "SessionLocal", return_value=db), patch.object(
        api_main, "schedule_knowledge_base_provisioning"
    ) as schedule:
        api_main.reconcile_knowledge_base_provisioning()

    verify_db = TestingSessionLocal()
    try:
        resumed = verify_db.get(KnowledgeBase, stale_id)
        unchanged = verify_db.get(KnowledgeBase, deleting_id)
        skipped = verify_db.get(KnowledgeBase, inactive_id)
        assert resumed.external_status == "retrying"
        assert resumed.provisioning_stage == "retrying"
        assert unchanged.external_status == "deleting"
        assert skipped.external_status == "pending"
    finally:
        verify_db.close()
    assert schedule.call_args_list == [
        ((pending_id,),),
        ((stale_id,),),
    ]


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
