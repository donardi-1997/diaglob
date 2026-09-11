"""Boundary tests for small Knowledge provisioning runtime helpers."""

import logging
from unittest.mock import MagicMock

import pytest

from app import bedrock_knowledge_base as facade
from app.knowledge_provisioning.runtime import (
    AwsDiagnosticsContext,
    log_provisioning_aws_error,
    sleep_between_attempts,
    tags_match,
)


VECTOR_BUCKET_ARN = (
    "arn:aws:s3vectors:us-east-2:123456789012:bucket/diaglob-vectors-test"
)
ROLE_ARN = "arn:aws:iam::123456789012:role/DiaglobBedrockKnowledgeBaseRole"
MODEL_ARN = (
    "arn:aws:bedrock:us-east-2::foundation-model/"
    "amazon.titan-embed-text-v2:0"
)
KNOWLEDGE_BUCKET = "diaglob-knowledge-test"


def test_sleep_only_occurs_between_attempts():
    sleeper = MagicMock()

    sleep_between_attempts(0, 3, 2.5, sleep=sleeper)
    sleeper.assert_called_once_with(2.5)

    sleeper.reset_mock()
    sleep_between_attempts(2, 3, 2.5, sleep=sleeper)
    sleeper.assert_not_called()

    sleep_between_attempts(0, 3, 0, sleep=sleeper)
    sleeper.assert_not_called()


def test_tags_match_preserves_expected_subset_semantics():
    actual = {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": "production",
        "provider-extra": "allowed",
    }
    assert tags_match(
        actual,
        {
            "diaglob:managed-by": "diaglob-backend",
            "diaglob:environment": "production",
        },
    ) is True
    assert tags_match(
        actual,
        {"diaglob:environment": "staging"},
    ) is False
    assert tags_match(actual, {"missing": "value"}) is False


def test_structured_aws_diagnostics_preserve_fields(caplog):
    logger = logging.getLogger("test.knowledge.runtime")
    context = AwsDiagnosticsContext(
        vector_bucket_arn=VECTOR_BUCKET_ARN,
        bedrock_service_role_arn=ROLE_ARN,
        embedding_model_arn=MODEL_ARN,
        knowledge_bucket=KNOWLEDGE_BUCKET,
    )
    error = RuntimeError("provider failure")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        log_provisioning_aws_error(
            logger=logger,
            operation="CreateIndex",
            aws_service="s3vectors",
            stage="creating_vector_index",
            org_id=7,
            kb_id=42,
            error=error,
            context=context,
            client_error_code=lambda _error: "AccessDeniedException",
            client_error_message=lambda _error: "TagResource permission is required",
            client_error_request_id=lambda _error: "request-123",
            vector_index_arn=f"{VECTOR_BUCKET_ARN}/index/diaglob-prod-kb-42",
            bedrock_kb_id="KB123",
            bedrock_data_source_id="DS123",
        )

    assert "operation=CreateIndex" in caplog.text
    assert "aws_service=s3vectors" in caplog.text
    assert "organization_id=7" in caplog.text
    assert "knowledge_base_id=42" in caplog.text
    assert "provisioning_stage=creating_vector_index" in caplog.text
    assert "aws_error_code=AccessDeniedException" in caplog.text
    assert "aws_error_message=TagResource permission is required" in caplog.text
    assert "aws_request_id=request-123" in caplog.text
    assert f"vector_bucket_arn={VECTOR_BUCKET_ARN}" in caplog.text
    assert f"bedrock_role_arn={ROLE_ARN}" in caplog.text
    assert f"embedding_model_arn={MODEL_ARN}" in caplog.text
    assert f"knowledge_bucket={KNOWLEDGE_BUCKET}" in caplog.text


def test_facade_diagnostics_context_uses_current_runtime_values(monkeypatch):
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", VECTOR_BUCKET_ARN)
    monkeypatch.setattr(facade, "BEDROCK_SERVICE_ROLE_ARN", ROLE_ARN)
    monkeypatch.setattr(facade, "EMBEDDING_MODEL_ARN", MODEL_ARN)
    monkeypatch.setattr(facade, "KNOWLEDGE_BUCKET", KNOWLEDGE_BUCKET)

    context = facade._diagnostics_context()

    assert context == AwsDiagnosticsContext(
        vector_bucket_arn=VECTOR_BUCKET_ARN,
        bedrock_service_role_arn=ROLE_ARN,
        embedding_model_arn=MODEL_ARN,
        knowledge_bucket=KNOWLEDGE_BUCKET,
    )


def test_facade_runtime_wrappers_capture_call_time_dependencies(monkeypatch):
    runtime_sleep = MagicMock()
    runtime_tags = MagicMock(return_value=True)
    runtime_log = MagicMock()

    monkeypatch.setattr(facade, "POLL_INTERVAL_SECONDS", 3.5)
    monkeypatch.setattr(facade, "runtime_sleep_between_attempts", runtime_sleep)
    monkeypatch.setattr(facade, "runtime_tags_match", runtime_tags)
    monkeypatch.setattr(facade, "runtime_log_provisioning_aws_error", runtime_log)
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", VECTOR_BUCKET_ARN)
    monkeypatch.setattr(facade, "BEDROCK_SERVICE_ROLE_ARN", ROLE_ARN)
    monkeypatch.setattr(facade, "EMBEDDING_MODEL_ARN", MODEL_ARN)
    monkeypatch.setattr(facade, "KNOWLEDGE_BUCKET", KNOWLEDGE_BUCKET)

    facade._sleep_between_attempts(1, 4)
    runtime_sleep.assert_called_once_with(1, 4, 3.5)

    actual = {"a": "1"}
    expected = {"a": "1"}
    assert facade._tags_match(actual, expected) is True
    runtime_tags.assert_called_once_with(actual, expected)

    error = RuntimeError("boom")
    facade._log_provisioning_aws_error(
        operation="GetIndex",
        aws_service="s3vectors",
        stage="retrying",
        org_id=5,
        kb_id=8,
        error=error,
        vector_index_arn="arn:index",
    )
    kwargs = runtime_log.call_args.kwargs
    assert kwargs["logger"] is facade.logger
    assert kwargs["operation"] == "GetIndex"
    assert kwargs["aws_service"] == "s3vectors"
    assert kwargs["stage"] == "retrying"
    assert kwargs["org_id"] == 5
    assert kwargs["kb_id"] == 8
    assert kwargs["error"] is error
    assert kwargs["vector_index_arn"] == "arn:index"
    assert kwargs["context"] == AwsDiagnosticsContext(
        vector_bucket_arn=VECTOR_BUCKET_ARN,
        bedrock_service_role_arn=ROLE_ARN,
        embedding_model_arn=MODEL_ARN,
        knowledge_bucket=KNOWLEDGE_BUCKET,
    )
