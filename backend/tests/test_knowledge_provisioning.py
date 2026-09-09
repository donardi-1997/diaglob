"""Tests for Knowledge Base startup reconciliation.

Covers the critical fix for the CI regression where
reconcile_knowledge_base_provisioning() crashed on databases
missing the knowledge_bases table, cascading failures into
every test that instantiates TestClient(app).
"""
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base


@pytest.fixture()
def empty_db_engine():
    """Create a temporary empty SQLite database (no tables)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture()
def kb_table_engine():
    """Create a temporary SQLite database WITH the knowledge_bases table."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


class TestReconcileMissingTable:
    """1. Missing knowledge_bases table: no crash, skips reconciliation."""

    def test_no_crash_when_table_missing(self, empty_db_engine):
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        EmptySession = sessionmaker(bind=empty_db_engine)
        with patch("app.services.knowledge_provisioning.SessionLocal", EmptySession):
            reconcile_knowledge_base_provisioning()

    def test_no_provisioning_scheduled_when_table_missing(self, empty_db_engine):
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        EmptySession = sessionmaker(bind=empty_db_engine)
        with patch("app.services.knowledge_provisioning.SessionLocal", EmptySession), \
             patch("app.services.knowledge_provisioning.schedule_knowledge_base_provisioning") as mock_schedule:
            reconcile_knowledge_base_provisioning()
            mock_schedule.assert_not_called()


class TestReconcileEmptyTable:
    """2. Existing table with no pending Knowledge Bases."""

    def test_returns_normally_with_no_records(self, kb_table_engine):
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        Session = sessionmaker(bind=kb_table_engine)
        with patch("app.services.knowledge_provisioning.SessionLocal", Session), \
             patch("app.services.knowledge_provisioning.schedule_knowledge_base_provisioning") as mock_schedule:
            reconcile_knowledge_base_provisioning()
            mock_schedule.assert_not_called()


class TestReconcileWithPendingKBs:
    """3. Existing table with pending/provisioning/retrying Knowledge Bases."""

    def test_pending_kb_schedules_provisioning(self, kb_table_engine):
        from app.models import KnowledgeBase, Organization
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        Session = sessionmaker(bind=kb_table_engine)
        db = Session()

        org = Organization(name="Test Org", slug="test-org", plan="starter", subscription_status="active")
        db.add(org)
        db.flush()

        kb = KnowledgeBase(
            organization_id=org.id,
            name="Test KB",
            scope="selected_stores",
            active=True,
            external_status="pending",
        )
        db.add(kb)
        db.commit()
        kb_id = kb.id
        db.close()

        with patch("app.services.knowledge_provisioning.SessionLocal", Session), \
             patch("app.services.knowledge_provisioning.schedule_knowledge_base_provisioning") as mock_schedule:
            reconcile_knowledge_base_provisioning()
            mock_schedule.assert_called_once_with(kb_id)

    def test_provisioning_kb_moved_to_retrying(self, kb_table_engine):
        from app.models import KnowledgeBase, Organization
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        Session = sessionmaker(bind=kb_table_engine)
        db = Session()

        org = Organization(name="Test Org", slug="test-org", plan="starter", subscription_status="active")
        db.add(org)
        db.flush()

        kb = KnowledgeBase(
            organization_id=org.id,
            name="Test KB",
            scope="selected_stores",
            active=True,
            external_status="provisioning",
        )
        db.add(kb)
        db.commit()
        kb_id = kb.id
        db.close()

        with patch("app.services.knowledge_provisioning.SessionLocal", Session), \
             patch("app.services.knowledge_provisioning.schedule_knowledge_base_provisioning"):
            reconcile_knowledge_base_provisioning()

        db = Session()
        updated = db.get(KnowledgeBase, kb_id)
        assert updated.external_status == "retrying"
        assert updated.provisioning_stage == "retrying"
        assert updated.provisioning_stage_started_at is not None
        db.close()

    def test_retrying_kb_stays_retrying(self, kb_table_engine):
        from app.models import KnowledgeBase, Organization
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        Session = sessionmaker(bind=kb_table_engine)
        db = Session()

        org = Organization(name="Test Org", slug="test-org", plan="starter", subscription_status="active")
        db.add(org)
        db.flush()

        kb = KnowledgeBase(
            organization_id=org.id,
            name="Test KB",
            scope="selected_stores",
            active=True,
            external_status="retrying",
        )
        db.add(kb)
        db.commit()
        kb_id = kb.id
        db.close()

        with patch("app.services.knowledge_provisioning.SessionLocal", Session), \
             patch("app.services.knowledge_provisioning.schedule_knowledge_base_provisioning") as mock_schedule:
            reconcile_knowledge_base_provisioning()
            mock_schedule.assert_called_once_with(kb_id)

        db = Session()
        updated = db.get(KnowledgeBase, kb_id)
        assert updated.external_status == "retrying"
        db.close()


class TestReconcileUnexpectedError:
    """4. Unexpected error must propagate."""

    def test_db_error_propagates(self, kb_table_engine):
        from app.services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        failing_session = MagicMock()
        failing_session.get_bind.return_value = kb_table_engine
        failing_session.query.side_effect = Exception("UNEXPECTED_DB_FAILURE")

        with patch("app.services.knowledge_provisioning.SessionLocal", return_value=failing_session):
            with pytest.raises(Exception, match="UNEXPECTED_DB_FAILURE"):
                reconcile_knowledge_base_provisioning()


class TestFastAPIRegression:
    """5. FastAPI TestClient works when global DB has no knowledge_bases table."""

    def test_testclient_app_starts_with_empty_global_db(self, empty_db_engine):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services import knowledge_provisioning as kp_mod
        from sqlalchemy.orm import sessionmaker

        EmptySession = sessionmaker(bind=empty_db_engine)

        original_sl = kp_mod.SessionLocal
        try:
            kp_mod.SessionLocal = EmptySession

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200
        finally:
            kp_mod.SessionLocal = original_sl
