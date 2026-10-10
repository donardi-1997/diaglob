"""Exercise Shopify privacy inbox Alembic revision in an isolated SQLite DB."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


REVISION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "a4e5f6a7b8c9_shopify_privacy_request_inbox.py"
)


def _revision():
    spec = importlib.util.spec_from_file_location("shopify_privacy_migration", REVISION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_privacy_inbox_upgrade_and_downgrade():
    module = _revision()
    assert module.down_revision == "z2b3c4d5e6f7"
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(module, "op", operations):
            module.upgrade()

    inspector = inspect(engine)
    assert "shopify_privacy_requests" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("shopify_privacy_requests")}
    assert {"request_id", "shop_domain", "organization_id", "store_id", "selector_encrypted", "status"} <= columns
    indexes = {index["name"] for index in inspector.get_indexes("shopify_privacy_requests")}
    assert "ix_shopify_privacy_requests_status" in indexes
    uniques = {
        entry["name"] for entry in inspector.get_unique_constraints("shopify_privacy_requests")
    }
    assert "uq_shopify_privacy_request_id" in uniques

    # The receipt needs to remain valid after an uninstall, with no organization.
    insert = text(
        "INSERT INTO shopify_privacy_requests "
        "(request_id, topic, shop_id, shop_domain, selector_encrypted, created_at, updated_at) "
        "VALUES ('receipt-one', 'shop/redact', '123', 'test.myshopify.com', "
        "'encrypted-placeholder', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    with engine.begin() as connection:
        connection.execute(insert)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert)

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(module, "op", operations):
            module.downgrade()
    assert "shopify_privacy_requests" not in inspect(engine).get_table_names()
