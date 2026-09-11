"""Small runtime helpers shared by Knowledge provisioning adapters.

This module owns retry sleeping, tag comparison, and structured AWS diagnostic
logging. Process configuration and client factories stay in the compatibility
facade so existing runtime/monkeypatch seams remain live.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AwsDiagnosticsContext:
    vector_bucket_arn: str
    bedrock_service_role_arn: str
    embedding_model_arn: str
    knowledge_bucket: str


def sleep_between_attempts(
    attempt: int,
    attempts: int,
    poll_interval_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Sleep between retry attempts, never after the final attempt."""
    if attempt + 1 < attempts and poll_interval_seconds > 0:
        sleep(poll_interval_seconds)


def tags_match(actual: dict[str, str], expected: dict[str, str]) -> bool:
    """Return whether every expected ownership tag is present with its value."""
    return all(actual.get(key) == value for key, value in expected.items())


def log_provisioning_aws_error(
    *,
    logger: logging.Logger,
    operation: str,
    aws_service: str,
    stage: str,
    org_id: int,
    kb_id: int,
    error: Exception,
    context: AwsDiagnosticsContext,
    client_error_code: Callable[[Exception], str | None],
    client_error_message: Callable[[Exception], str | None],
    client_error_request_id: Callable[[Exception], str | None],
    vector_index_arn: str | None = None,
    bedrock_kb_id: str | None = None,
    bedrock_data_source_id: str | None = None,
) -> None:
    """Emit the historical safe, structured AWS provisioning diagnostic line."""
    logger.error(
        "knowledge_base_aws_operation_failed operation=%s aws_service=%s "
        "organization_id=%s knowledge_base_id=%s provisioning_stage=%s "
        "aws_error_code=%s aws_error_message=%s aws_request_id=%s "
        "vector_bucket_arn=%s vector_index_arn=%s bedrock_kb_id=%s "
        "bedrock_data_source_id=%s bedrock_role_arn=%s embedding_model_arn=%s "
        "knowledge_bucket=%s",
        operation,
        aws_service,
        org_id,
        kb_id,
        stage,
        client_error_code(error),
        client_error_message(error),
        client_error_request_id(error),
        context.vector_bucket_arn,
        vector_index_arn,
        bedrock_kb_id,
        bedrock_data_source_id,
        context.bedrock_service_role_arn,
        context.embedding_model_arn,
        context.knowledge_bucket,
        exc_info=(type(error), error, error.__traceback__),
    )
