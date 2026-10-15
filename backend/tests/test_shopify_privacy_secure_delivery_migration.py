"""Encrypted delivery migration: no tokens/customer plaintext or foreign keys."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


MIGRATION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
    / "b9c0d1e2f3a4_shopify_privacy_encrypted_delivery.py"
)


def test_encrypted_delivery_migration_and_unique_digest():
    spec = importlib.util.spec_from_file_location("secure_delivery_revision", MIGRATION)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "a9b0c1d2e3f4"
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ops = Operations(MigrationContext.configure(conn))
        with patch.object(revision, "op", ops):
            revision.upgrade()
    inspector = inspect(engine)
    cols = {
        c["name"] for c in inspector.get_columns("shopify_privacy_delivery_artifacts")
    }
    assert "ciphertext_encrypted" in cols
    assert "token_digest" in cols
    assert "recipient_user_id" in cols
    assert "plaintext" not in cols
    assert not inspector.get_foreign_keys("shopify_privacy_delivery_artifacts")
    assert "shopify_privacy_delivery_audit" in inspector.get_table_names()

    sql = text(
        "INSERT INTO shopify_privacy_delivery_artifacts "
        "(request_id,organization_id,store_id,recipient_user_id,token_digest,"
        "artifact_sha256,ciphertext_encrypted,created_at,expires_at,synthetic_only) "
        "VALUES ('opaque-receipt',1,2,3,'opaque-token-digest','artifact-hash',"
        "'encrypted-placeholder',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
    )
    with engine.begin() as conn:
        conn.execute(sql)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(sql)

    with engine.begin() as conn:
        ops = Operations(MigrationContext.configure(conn))
        with patch.object(revision, "op", ops):
            revision.downgrade()
    assert "shopify_privacy_delivery_artifacts" not in inspect(engine).get_table_names()
    engine.dispose()
