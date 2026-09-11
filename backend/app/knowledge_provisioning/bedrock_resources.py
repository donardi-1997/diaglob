"""Bedrock Knowledge Base and Data Source infrastructure adapter."""

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
class BedrockResourcesConfig:
    vector_bucket_arn: str
    bedrock_service_role_arn: str
    embedding_model_arn: str
    knowledge_bucket: str
    vector_dimension: int
    vector_embedding_data_type: str
    recovery_attempts: int
    wait_attempts: int


class BedrockResourcesAdapter:
    """Own modern Bedrock Knowledge Base and Data Source provider operations."""

    def __init__(
        self,
        *,
        config: BedrockResourcesConfig,
        client_factory: Callable[[], Any],
        make_kb_name: Callable[[int, int], str],
        make_ds_name: Callable[[int], str],
        make_client_token: Callable[[str, int, int], str],
        make_tags: Callable[[int, int], dict[str, str]],
        tags_match: Callable[[dict[str, str], dict[str, str]], bool],
        get_s3_prefix: Callable[[int, int], str],
        vector_index_arn: Callable[[int], str],
        validate_configuration: Callable[[], None],
        sleep_between_attempts: Callable[[int, int], None],
        log_aws_error: Callable[..., None],
    ) -> None:
        self.config = config
        self._client_factory = client_factory
        self._make_kb_name = make_kb_name
        self._make_ds_name = make_ds_name
        self._make_client_token = make_client_token
        self._make_tags = make_tags
        self._tags_match = tags_match
        self._get_s3_prefix = get_s3_prefix
        self._vector_index_arn = vector_index_arn
        self._validate_configuration = validate_configuration
        self._sleep_between_attempts = sleep_between_attempts
        self._log_aws_error = log_aws_error

    def get_knowledge_base(self, bedrock_kb_id: str) -> dict[str, Any] | None:
        try:
            response = self._client_factory().get_knowledge_base(
                knowledgeBaseId=bedrock_kb_id
            )
            return response.get("knowledgeBase")
        except ClientError as error:
            if _client_error_code(error) == "ResourceNotFoundException":
                return None
            logger.exception("Failed to inspect Bedrock Knowledge Base")
            raise _aws_provisioning_error(
                "bedrock_kb_get_failed",
                "knowledge_base",
                error,
                aws_service="bedrock-agent",
                aws_operation="GetKnowledgeBase",
                classification=classify_provisioning_aws_error(error),
            ) from error
        except BotoCoreError as error:
            logger.exception("Failed to inspect Bedrock Knowledge Base")
            raise _aws_provisioning_error(
                "bedrock_kb_get_failed",
                "knowledge_base",
                error,
                aws_service="bedrock-agent",
                aws_operation="GetKnowledgeBase",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def get_tags(self, resource_arn: str) -> dict[str, str]:
        try:
            return self._client_factory().list_tags_for_resource(
                resourceArn=resource_arn
            ).get("tags", {})
        except (BotoCoreError, ClientError) as error:
            logger.exception("Failed to inspect Bedrock Knowledge Base tags")
            raise _aws_provisioning_error(
                "bedrock_kb_tags_get_failed",
                "knowledge_base",
                error,
                aws_service="bedrock-agent",
                aws_operation="ListTagsForResource",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def validate_knowledge_base(
        self,
        remote: dict[str, Any],
        org_id: int,
        kb_id: int,
        index_arn: str,
    ) -> None:
        if (
            remote.get("name") != self._make_kb_name(org_id, kb_id)
            or remote.get("roleArn") != self.config.bedrock_service_role_arn
        ):
            raise BedrockProvisioningError(
                "resource_ownership_mismatch", resource="knowledge_base"
            )

        storage = remote.get("storageConfiguration", {})
        s3_vectors = storage.get("s3VectorsConfiguration", {})
        configuration = remote.get("knowledgeBaseConfiguration", {})
        vector_configuration = configuration.get(
            "vectorKnowledgeBaseConfiguration", {}
        )
        embedding_configuration = vector_configuration.get(
            "embeddingModelConfiguration", {}
        ).get("bedrockEmbeddingModelConfiguration", {})
        if (
            storage.get("type") != "S3_VECTORS"
            or s3_vectors.get("vectorBucketArn")
            != self.config.vector_bucket_arn
            or s3_vectors.get("indexArn") != index_arn
            or configuration.get("type") != "VECTOR"
            or vector_configuration.get("embeddingModelArn")
            != self.config.embedding_model_arn
            or embedding_configuration.get("dimensions")
            != self.config.vector_dimension
            or embedding_configuration.get("embeddingDataType")
            != self.config.vector_embedding_data_type
        ):
            raise BedrockProvisioningError(
                "bedrock_kb_configuration_mismatch", resource="knowledge_base"
            )

        resource_arn = remote.get("knowledgeBaseArn")
        if not resource_arn or not self._tags_match(
            self.get_tags(resource_arn), self._make_tags(org_id, kb_id)
        ):
            raise BedrockProvisioningError(
                "resource_ownership_mismatch", resource="knowledge_base"
            )

    def _list_knowledge_bases_by_name(
        self, name: str
    ) -> list[dict[str, Any]]:
        client = self._client_factory()
        candidates: list[dict[str, Any]] = []
        next_token = None
        try:
            while True:
                kwargs: dict[str, Any] = {"maxResults": 1000}
                if next_token:
                    kwargs["nextToken"] = next_token
                response = client.list_knowledge_bases(**kwargs)
                candidates.extend(
                    item
                    for item in response.get("knowledgeBaseSummaries", [])
                    if item.get("name") == name
                )
                next_token = response.get("nextToken")
                if not next_token:
                    return candidates
        except (BotoCoreError, ClientError) as error:
            logger.exception("Failed to discover Bedrock Knowledge Base")
            raise _aws_provisioning_error(
                "resource_recovery_failed",
                "knowledge_base",
                error,
                aws_service="bedrock-agent",
                aws_operation="ListKnowledgeBases",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def discover_knowledge_base(
        self, org_id: int, kb_id: int, index_arn: str
    ) -> dict[str, Any] | None:
        expected_name = self._make_kb_name(org_id, kb_id)
        for attempt in range(self.config.recovery_attempts):
            candidates = self._list_knowledge_bases_by_name(expected_name)
            if len(candidates) > 1:
                raise BedrockProvisioningError(
                    "resource_recovery_ambiguous", resource="knowledge_base"
                )
            if candidates:
                remote = self.get_knowledge_base(
                    candidates[0]["knowledgeBaseId"]
                )
                if remote:
                    self.validate_knowledge_base(
                        remote, org_id, kb_id, index_arn
                    )
                    return remote
            self._sleep_between_attempts(
                attempt, self.config.recovery_attempts
            )
        return None

    def create_knowledge_base(
        self,
        org_id: int,
        kb_id: int,
        index_arn: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        self._validate_configuration()
        create_kwargs = {
            "name": self._make_kb_name(org_id, kb_id),
            "description": description
            or f"Diaglob Knowledge Base for organization {org_id}, KB {kb_id}",
            "roleArn": self.config.bedrock_service_role_arn,
            "knowledgeBaseConfiguration": {
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": self.config.embedding_model_arn,
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": self.config.vector_dimension,
                            "embeddingDataType": (
                                self.config.vector_embedding_data_type
                            ),
                        }
                    },
                },
            },
            "storageConfiguration": {
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": {
                    "vectorBucketArn": self.config.vector_bucket_arn,
                    "indexArn": index_arn,
                },
            },
            "clientToken": self._make_client_token("kb", org_id, kb_id),
            "tags": self._make_tags(org_id, kb_id),
        }
        try:
            remote = self._client_factory().create_knowledge_base(
                **create_kwargs
            ).get("knowledgeBase", {})
            if remote.get("knowledgeBaseId"):
                return remote
            logger.warning("Bedrock KB create response omitted the resource ID")
        except (BotoCoreError, ClientError) as error:
            if not _is_uncertain_create_error(error):
                self._log_aws_error(
                    operation="CreateKnowledgeBase",
                    aws_service="bedrock-agent",
                    stage="creating_knowledge_base",
                    org_id=org_id,
                    kb_id=kb_id,
                    error=error,
                    vector_index_arn=index_arn,
                )
                raise _aws_provisioning_error(
                    "bedrock_kb_create_failed",
                    "knowledge_base",
                    error,
                    aws_service="bedrock-agent",
                    aws_operation="CreateKnowledgeBase",
                    classification=classify_provisioning_aws_error(error),
                ) from error
            logger.warning(
                "Bedrock KB create response was uncertain; attempting recovery",
                exc_info=True,
            )

        recovered = self.discover_knowledge_base(org_id, kb_id, index_arn)
        if not recovered:
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="knowledge_base"
            )
        return recovered

    def wait_for_knowledge_base(
        self, bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
    ) -> dict[str, Any]:
        for attempt in range(self.config.wait_attempts):
            remote = self.get_knowledge_base(bedrock_kb_id)
            if remote:
                self.validate_knowledge_base(
                    remote, org_id, kb_id, index_arn
                )
                status = remote.get("status")
                if status == "ACTIVE":
                    return remote
                if status in {"FAILED", "DELETE_UNSUCCESSFUL"}:
                    raise BedrockProvisioningError(
                        "bedrock_kb_not_active", resource="knowledge_base"
                    )
            self._sleep_between_attempts(attempt, self.config.wait_attempts)
        raise BedrockProvisioningError(
            "bedrock_kb_activation_timeout", resource="knowledge_base"
        )

    def get_data_source(
        self, bedrock_kb_id: str, data_source_id: str
    ) -> dict[str, Any] | None:
        try:
            response = self._client_factory().get_data_source(
                knowledgeBaseId=bedrock_kb_id,
                dataSourceId=data_source_id,
            )
            return response.get("dataSource")
        except ClientError as error:
            if _client_error_code(error) == "ResourceNotFoundException":
                return None
            logger.exception("Failed to inspect Bedrock Data Source")
            raise _aws_provisioning_error(
                "bedrock_data_source_get_failed",
                "data_source",
                error,
                aws_service="bedrock-agent",
                aws_operation="GetDataSource",
                classification=classify_provisioning_aws_error(error),
            ) from error
        except BotoCoreError as error:
            logger.exception("Failed to inspect Bedrock Data Source")
            raise _aws_provisioning_error(
                "bedrock_data_source_get_failed",
                "data_source",
                error,
                aws_service="bedrock-agent",
                aws_operation="GetDataSource",
                classification=classify_provisioning_aws_error(error),
            ) from error

    def validate_data_source(
        self,
        remote: dict[str, Any],
        bedrock_kb_id: str,
        org_id: int,
        kb_id: int,
    ) -> None:
        s3_configuration = remote.get("dataSourceConfiguration", {}).get(
            "s3Configuration", {}
        )
        chunking = remote.get("vectorIngestionConfiguration", {}).get(
            "chunkingConfiguration", {}
        )
        fixed_size = chunking.get("fixedSizeChunkingConfiguration", {})
        if (
            remote.get("knowledgeBaseId") != bedrock_kb_id
            or remote.get("name") != self._make_ds_name(kb_id)
            or remote.get("dataSourceConfiguration", {}).get("type") != "S3"
            or s3_configuration.get("bucketArn")
            != f"arn:aws:s3:::{self.config.knowledge_bucket}"
            or s3_configuration.get("inclusionPrefixes")
            != [self._get_s3_prefix(org_id, kb_id)]
            or remote.get("dataDeletionPolicy") != "DELETE"
            or chunking.get("chunkingStrategy") != "FIXED_SIZE"
            or fixed_size.get("maxTokens") != 300
            or fixed_size.get("overlapPercentage") != 20
        ):
            raise BedrockProvisioningError(
                "resource_ownership_mismatch", resource="data_source"
            )

    def discover_data_source(
        self, bedrock_kb_id: str, org_id: int, kb_id: int
    ) -> dict[str, Any] | None:
        expected_name = self._make_ds_name(kb_id)
        for attempt in range(self.config.recovery_attempts):
            client = self._client_factory()
            candidates: list[dict[str, Any]] = []
            next_token = None
            try:
                while True:
                    kwargs: dict[str, Any] = {
                        "knowledgeBaseId": bedrock_kb_id,
                        "maxResults": 1000,
                    }
                    if next_token:
                        kwargs["nextToken"] = next_token
                    response = client.list_data_sources(**kwargs)
                    candidates.extend(
                        item
                        for item in response.get("dataSourceSummaries", [])
                        if item.get("name") == expected_name
                    )
                    next_token = response.get("nextToken")
                    if not next_token:
                        break
            except (BotoCoreError, ClientError) as error:
                logger.exception("Failed to discover Bedrock Data Source")
                raise _aws_provisioning_error(
                    "resource_recovery_failed",
                    "data_source",
                    error,
                    aws_service="bedrock-agent",
                    aws_operation="ListDataSources",
                    classification=classify_provisioning_aws_error(error),
                ) from error

            if len(candidates) > 1:
                raise BedrockProvisioningError(
                    "resource_recovery_ambiguous", resource="data_source"
                )
            if candidates:
                remote = self.get_data_source(
                    bedrock_kb_id, candidates[0]["dataSourceId"]
                )
                if remote:
                    self.validate_data_source(
                        remote, bedrock_kb_id, org_id, kb_id
                    )
                    return remote
            self._sleep_between_attempts(
                attempt, self.config.recovery_attempts
            )
        return None

    def create_data_source(
        self, bedrock_kb_id: str, org_id: int, kb_id: int
    ) -> dict[str, Any]:
        create_kwargs = {
            "knowledgeBaseId": bedrock_kb_id,
            "name": self._make_ds_name(kb_id),
            "description": f"Diaglob S3 Data Source for org {org_id}, KB {kb_id}",
            "dataSourceConfiguration": {
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{self.config.knowledge_bucket}",
                    "inclusionPrefixes": [self._get_s3_prefix(org_id, kb_id)],
                },
            },
            "vectorIngestionConfiguration": {
                "chunkingConfiguration": {
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": 300,
                        "overlapPercentage": 20,
                    },
                },
            },
            "dataDeletionPolicy": "DELETE",
            "clientToken": self._make_client_token("ds", org_id, kb_id),
        }
        try:
            remote = self._client_factory().create_data_source(
                **create_kwargs
            ).get("dataSource", {})
            if remote.get("dataSourceId"):
                return remote
            logger.warning(
                "Bedrock Data Source create response omitted the resource ID"
            )
        except (BotoCoreError, ClientError) as error:
            if not _is_uncertain_create_error(error):
                self._log_aws_error(
                    operation="CreateDataSource",
                    aws_service="bedrock-agent",
                    stage="creating_data_source",
                    org_id=org_id,
                    kb_id=kb_id,
                    error=error,
                    vector_index_arn=self._vector_index_arn(kb_id),
                    bedrock_kb_id=bedrock_kb_id,
                )
                raise _aws_provisioning_error(
                    "bedrock_data_source_create_failed",
                    "data_source",
                    error,
                    aws_service="bedrock-agent",
                    aws_operation="CreateDataSource",
                    classification=classify_provisioning_aws_error(error),
                ) from error
            logger.warning(
                "Bedrock Data Source create response was uncertain; "
                "attempting recovery",
                exc_info=True,
            )

        parent = self.get_knowledge_base(bedrock_kb_id)
        if not parent:
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="data_source"
            )
        self.validate_knowledge_base(
            parent, org_id, kb_id, self._vector_index_arn(kb_id)
        )
        if parent.get("status") != "ACTIVE":
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="data_source"
            )

        recovered = self.discover_data_source(bedrock_kb_id, org_id, kb_id)
        if not recovered:
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="data_source"
            )
        return recovered

    def wait_for_data_source(
        self,
        bedrock_kb_id: str,
        data_source_id: str,
        org_id: int,
        kb_id: int,
    ) -> dict[str, Any]:
        for attempt in range(self.config.wait_attempts):
            remote = self.get_data_source(bedrock_kb_id, data_source_id)
            if remote:
                self.validate_data_source(
                    remote, bedrock_kb_id, org_id, kb_id
                )
                status = remote.get("status")
                if status == "AVAILABLE":
                    return remote
                if status in {"FAILED", "DELETE_UNSUCCESSFUL"}:
                    raise BedrockProvisioningError(
                        "bedrock_data_source_not_available",
                        resource="data_source",
                    )
            self._sleep_between_attempts(attempt, self.config.wait_attempts)
        raise BedrockProvisioningError(
            "bedrock_data_source_activation_timeout", resource="data_source"
        )

    def delete_data_source(
        self,
        bedrock_kb_id: str,
        data_source_id: str,
        org_id: int,
        kb_id: int,
        index_arn: str,
    ) -> None:
        parent = self.get_knowledge_base(bedrock_kb_id)
        if not parent:
            return
        self.validate_knowledge_base(parent, org_id, kb_id, index_arn)
        remote = self.get_data_source(bedrock_kb_id, data_source_id)
        if not remote:
            return
        self.validate_data_source(remote, bedrock_kb_id, org_id, kb_id)
        try:
            self._client_factory().delete_data_source(
                knowledgeBaseId=bedrock_kb_id,
                dataSourceId=data_source_id,
            )
        except (BotoCoreError, ClientError) as error:
            if _client_error_code(error) == "ResourceNotFoundException":
                return
            self._log_aws_error(
                operation="DeleteDataSource",
                aws_service="bedrock-agent",
                stage="deleting",
                org_id=org_id,
                kb_id=kb_id,
                error=error,
                vector_index_arn=index_arn,
                bedrock_kb_id=bedrock_kb_id,
                bedrock_data_source_id=data_source_id,
            )
            raise _aws_provisioning_error(
                "bedrock_data_source_delete_failed",
                "data_source",
                error,
                aws_service="bedrock-agent",
                aws_operation="DeleteDataSource",
            ) from error

        for attempt in range(self.config.wait_attempts):
            remote = self.get_data_source(bedrock_kb_id, data_source_id)
            if remote is None:
                return
            if remote.get("status") == "DELETE_UNSUCCESSFUL":
                break
            self._sleep_between_attempts(attempt, self.config.wait_attempts)
        raise BedrockProvisioningError(
            "bedrock_data_source_delete_unconfirmed", resource="data_source"
        )

    def delete_knowledge_base(
        self, bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
    ) -> None:
        remote = self.get_knowledge_base(bedrock_kb_id)
        if not remote:
            return
        self.validate_knowledge_base(remote, org_id, kb_id, index_arn)
        try:
            self._client_factory().delete_knowledge_base(
                knowledgeBaseId=bedrock_kb_id
            )
        except (BotoCoreError, ClientError) as error:
            if _client_error_code(error) == "ResourceNotFoundException":
                return
            self._log_aws_error(
                operation="DeleteKnowledgeBase",
                aws_service="bedrock-agent",
                stage="deleting",
                org_id=org_id,
                kb_id=kb_id,
                error=error,
                vector_index_arn=index_arn,
                bedrock_kb_id=bedrock_kb_id,
            )
            raise _aws_provisioning_error(
                "bedrock_kb_delete_failed",
                "knowledge_base",
                error,
                aws_service="bedrock-agent",
                aws_operation="DeleteKnowledgeBase",
            ) from error

        for attempt in range(self.config.wait_attempts):
            remote = self.get_knowledge_base(bedrock_kb_id)
            if remote is None:
                return
            if remote.get("status") == "DELETE_UNSUCCESSFUL":
                break
            self._sleep_between_attempts(attempt, self.config.wait_attempts)
        raise BedrockProvisioningError(
            "bedrock_kb_delete_unconfirmed", resource="knowledge_base"
        )


__all__ = ["BedrockResourcesAdapter", "BedrockResourcesConfig"]
