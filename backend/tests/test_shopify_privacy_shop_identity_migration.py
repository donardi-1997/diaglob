"""Migration keeps historical Shopify identity after merchant disconnect."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


REVISION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
    / "a9b0c1d2e3f4_shopify_privacy_shop_identity.py"
)


def test_shop_identity_migration_upgrade_integrity_and_downgrade():
    spec = importlib.util.spec_from_file_location("privacy_identity_migration", REVISION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "d0e1f2a3b4c5"

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        ops = Operations(MigrationContext.configure(connection))
        with patch.object(module, "op", ops):
            module.upgrade()
    inspector = inspect(engine)
    assert "shopify_privacy_shop_identities" in inspector.get_table_names()
    names = {c["name"] for c in inspector.get_columns(
        "shopify_privacy_shop_identities"
    )}
    assert names == {
        "id", "shop_id", "shop_domain", "organization_id", "store_id",
        "provenance", "first_seen_at", "last_seen_at", "uninstalled_at",
    }
    assert not inspector.get_foreign_keys("shopify_privacy_shop_identities")
    uniques = {item["name"] for item in inspector.get_unique_constraints(
        "shopify_privacy_shop_identities"
    )}
    assert "uq_shopify_privacy_shop_identity" in uniques

    insert = text(
        "INSERT INTO shopify_privacy_shop_identities "
        "(shop_id,shop_domain,organization_id,store_id,provenance,"
        "first_seen_at,last_seen_at,uninstalled_at) "
        "VALUES ('321','history.myshopify.com',31,71,'hmac_uninstall',"
        "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
    )
    with engine.begin() as connection:
        connection.execute(insert)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert)

    with engine.begin() as connection:
        ops = Operations(MigrationContext.configure(connection))
        with patch.object(module, "op", ops):
            module.downgrade()
    assert "shopify_privacy_shop_identities" not in inspect(engine).get_table_names()
    engine.dispose()
