"""S3 Vectors infrastructure adapter for Knowledge provisioning."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from botocore.exceptions import BotoCoreError, ClientError

from .errors import (
    BedrockProvisioningError,
    _aws_provisioning_error,
    _client_error_code,
    _is_uncertain_create_error,
    classify_provisioning_aws_error,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3VectorsConfig:
    vector_bucket_arn: str
    environment: str
    vector_dimension: int
    vector_data_type: str
    vector_distance_metric: str
    non_filterable_metadata_keys: tuple[str, ...]
    recovery_attempts: int
    wait_attempts: int


class S3VectorsAdapter:
    """Own S3 Vectors resource operations behind explicit dependencies."""

    def __init__(
        self,
        *,
        config: S3VectorsConfig,
        client_factory: Callable[[], Any],
        vector_index_arn: Callable[[int], str],
        build_vector_index_name: Callable[[str, int], str],
        make_tags: Callable[[int, int], dict[str, str]],
        tags_match: Callable[[dict[str, str], dict[str, str]], bool],
        sleep_between_attempts: Callable[[int, int], None],
        validate_configuration: Callable[[], None],
        log_aws_error: Callable[..., None],
    ) -> None:
        self.config = config
        self._client_factory = client_factory
        self._vector_index_arn = vector_index_arn
        self._build_vector_index_name = build_vector_index_name
        self._make_tags = make_tags
        self._tags_match = tags_match
        self._sleep_between_attempts = sleep_between_attempts
        self._validate_configuration = validate_configuration
        self._log_aws_error = log_aws_error

    def get_index(self, index_arn: str) -> dict[str, Any] | None:
        """Return an S3 Vectors index, or None when it does not exist."""
        try:
            return self._client_factory().get_index(indexArn=index_arn).get(
                "index"
            )
        except ClientError as error:
            if _client_error_code(error) == "NotFoundException":
                return None
            logger.exception("Failed to inspect managed S3 Vectors index")
            raise _aws_provisioning_error(
                "vector_index_get_failed",
                "vector_index",
                error,
                aws_service="s3vectors",
                aws_operation="GetIndex",
                classification=classify_provisioning_aws_error(error),
            ) from error
        except BotoCoreError as error:
            logger.exception("Failed to inspect managed S3 Vectors index")
            raise _aws_provisioning_error(
                "vector_index_get_failed",
                "vector_index",
                error,
                aws_service="s3vectors",
                aws_operation="GetIndex",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def get_tags(self, index_arn: str) -> dict[str, str]:
        try:
            return self._client_factory().list_tags_for_resource(
                resourceArn=index_arn
            ).get("tags", {})
        except (BotoCoreError, ClientError) as error:
            logger.exception("Failed to inspect managed S3 Vectors index tags")
            raise _aws_provisioning_error(
                "vector_index_tags_get_failed",
                "vector_index",
                error,
                aws_service="s3vectors",
                aws_operation="ListTagsForResource",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def validate_index(
        self,
        index: dict[str, Any],
        tags: dict[str, str],
        org_id: int,
        kb_id: int,
    ) -> None:
        expected_arn = self._vector_index_arn(kb_id)
        expected_name = self._build_vector_index_name(
            self.config.environment, kb_id
        )
        if (
            index.get("indexArn") != expected_arn
            or index.get("indexName") != expected_name
            or not self._tags_match(tags, self._make_tags(org_id, kb_id))
        ):
            raise BedrockProvisioningError(
                "resource_ownership_mismatch", resource="vector_index"
            )

        metadata_keys = set(
            index.get("metadataConfiguration", {}).get(
                "nonFilterableMetadataKeys", []
            )
        )
        if (
            index.get("dataType") != self.config.vector_data_type
            or index.get("dimension") != self.config.vector_dimension
            or index.get("distanceMetric")
            != self.config.vector_distance_metric
            or not set(self.config.non_filterable_metadata_keys).issubset(
                metadata_keys
            )
        ):
            raise BedrockProvisioningError(
                "vector_index_configuration_mismatch", resource="vector_index"
            )

    def recover_index(
        self, org_id: int, kb_id: int
    ) -> dict[str, Any] | None:
        index_arn = self._vector_index_arn(kb_id)
        for attempt in range(self.config.recovery_attempts):
            index = self.get_index(index_arn)
            if index:
                self.validate_index(
                    index,
                    self.get_tags(index_arn),
                    org_id,
                    kb_id,
                )
                return index
            self._sleep_between_attempts(
                attempt, self.config.recovery_attempts
            )
        return None

    def create_index(self, org_id: int, kb_id: int) -> dict[str, Any]:
        """Create or safely recover the deterministic S3 Vectors index."""
        self._validate_configuration()
        index_name = self._build_vector_index_name(
            self.config.environment, kb_id
        )
        index_arn = self._vector_index_arn(kb_id)
        try:
            response = self._client_factory().create_index(
                vectorBucketArn=self.config.vector_bucket_arn,
                indexName=index_name,
                dataType=self.config.vector_data_type,
                dimension=self.config.vector_dimension,
                distanceMetric=self.config.vector_distance_metric,
                metadataConfiguration={
                    "nonFilterableMetadataKeys": list(
                        self.config.non_filterable_metadata_keys
                    )
                },
                tags=self._make_tags(org_id, kb_id),
            )
            if response.get("indexArn") != index_arn:
                raise BedrockProvisioningError(
                    "vector_index_create_failed", resource="vector_index"
                )
        except BedrockProvisioningError:
            raise
        except (BotoCoreError, ClientError) as error:
            if not _is_uncertain_create_error(error):
                self._log_aws_error(
                    operation="CreateIndex",
                    aws_service="s3vectors",
                    stage="creating_vector_index",
                    org_id=org_id,
                    kb_id=kb_id,
                    error=error,
                    vector_index_arn=index_arn,
                )
                raise _aws_provisioning_error(
                    "vector_index_create_failed",
                    "vector_index",
                    error,
                    aws_service="s3vectors",
                    aws_operation="CreateIndex",
                    classification=classify_provisioning_aws_error(error),
                ) from error
            logger.warning(
                "S3 Vectors index create response was uncertain; "
                "attempting recovery",
                exc_info=True,
            )

        recovered = self.recover_index(org_id, kb_id)
        if not recovered:
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="vector_index"
            )
        return recovered

    def delete_index(self, index_arn: str, org_id: int, kb_id: int) -> None:
        """Delete only the owned deterministic index and confirm absence."""
        if index_arn != self._vector_index_arn(kb_id):
            raise BedrockProvisioningError(
                "resource_ownership_mismatch", resource="vector_index"
            )
        index = self.get_index(index_arn)
        if not index:
            return
        self.validate_index(
            index,
            self.get_tags(index_arn),
            org_id,
            kb_id,
        )
        try:
            self._client_factory().delete_index(indexArn=index_arn)
        except (BotoCoreError, ClientError) as error:
            if _client_error_code(error) == "NotFoundException":
                return
            self._log_aws_error(
                operation="DeleteIndex",
                aws_service="s3vectors",
                stage="deleting",
                org_id=org_id,
                kb_id=kb_id,
                error=error,
                vector_index_arn=index_arn,
            )
            raise _aws_provisioning_error(
                "vector_index_delete_failed",
                "vector_index",
                error,
                aws_service="s3vectors",
                aws_operation="DeleteIndex",
            ) from error

        for attempt in range(self.config.wait_attempts):
            if self.get_index(index_arn) is None:
                return
            self._sleep_between_attempts(
                attempt, self.config.wait_attempts
            )
        raise BedrockProvisioningError(
            "vector_index_delete_unconfirmed", resource="vector_index"
        )


__all__ = ["S3VectorsAdapter", "S3VectorsConfig"]
