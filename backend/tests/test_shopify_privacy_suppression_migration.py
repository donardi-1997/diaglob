"""SQL migrations keep Shopify privacy tombstones unique and PII-free."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text


MIGRATION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
    / "c0d1e2f3a4b5_shopify_privacy_suppressions.py"
)


def test_shopify_suppression_migration_upgrade_and_downgrade():
    spec = importlib.util.spec_from_file_location("privacy_suppression_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "b0c1d2e3f4a5"
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(revision, "op", operations):
            revision.upgrade()
        connection.execute(text(
            "INSERT INTO shopify_privacy_suppressions "
            "(organization_id,store_id,request_id,kind,selector_digest,"
            "key_fingerprint,status,created_at) "
            "VALUES (1,2,'opaque-digest','customer','opaque-selector',"
            "'test-only-key-tag','staged',CURRENT_TIMESTAMP)"
        ))
    columns = {
        col["name"] for col in inspect(engine).get_columns(
            "shopify_privacy_suppressions"
        )
    }
    assert columns == {
        "id", "organization_id", "store_id", "request_id", "kind",
        "selector_digest", "key_fingerprint", "status", "created_at",
        "activated_at",
    }
    assert not inspect(engine).get_foreign_keys("shopify_privacy_suppressions")
    indexes = {
        item["name"] for item in inspect(engine).get_indexes(
            "shopify_privacy_suppressions"
        )
    }
    assert "ix_shopify_privacy_suppressions_request_id" in indexes
    assert "ix_shopify_privacy_suppressions_store_id" in indexes
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(revision, "op", operations):
            revision.downgrade()
    assert "shopify_privacy_suppressions" not in inspect(engine).get_table_names()
    engine.dispose()
