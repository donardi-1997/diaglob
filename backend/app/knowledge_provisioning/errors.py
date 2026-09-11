"""Provider-neutral error taxonomy for Knowledge provisioning.

This module owns safe failure classification and AWS error inspection. It does
not know about SQLAlchemy, FastAPI, resource orchestration, or application
configuration, which keeps error handling reusable across provisioning
adapters.
"""
from __future__ import annotations

import re
from enum import Enum

from botocore.exceptions import BotoCoreError, ClientError


class ProvisioningErrorClassification(str, Enum):
    USER_ACTION_REQUIRED = "user_action_required"
    RETRYABLE_INFRASTRUCTURE = "retryable_infrastructure"
    PLATFORM_CONFIGURATION_ERROR = "platform_configuration_error"
    PERMANENT_RESOURCE_ERROR = "permanent_resource_error"


class BedrockProvisioningError(Exception):
    """A safe, stable provisioning failure suitable for persistence."""

    def __init__(
        self,
        code: str,
        resource: str | None = None,
        classification: ProvisioningErrorClassification | None = None,
        aws_service: str | None = None,
        aws_operation: str | None = None,
        aws_error_code: str | None = None,
        aws_request_id: str | None = None,
    ):
        self.code = code
        self.resource = resource
        self.classification = (
            classification
            or ProvisioningErrorClassification.PERMANENT_RESOURCE_ERROR
        )
        self.aws_service = aws_service
        self.aws_operation = aws_operation
        self.aws_error_code = aws_error_code
        self.aws_request_id = aws_request_id
        super().__init__(code)

    @property
    def persistence_code(self) -> str:
        if self.aws_error_code and re.fullmatch(
            r"[A-Za-z0-9._-]{1,100}", self.aws_error_code
        ):
            return f"{self.code}:{self.aws_error_code}"
        return self.code


class ProvisioningInProgressError(BedrockProvisioningError):
    """Raised when another request already owns the provisioning attempt."""

    def __init__(self):
        super().__init__("provisioning_in_progress", resource="knowledge_base")


def _find_client_error(error: Exception) -> ClientError | None:
    current: BaseException | None = error
    visited: set[int] = set()
    while current and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, ClientError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _client_error_code(error: Exception) -> str | None:
    client_error = _find_client_error(error)
    if client_error:
        return client_error.response.get("Error", {}).get("Code")
    return None


def _client_error_message(error: Exception) -> str | None:
    client_error = _find_client_error(error)
    if not client_error:
        return None
    message = client_error.response.get("Error", {}).get("Message")
    if not isinstance(message, str):
        return None
    return " ".join(message.split())[:500]


def _client_error_request_id(error: Exception) -> str | None:
    client_error = _find_client_error(error)
    if not client_error:
        return None
    return client_error.response.get("ResponseMetadata", {}).get("RequestId")


def classify_provisioning_aws_error(
    error: Exception,
) -> ProvisioningErrorClassification:
    code = _client_error_code(error)
    if code in {
        "ThrottlingException",
        "TooManyRequestsException",
        "InternalServerException",
        "ServiceUnavailableException",
        "RequestTimeoutException",
    } or isinstance(error, BotoCoreError):
        return ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE
    if code in {
        "AccessDeniedException",
        "UnauthorizedException",
        "ValidationException",
    }:
        return ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR
    return ProvisioningErrorClassification.PERMANENT_RESOURCE_ERROR


def _aws_provisioning_error(
    code: str,
    resource: str,
    error: Exception,
    *,
    aws_service: str,
    aws_operation: str,
    classification: ProvisioningErrorClassification | None = None,
) -> BedrockProvisioningError:
    return BedrockProvisioningError(
        code,
        resource=resource,
        classification=classification,
        aws_service=aws_service,
        aws_operation=aws_operation,
        aws_error_code=_client_error_code(error),
        aws_request_id=_client_error_request_id(error),
    )


def _is_uncertain_create_error(error: Exception) -> bool:
    if isinstance(error, BotoCoreError):
        return True
    return _client_error_code(error) in {
        "ConflictException",
        "InternalServerException",
        "RequestTimeoutException",
        "ServiceUnavailableException",
        "ThrottlingException",
        "TooManyRequestsException",
    }


__all__ = [
    "BedrockProvisioningError",
    "ProvisioningErrorClassification",
    "ProvisioningInProgressError",
    "classify_provisioning_aws_error",
]
