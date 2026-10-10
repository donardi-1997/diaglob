"""Alembic privacy audit event revision: independent, PII-free evidence."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text


MIGRATION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
    / "c5d6e7f8a9b0_shopify_privacy_audit_events.py"
)


def test_privacy_audit_migration_roundtrip():
    spec = importlib.util.spec_from_file_location("shopify_audit_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "a4e5f6a7b8c9"

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(revision, "op", operations):
            revision.upgrade()
        connection.execute(
            text(
                "INSERT INTO shopify_privacy_audit_events "
                "(request_id,event_type,from_status,to_status,reason_code,"
                "actor_type,created_at) "
                "VALUES ('fake-digest','received',NULL,'pending_policy_review',"
                "'tenant_unresolved','shopify_hmac_verified',CURRENT_TIMESTAMP)"
            )
        )

    columns = {c["name"] for c in inspect(engine).get_columns(
        "shopify_privacy_audit_events"
    )}
    assert columns == {
        "id", "request_id", "event_type", "from_status", "to_status",
        "reason_code", "actor_type", "created_at",
    }
    indexes = {
        item["name"] for item in inspect(engine).get_indexes(
            "shopify_privacy_audit_events"
        )
    }
    assert "ix_shopify_privacy_audit_events_request_id" in indexes

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(revision, "op", operations):
            revision.downgrade()
    assert "shopify_privacy_audit_events" not in inspect(engine).get_table_names()
    engine.dispose()
