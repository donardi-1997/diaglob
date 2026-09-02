"""Run disposable AWS Knowledge Base provisioning smoke checks.

This script deliberately refuses to run outside the production API identity. It
does not create or mutate database rows and it never targets existing resources.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


REGION = "us-east-2"
ACCOUNT_ID = "765761474007"
PRODUCTION_PRINCIPAL_ARN = (
    "arn:aws:iam::765761474007:user/diaglob-prod-knowledge"
)
VECTOR_BUCKET_ARN = (
    "arn:aws:s3vectors:us-east-2:765761474007:bucket/"
    "diaglob-vectors-765761474007-us-east-2"
)
KNOWLEDGE_BUCKET = "diaglob-knowledge-765761474007-us-east-2"
BEDROCK_SERVICE_ROLE_ARN = (
    "arn:aws:iam::765761474007:role/DiaglobBedrockKnowledgeBaseRole"
)


def emit(event: str, **details: Any) -> None:
    print(json.dumps({"event": event, **details}, sort_keys=True), flush=True)


def elapsed_seconds(started_at: float) -> float:
    return round(time.monotonic() - started_at, 3)


def aws_error_details(error: Exception) -> dict[str, str | None]:
    current: BaseException | None = error
    while current:
        if isinstance(current, ClientError):
            aws_error = current.response.get("Error", {})
            return {
                "exception_class": type(current).__name__,
                "aws_error_code": aws_error.get("Code"),
                "aws_error_message": " ".join(
                    str(aws_error.get("Message", "")).split()
                )[:500],
            }
        current = current.__cause__
    return {
        "exception_class": type(error).__name__,
        "aws_error_code": None,
        "aws_error_message": str(error)[:500],
    }


def require_safe_environment() -> dict[str, str]:
    if os.getenv("DIAGLOB_AWS_SMOKE_TEST") != "1":
        raise RuntimeError("DIAGLOB_AWS_SMOKE_TEST=1 is required")

    required = {
        "AWS_REGION": REGION,
        "DIAGLOB_ENVIRONMENT": "production",
        "DIAGLOB_VECTOR_BUCKET_ARN": VECTOR_BUCKET_ARN,
        "DIAGLOB_KNOWLEDGE_BUCKET": KNOWLEDGE_BUCKET,
        "BEDROCK_SERVICE_ROLE_ARN": BEDROCK_SERVICE_ROLE_ARN,
    }
    mismatched = [
        key for key, expected in required.items() if os.getenv(key, "").strip() != expected
    ]
    if mismatched:
        raise RuntimeError(
            "Required production configuration is missing or unexpected: "
            + ", ".join(mismatched)
        )
    return required


def wait_for_status(
    get_resource: Any,
    validate_resource: Any,
    target_status: str,
    terminal_statuses: set[str],
    timeout_seconds: int = 180,
) -> tuple[dict[str, Any], list[str]]:
    started_at = time.monotonic()
    transitions: list[str] = []
    previous_status: str | None = None
    while elapsed_seconds(started_at) < timeout_seconds:
        resource = get_resource()
        if resource is None:
            raise RuntimeError("Resource disappeared while waiting for status")
        validate_resource(resource)
        status = str(resource.get("status"))
        if status != previous_status:
            transitions.append(status)
            emit("status_transition", status=status)
            previous_status = status
        if status == target_status:
            return resource, transitions
        if status in terminal_statuses:
            raise RuntimeError(f"Resource reached terminal status {status}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {target_status}")


def main() -> int:
    try:
        require_safe_environment()
    except RuntimeError as error:
        emit("refused", reason=str(error))
        return 2

    identity = boto3.client("sts", region_name=REGION).get_caller_identity()
    emit(
        "caller_identity",
        account=identity["Account"],
        arn=identity["Arn"],
        user_id=identity["UserId"],
    )
    if identity["Account"] != ACCOUNT_ID or identity["Arn"] != PRODUCTION_PRINCIPAL_ARN:
        emit(
            "refused",
            reason="Smoke tests must run with the production diaglob-api IAM identity",
            expected_principal_arn=PRODUCTION_PRINCIPAL_ARN,
        )
        return 2

    # Import after validating environment so application configuration is exact.
    from app import bedrock_knowledge_base as provisioning

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    org_id = 900_000_000 + secrets.randbelow(90_000_000)
    kb_id = 1_900_000_000 + secrets.randbelow(90_000_000)
    index_arn = provisioning._vector_index_arn(kb_id)
    index_name = provisioning.build_vector_index_name(provisioning.ENVIRONMENT, kb_id)
    created: dict[str, str | None] = {
        "index_arn": index_arn,
        "bedrock_kb_id": None,
        "data_source_id": None,
    }
    cleanup_errors: list[dict[str, Any]] = []
    succeeded = False

    emit(
        "smoke_started",
        smoke_suffix=f"smoke-{suffix}",
        organization_id=org_id,
        knowledge_base_id=kb_id,
        index_name=index_name,
        index_arn=index_arn,
    )
    try:
        if provisioning.get_s3_vectors_index(index_arn) is not None:
            raise RuntimeError("Generated disposable vector index already exists")

        started_at = time.monotonic()
        index = provisioning.create_s3_vectors_index(org_id, kb_id)
        emit(
            "vector_create_succeeded",
            index_arn=index.get("indexArn"),
            elapsed_seconds=elapsed_seconds(started_at),
        )

        started_at = time.monotonic()
        index = provisioning.get_s3_vectors_index(index_arn)
        if not index:
            raise RuntimeError("GetIndex returned no disposable index after CreateIndex")
        tags = provisioning._get_s3_vectors_tags(index_arn)
        provisioning._validate_s3_vectors_index(index, tags, org_id, kb_id)
        emit(
            "vector_get_and_ownership_succeeded",
            dimension=index.get("dimension"),
            data_type=index.get("dataType"),
            distance_metric=index.get("distanceMetric"),
            tags=tags,
            elapsed_seconds=elapsed_seconds(started_at),
        )

        started_at = time.monotonic()
        bedrock_kb = provisioning.create_bedrock_knowledge_base(org_id, kb_id, index_arn)
        created["bedrock_kb_id"] = bedrock_kb["knowledgeBaseId"]
        emit(
            "bedrock_kb_create_succeeded",
            bedrock_kb_id=created["bedrock_kb_id"],
            initial_status=bedrock_kb.get("status"),
            elapsed_seconds=elapsed_seconds(started_at),
        )

        started_at = time.monotonic()
        _, kb_transitions = wait_for_status(
            lambda: provisioning.get_bedrock_knowledge_base(created["bedrock_kb_id"]),
            lambda resource: provisioning._validate_bedrock_knowledge_base(
                resource, org_id, kb_id, index_arn
            ),
            "ACTIVE",
            {"FAILED", "DELETE_UNSUCCESSFUL"},
        )
        emit(
            "bedrock_kb_active",
            bedrock_kb_id=created["bedrock_kb_id"],
            transitions=kb_transitions,
            elapsed_seconds=elapsed_seconds(started_at),
        )

        started_at = time.monotonic()
        data_source = provisioning.create_bedrock_data_source(
            created["bedrock_kb_id"], org_id, kb_id
        )
        created["data_source_id"] = data_source["dataSourceId"]
        emit(
            "data_source_create_succeeded",
            data_source_id=created["data_source_id"],
            initial_status=data_source.get("status"),
            prefix=provisioning._get_s3_prefix(org_id, kb_id),
            elapsed_seconds=elapsed_seconds(started_at),
        )

        started_at = time.monotonic()
        _, data_source_transitions = wait_for_status(
            lambda: provisioning.get_bedrock_data_source(
                created["bedrock_kb_id"], created["data_source_id"]
            ),
            lambda resource: provisioning._validate_bedrock_data_source(
                resource, created["bedrock_kb_id"], org_id, kb_id
            ),
            "AVAILABLE",
            {"FAILED", "DELETE_UNSUCCESSFUL"},
        )
        emit(
            "data_source_available",
            data_source_id=created["data_source_id"],
            transitions=data_source_transitions,
            elapsed_seconds=elapsed_seconds(started_at),
        )
        succeeded = True
        emit(
            "service_level_provisioning",
            status="not_run",
            reason="provision_diaglob_knowledge_base requires a database record; this smoke test intentionally does not mutate production data",
        )
    except Exception as error:
        emit("smoke_failed", stage="provisioning", **aws_error_details(error))
    finally:
        if created["data_source_id"] and created["bedrock_kb_id"]:
            try:
                provisioning.delete_bedrock_data_source(
                    created["bedrock_kb_id"],
                    created["data_source_id"],
                    org_id,
                    kb_id,
                    index_arn,
                )
                emit("cleanup_succeeded", resource="data_source", resource_id=created["data_source_id"])
            except Exception as error:
                cleanup_errors.append({"resource": "data_source", **aws_error_details(error)})
        if created["bedrock_kb_id"]:
            try:
                provisioning.delete_bedrock_knowledge_base(
                    created["bedrock_kb_id"], org_id, kb_id, index_arn
                )
                emit("cleanup_succeeded", resource="bedrock_knowledge_base", resource_id=created["bedrock_kb_id"])
            except Exception as error:
                cleanup_errors.append({"resource": "bedrock_knowledge_base", **aws_error_details(error)})
        try:
            provisioning.delete_s3_vectors_index(index_arn, org_id, kb_id)
            emit("cleanup_succeeded", resource="vector_index", resource_id=index_arn)
        except Exception as error:
            cleanup_errors.append({"resource": "vector_index", **aws_error_details(error)})

    for error in cleanup_errors:
        emit("cleanup_failed", **error)
    return 0 if succeeded and not cleanup_errors else 1


if __name__ == "__main__":
    sys.exit(main())
