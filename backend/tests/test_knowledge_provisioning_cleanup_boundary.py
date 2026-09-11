"""Boundary tests for modern Knowledge Base remote-resource cleanup."""

from app import bedrock_knowledge_base as provisioning
from app.knowledge_provisioning.cleanup import CleanupResult


INDEX_ARN = "arn:aws:s3vectors:us-east-2:123456789012:bucket/test/index/test"
BEDROCK_KB_ID = "ABCDEFGHIJ"
BEDROCK_DS_ID = "KLMNOPQRST"


def test_facade_reexports_cleanup_result_type():
    assert provisioning.CleanupResult is CleanupResult


def test_facade_cleanup_uses_current_delete_callables_in_dependency_order(monkeypatch):
    calls = []

    def delete_ds(kb_external_id, ds_external_id, org_id, kb_id, index_arn):
        calls.append(("data_source", kb_external_id, ds_external_id, org_id, kb_id, index_arn))

    def delete_kb(kb_external_id, org_id, kb_id, index_arn):
        calls.append(("knowledge_base", kb_external_id, org_id, kb_id, index_arn))

    def delete_index(index_arn, org_id, kb_id):
        calls.append(("vector_index", index_arn, org_id, kb_id))

    monkeypatch.setattr(provisioning, "delete_bedrock_data_source", delete_ds)
    monkeypatch.setattr(provisioning, "delete_bedrock_knowledge_base", delete_kb)
    monkeypatch.setattr(provisioning, "delete_s3_vectors_index", delete_index)

    result = provisioning._cleanup_remote_resources(
        7,
        11,
        INDEX_ARN,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
    )

    assert result == CleanupResult(True, None, None)
    assert calls == [
        ("data_source", BEDROCK_KB_ID, BEDROCK_DS_ID, 7, 11, INDEX_ARN),
        ("knowledge_base", BEDROCK_KB_ID, 7, 11, INDEX_ARN),
        ("vector_index", INDEX_ARN, 7, 11),
    ]


def test_data_source_failure_preserves_all_remote_ids_and_stops(monkeypatch):
    failure = RuntimeError("data source delete uncertain")
    calls = []

    def delete_ds(*args):
        calls.append("data_source")
        raise failure

    def unexpected(*args):
        calls.append("unexpected")

    monkeypatch.setattr(provisioning, "delete_bedrock_data_source", delete_ds)
    monkeypatch.setattr(provisioning, "delete_bedrock_knowledge_base", unexpected)
    monkeypatch.setattr(provisioning, "delete_s3_vectors_index", unexpected)

    result = provisioning._cleanup_remote_resources(
        7,
        11,
        INDEX_ARN,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
    )

    assert result.succeeded is False
    assert result.bedrock_kb_id == BEDROCK_KB_ID
    assert result.bedrock_ds_id == BEDROCK_DS_ID
    assert result.error is failure
    assert calls == ["data_source"]


def test_knowledge_base_failure_clears_only_confirmed_data_source_id(monkeypatch):
    failure = RuntimeError("knowledge base delete uncertain")
    calls = []

    def delete_ds(*args):
        calls.append("data_source")

    def delete_kb(*args):
        calls.append("knowledge_base")
        raise failure

    def unexpected(*args):
        calls.append("unexpected")

    monkeypatch.setattr(provisioning, "delete_bedrock_data_source", delete_ds)
    monkeypatch.setattr(provisioning, "delete_bedrock_knowledge_base", delete_kb)
    monkeypatch.setattr(provisioning, "delete_s3_vectors_index", unexpected)

    result = provisioning._cleanup_remote_resources(
        7,
        11,
        INDEX_ARN,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
    )

    assert result.succeeded is False
    assert result.bedrock_kb_id == BEDROCK_KB_ID
    assert result.bedrock_ds_id is None
    assert result.error is failure
    assert calls == ["data_source", "knowledge_base"]


def test_vector_index_failure_preserves_confirmed_bedrock_deletions(monkeypatch):
    failure = RuntimeError("vector index delete uncertain")
    calls = []

    monkeypatch.setattr(
        provisioning,
        "delete_bedrock_data_source",
        lambda *args: calls.append("data_source"),
    )
    monkeypatch.setattr(
        provisioning,
        "delete_bedrock_knowledge_base",
        lambda *args: calls.append("knowledge_base"),
    )

    def delete_index(*args):
        calls.append("vector_index")
        raise failure

    monkeypatch.setattr(provisioning, "delete_s3_vectors_index", delete_index)

    result = provisioning._cleanup_remote_resources(
        7,
        11,
        INDEX_ARN,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
    )

    assert result.succeeded is False
    assert result.bedrock_kb_id is None
    assert result.bedrock_ds_id is None
    assert result.error is failure
    assert calls == ["data_source", "knowledge_base", "vector_index"]


def test_missing_index_arn_keeps_knowledge_base_id_but_can_clear_data_source(monkeypatch):
    calls = []

    monkeypatch.setattr(
        provisioning,
        "delete_bedrock_data_source",
        lambda *args: calls.append(("data_source", args[-1])),
    )
    monkeypatch.setattr(
        provisioning,
        "delete_bedrock_knowledge_base",
        lambda *args: calls.append(("knowledge_base",)),
    )
    monkeypatch.setattr(
        provisioning,
        "delete_s3_vectors_index",
        lambda *args: calls.append(("vector_index",)),
    )

    result = provisioning._cleanup_remote_resources(
        7,
        11,
        None,
        BEDROCK_KB_ID,
        BEDROCK_DS_ID,
    )

    assert result == CleanupResult(True, BEDROCK_KB_ID, None)
    assert calls == [("data_source", None)]
