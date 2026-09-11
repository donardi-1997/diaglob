"""Boundary tests for Knowledge Base deletion orchestration."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app import bedrock_knowledge_base as provisioning
from app.knowledge_provisioning.cleanup import CleanupResult
from app.knowledge_provisioning.deletion import (
    DeletionOperations,
    cleanup_owned_resources,
    delete_knowledge_base,
)
from app.knowledge_provisioning.errors import BedrockProvisioningError


INDEX_ARN = "arn:aws:s3vectors:us-east-2:123456789012:bucket/test/index/test"


def _operations(**overrides):
    values = {
        "vector_index_arn": MagicMock(return_value=INDEX_ARN),
        "cleanup_remote_resources": MagicMock(
            return_value=CleanupResult(True, None, None)
        ),
        "commit_state": MagicMock(),
        "is_verified_legacy_parent": MagicMock(return_value=False),
        "cleanup_verified_legacy_resources": MagicMock(),
        "delete_knowledge_prefix": MagicMock(),
        "client_error_code": MagicMock(return_value=None),
        "client_error_message": MagicMock(return_value=None),
        "client_error_request_id": MagicMock(return_value=None),
    }
    values.update(overrides)
    return DeletionOperations(**values)


def _knowledge_base(**overrides):
    values = {
        "id": 11,
        "organization_id": 7,
        "external_id": "kb-id",
        "external_data_source_id": "ds-id",
        "external_status": "ready",
        "external_last_error": None,
        "provisioning_stage": "ready",
        "provisioning_stage_started_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _db_with_successful_claim():
    db = MagicMock()
    db.query.return_value.filter.return_value.update.return_value = 1
    return db


def test_facade_builds_deletion_operations_from_current_callables(monkeypatch):
    replacements = {
        "_vector_index_arn": MagicMock(name="vector_index_arn"),
        "_cleanup_remote_resources": MagicMock(name="cleanup_remote"),
        "_commit_state": MagicMock(name="commit"),
        "is_verified_legacy_parent": MagicMock(name="legacy_check"),
        "cleanup_verified_legacy_resources": MagicMock(name="legacy_cleanup"),
        "delete_knowledge_prefix": MagicMock(name="delete_prefix"),
        "_client_error_code": MagicMock(name="error_code"),
        "_client_error_message": MagicMock(name="error_message"),
        "_client_error_request_id": MagicMock(name="request_id"),
    }
    for name, replacement in replacements.items():
        monkeypatch.setattr(provisioning, name, replacement)

    operations = provisioning._deletion_operations()

    assert operations.vector_index_arn is replacements["_vector_index_arn"]
    assert operations.cleanup_remote_resources is replacements["_cleanup_remote_resources"]
    assert operations.commit_state is replacements["_commit_state"]
    assert operations.is_verified_legacy_parent is replacements["is_verified_legacy_parent"]
    assert operations.cleanup_verified_legacy_resources is replacements[
        "cleanup_verified_legacy_resources"
    ]
    assert operations.delete_knowledge_prefix is replacements["delete_knowledge_prefix"]
    assert operations.client_error_code is replacements["_client_error_code"]
    assert operations.client_error_message is replacements["_client_error_message"]
    assert operations.client_error_request_id is replacements["_client_error_request_id"]


def test_cleanup_facade_delegates_with_call_time_operations(monkeypatch):
    db = object()
    knowledge_base = object()
    sentinel = MagicMock(name="cleanup_remote")
    captured = {}

    monkeypatch.setattr(provisioning, "_cleanup_remote_resources", sentinel)

    def fake_cleanup(received_db, received_kb, *, operations):
        captured["db"] = received_db
        captured["kb"] = received_kb
        captured["operations"] = operations

    monkeypatch.setattr(provisioning, "cleanup_owned_resources", fake_cleanup)

    provisioning.cleanup_bedrock_resources(db, knowledge_base)

    assert captured["db"] is db
    assert captured["kb"] is knowledge_base
    assert captured["operations"].cleanup_remote_resources is sentinel


def test_delete_facade_delegates_with_call_time_operations(monkeypatch):
    db = object()
    knowledge_base = object()
    sentinel = MagicMock(name="legacy_cleanup")
    captured = {}

    monkeypatch.setattr(provisioning, "cleanup_verified_legacy_resources", sentinel)

    def fake_delete(received_db, received_kb, *, operations):
        captured["db"] = received_db
        captured["kb"] = received_kb
        captured["operations"] = operations

    monkeypatch.setattr(provisioning, "delete_knowledge_base", fake_delete)

    provisioning.delete_diaglob_knowledge_base(db, knowledge_base)

    assert captured["db"] is db
    assert captured["kb"] is knowledge_base
    assert captured["operations"].cleanup_verified_legacy_resources is sentinel


def test_cleanup_owned_resources_preserves_missing_index_arn_fallback():
    db = MagicMock()
    knowledge_base = _knowledge_base()
    vector_error = BedrockProvisioningError(
        "vector_bucket_not_configured",
        resource="configuration",
    )
    cleanup = MagicMock(return_value=CleanupResult(True, None, None))
    operations = _operations(
        vector_index_arn=MagicMock(side_effect=vector_error),
        cleanup_remote_resources=cleanup,
    )

    cleanup_owned_resources(db, knowledge_base, operations=operations)

    cleanup.assert_called_once_with(7, 11, None, "kb-id", "ds-id")
    assert knowledge_base.external_id is None
    assert knowledge_base.external_data_source_id is None
    assert knowledge_base.external_status == "failed"
    assert knowledge_base.external_last_error == "resources_cleaned"
    operations.commit_state.assert_called_once_with(db, "failure_state_persist_failed")


def test_legacy_deletion_routes_only_to_verified_legacy_cleanup():
    db = _db_with_successful_claim()
    knowledge_base = _knowledge_base(external_id="legacy-kb")
    legacy_cleanup = MagicMock()
    modern_cleanup = MagicMock()
    operations = _operations(
        is_verified_legacy_parent=MagicMock(return_value=True),
        cleanup_verified_legacy_resources=legacy_cleanup,
        cleanup_remote_resources=modern_cleanup,
    )

    delete_knowledge_base(db, knowledge_base, operations=operations)

    legacy_cleanup.assert_called_once_with(db, knowledge_base)
    modern_cleanup.assert_not_called()
    operations.vector_index_arn.assert_not_called()
    operations.delete_knowledge_prefix.assert_not_called()


def test_modern_deletion_never_invokes_legacy_cleanup():
    db = _db_with_successful_claim()
    knowledge_base = _knowledge_base()
    operations = _operations()

    delete_knowledge_base(db, knowledge_base, operations=operations)

    operations.cleanup_verified_legacy_resources.assert_not_called()
    operations.vector_index_arn.assert_called_once_with(11)
    operations.cleanup_remote_resources.assert_called_once_with(
        7,
        11,
        INDEX_ARN,
        "kb-id",
        "ds-id",
    )
    operations.delete_knowledge_prefix.assert_called_once_with(7, 11)
    db.delete.assert_called_once_with(knowledge_base)
    operations.commit_state.assert_any_call(db, "deletion_state_persist_failed")
