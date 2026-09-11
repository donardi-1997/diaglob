"""Boundary tests for Knowledge Base provisioning orchestration."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import bedrock_knowledge_base as provisioning
from app.knowledge_provisioning.errors import BedrockProvisioningError
from app.knowledge_provisioning.orchestrator import (
    ProvisioningOperations,
    provision_knowledge_base,
)


def _operations(**overrides):
    values = {
        "claim_provisioning": MagicMock(),
        "create_vector_index": MagicMock(),
        "set_stage": MagicMock(),
        "get_knowledge_base": MagicMock(),
        "wait_for_knowledge_base": MagicMock(),
        "create_knowledge_base": MagicMock(),
        "commit_state": MagicMock(),
        "get_data_source": MagicMock(),
        "wait_for_data_source": MagicMock(),
        "create_data_source": MagicMock(),
        "cleanup_remote_resources": MagicMock(),
        "as_utc": MagicMock(),
    }
    values.update(overrides)
    return ProvisioningOperations(**values)


def test_facade_builds_operations_from_current_callables(monkeypatch):
    replacements = {
        "_claim_provisioning": MagicMock(name="claim"),
        "create_s3_vectors_index": MagicMock(name="create_vector"),
        "_set_provisioning_stage": MagicMock(name="stage"),
        "get_bedrock_knowledge_base": MagicMock(name="get_kb"),
        "wait_for_bedrock_knowledge_base": MagicMock(name="wait_kb"),
        "create_bedrock_knowledge_base": MagicMock(name="create_kb"),
        "_commit_state": MagicMock(name="commit"),
        "get_bedrock_data_source": MagicMock(name="get_ds"),
        "wait_for_bedrock_data_source": MagicMock(name="wait_ds"),
        "create_bedrock_data_source": MagicMock(name="create_ds"),
        "_cleanup_remote_resources": MagicMock(name="cleanup"),
        "_as_utc": MagicMock(name="as_utc"),
    }
    for name, replacement in replacements.items():
        monkeypatch.setattr(provisioning, name, replacement)

    operations = provisioning._provisioning_operations()

    assert operations.claim_provisioning is replacements["_claim_provisioning"]
    assert operations.create_vector_index is replacements["create_s3_vectors_index"]
    assert operations.set_stage is replacements["_set_provisioning_stage"]
    assert operations.get_knowledge_base is replacements["get_bedrock_knowledge_base"]
    assert operations.wait_for_knowledge_base is replacements["wait_for_bedrock_knowledge_base"]
    assert operations.create_knowledge_base is replacements["create_bedrock_knowledge_base"]
    assert operations.commit_state is replacements["_commit_state"]
    assert operations.get_data_source is replacements["get_bedrock_data_source"]
    assert operations.wait_for_data_source is replacements["wait_for_bedrock_data_source"]
    assert operations.create_data_source is replacements["create_bedrock_data_source"]
    assert operations.cleanup_remote_resources is replacements["_cleanup_remote_resources"]
    assert operations.as_utc is replacements["_as_utc"]


def test_facade_delegates_with_operations_captured_at_call_time(monkeypatch):
    db = object()
    knowledge_base = object()
    sentinel_operation = MagicMock(name="create_vector")
    captured = {}

    monkeypatch.setattr(provisioning, "create_s3_vectors_index", sentinel_operation)

    def fake_orchestrator(received_db, received_kb, *, operations):
        captured["db"] = received_db
        captured["kb"] = received_kb
        captured["operations"] = operations
        return "kb-id", "ds-id"

    monkeypatch.setattr(provisioning, "provision_knowledge_base", fake_orchestrator)

    result = provisioning.provision_diaglob_knowledge_base(db, knowledge_base)

    assert result == ("kb-id", "ds-id")
    assert captured["db"] is db
    assert captured["kb"] is knowledge_base
    assert captured["operations"].create_vector_index is sentinel_operation


def test_ready_resource_shortcut_does_not_touch_dependencies():
    operations = _operations()
    knowledge_base = SimpleNamespace(
        external_status="ready",
        external_id="kb-id",
        external_data_source_id="ds-id",
    )

    result = provision_knowledge_base(object(), knowledge_base, operations=operations)

    assert result == ("kb-id", "ds-id")
    for operation in operations.__dict__.values():
        operation.assert_not_called()


def test_ready_resource_without_ids_preserves_historical_error_contract():
    operations = _operations()
    knowledge_base = SimpleNamespace(
        external_status="ready",
        external_id=None,
        external_data_source_id=None,
    )

    with pytest.raises(BedrockProvisioningError) as exc:
        provision_knowledge_base(object(), knowledge_base, operations=operations)

    assert exc.value.code == "ready_resource_ids_missing"
    assert exc.value.resource == "knowledge_base"
    for operation in operations.__dict__.values():
        operation.assert_not_called()
