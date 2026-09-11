"""Contract tests for transactional Knowledge provisioning lifecycle state."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import bedrock_knowledge_base as facade
from app.knowledge_provisioning import lifecycle
from app.knowledge_provisioning.errors import BedrockProvisioningError


def test_facade_exports_canonical_lifecycle_helpers():
    assert facade._commit_state is lifecycle._commit_state
    assert facade._as_utc is lifecycle._as_utc
    assert facade._set_provisioning_stage is lifecycle._set_provisioning_stage
    assert facade._claim_provisioning is lifecycle._claim_provisioning


def test_as_utc_preserves_aware_timestamp_and_normalizes_naive():
    aware = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 11, 2, 0)

    assert lifecycle._as_utc(aware) is aware
    normalized = lifecycle._as_utc(naive)
    assert normalized.tzinfo == timezone.utc
    assert normalized.replace(tzinfo=None) == naive


def test_commit_state_commits_without_rollback():
    db = MagicMock()

    lifecycle._commit_state(db)

    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_commit_state_rolls_back_and_sanitizes_database_failure():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database provider detail")

    with pytest.raises(BedrockProvisioningError) as exc:
        lifecycle._commit_state(db, "custom_persist_failed")

    db.rollback.assert_called_once_with()
    assert exc.value.code == "custom_persist_failed"
    assert exc.value.resource == "database"
    assert "provider detail" not in str(exc.value)


def test_set_provisioning_stage_persists_checkpoint(monkeypatch):
    commit_state = MagicMock()
    monkeypatch.setattr(lifecycle, "_commit_state", commit_state)
    started_at = datetime(2026, 9, 11, 1, 0, tzinfo=timezone.utc)
    previous_stage_started_at = datetime(
        2026, 9, 11, 1, 30, tzinfo=timezone.utc
    )
    knowledge_base = SimpleNamespace(
        organization_id=10,
        id=20,
        provisioning_stage="creating_vector_index",
        provisioning_started_at=started_at,
        provisioning_stage_started_at=previous_stage_started_at,
    )
    db = MagicMock()

    lifecycle._set_provisioning_stage(
        db,
        knowledge_base,
        "creating_knowledge_base",
    )

    assert knowledge_base.provisioning_stage == "creating_knowledge_base"
    assert knowledge_base.provisioning_started_at == started_at
    assert knowledge_base.provisioning_stage_started_at.tzinfo == timezone.utc
    assert knowledge_base.provisioning_stage_started_at >= previous_stage_started_at
    commit_state.assert_called_once_with(db)


def test_set_provisioning_stage_initializes_total_start(monkeypatch):
    commit_state = MagicMock()
    monkeypatch.setattr(lifecycle, "_commit_state", commit_state)
    knowledge_base = SimpleNamespace(
        organization_id=10,
        id=20,
        provisioning_stage=None,
        provisioning_started_at=None,
        provisioning_stage_started_at=None,
    )
    db = MagicMock()

    lifecycle._set_provisioning_stage(db, knowledge_base, "creating_vector_index")

    assert knowledge_base.provisioning_started_at is not None
    assert knowledge_base.provisioning_started_at.tzinfo == timezone.utc
    assert (
        knowledge_base.provisioning_stage_started_at
        == knowledge_base.provisioning_started_at
    )
    commit_state.assert_called_once_with(db)
