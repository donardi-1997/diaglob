"""Regression tests for the Knowledge provisioning error boundary."""
from pathlib import Path

from botocore.exceptions import ClientError

from app import bedrock_knowledge_base as legacy
from app.knowledge_provisioning import errors


def _client_error(code: str, message: str = "provider detail") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"RequestId": "req-123"},
        },
        "TestOperation",
    )


def test_legacy_facade_reexports_canonical_error_types():
    assert legacy.BedrockProvisioningError is errors.BedrockProvisioningError
    assert (
        legacy.ProvisioningErrorClassification
        is errors.ProvisioningErrorClassification
    )
    assert legacy.ProvisioningInProgressError is errors.ProvisioningInProgressError


def test_error_types_are_physically_owned_by_boundary_module():
    assert errors.BedrockProvisioningError.__module__ == (
        "app.knowledge_provisioning.errors"
    )
    assert errors.ProvisioningInProgressError.__module__ == (
        "app.knowledge_provisioning.errors"
    )


def test_aws_error_classification_contract_is_preserved():
    assert errors.classify_provisioning_aws_error(
        _client_error("ThrottlingException")
    ) == errors.ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE
    assert errors.classify_provisioning_aws_error(
        _client_error("AccessDeniedException")
    ) == errors.ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
    assert errors.classify_provisioning_aws_error(
        _client_error("ConflictException")
    ) == errors.ProvisioningErrorClassification.PERMANENT_RESOURCE_ERROR


def test_error_inspection_handles_chained_client_errors():
    root = _client_error("AccessDeniedException", "denied")
    wrapped = RuntimeError("wrapper")
    wrapped.__cause__ = root

    assert errors._client_error_code(wrapped) == "AccessDeniedException"
    assert errors._client_error_message(wrapped) == "denied"
    assert errors._client_error_request_id(wrapped) == "req-123"


def test_persistence_code_only_includes_safe_aws_codes():
    safe = errors.BedrockProvisioningError(
        "vector_index_create_failed",
        aws_error_code="AccessDeniedException",
    )
    unsafe = errors.BedrockProvisioningError(
        "vector_index_create_failed",
        aws_error_code="Access denied: secret detail",
    )

    assert safe.persistence_code == (
        "vector_index_create_failed:AccessDeniedException"
    )
    assert unsafe.persistence_code == "vector_index_create_failed"


def test_legacy_module_no_longer_defines_error_taxonomy():
    source = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "class BedrockProvisioningError" not in source
    assert "class ProvisioningInProgressError" not in source
    assert "class ProvisioningErrorClassification" not in source
    assert "def _find_client_error(" not in source
    assert "def _aws_provisioning_error(" not in source
    assert "from .knowledge_provisioning.errors import (" in source
