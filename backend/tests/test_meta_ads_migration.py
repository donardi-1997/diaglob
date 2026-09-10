import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "f2a3b4c5d6e7_add_meta_ads_connections.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "meta_ads_schema_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInspector:
    def __init__(
        self,
        *,
        columns,
        indexes=None,
        unique_constraints=None,
        primary_key=None,
        foreign_keys=None,
    ):
        self._columns = columns
        self._indexes = indexes if indexes is not None else _valid_indexes()
        self._unique_constraints = (
            unique_constraints
            if unique_constraints is not None
            else _valid_unique_constraints()
        )
        self._primary_key = primary_key or {"constrained_columns": ["id"]}
        self._foreign_keys = (
            foreign_keys if foreign_keys is not None else _valid_foreign_keys()
        )

    def get_columns(self, table):
        assert table == "meta_ads_connections"
        return self._columns

    def get_indexes(self, table):
        assert table == "meta_ads_connections"
        return self._indexes

    def get_unique_constraints(self, table):
        assert table == "meta_ads_connections"
        return self._unique_constraints

    def get_pk_constraint(self, table):
        assert table == "meta_ads_connections"
        return self._primary_key

    def get_foreign_keys(self, table):
        assert table == "meta_ads_connections"
        return self._foreign_keys


def _valid_columns():
    return [
        {"name": "id", "type": sa.Integer(), "nullable": False},
        {"name": "organization_id", "type": sa.Integer(), "nullable": False},
        {"name": "store_id", "type": sa.Integer(), "nullable": False},
        {"name": "provider", "type": sa.String(30), "nullable": False},
        {"name": "external_account_id", "type": sa.String(255), "nullable": False},
        {"name": "external_account_name", "type": sa.String(500), "nullable": True},
        {"name": "account_currency", "type": sa.String(10), "nullable": True},
        {"name": "account_timezone", "type": sa.String(100), "nullable": True},
        {"name": "access_token_encrypted", "type": sa.Text(), "nullable": False},
        {"name": "status", "type": sa.String(30), "nullable": False},
        {"name": "last_sync_at", "type": sa.DateTime(), "nullable": True},
        {"name": "last_sync_status", "type": sa.String(30), "nullable": True},
        {"name": "last_error_category", "type": sa.String(50), "nullable": True},
        {"name": "connected_at", "type": sa.DateTime(), "nullable": True},
        {"name": "created_at", "type": sa.DateTime(), "nullable": False},
        {"name": "updated_at", "type": sa.DateTime(), "nullable": False},
    ]


def _valid_indexes():
    return [
        {
            "name": "ix_meta_ads_connections_organization_id",
            "column_names": ["organization_id"],
            "unique": False,
        },
        {
            "name": "ix_meta_ads_connections_status",
            "column_names": ["status"],
            "unique": False,
        },
        {
            "name": "ix_meta_ads_connections_store_id",
            "column_names": ["store_id"],
            "unique": True,
        },
    ]


def _valid_unique_constraints():
    return [
        {
            "name": "uq_meta_ads_connection_store",
            "column_names": ["store_id"],
        }
    ]


def _valid_foreign_keys():
    return [
        {
            "constrained_columns": ["organization_id"],
            "referred_table": "organizations",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        },
        {
            "constrained_columns": ["store_id"],
            "referred_table": "stores",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        },
    ]


def test_existing_exact_table_requires_no_repairs():
    migration = _load_migration()
    inspector = FakeInspector(columns=_valid_columns())

    assert migration._existing_table_repair_plan(inspector) == ([], [], False)


def test_existing_table_repairs_optional_columns_indexes_and_constraint():
    migration = _load_migration()
    columns = [
        column
        for column in _valid_columns()
        if column["name"] not in {"account_timezone", "connected_at"}
    ]
    indexes = [
        index
        for index in _valid_indexes()
        if index["name"] != "ix_meta_ads_connections_status"
    ]
    inspector = FakeInspector(
        columns=columns,
        indexes=indexes,
        unique_constraints=[],
    )

    missing_columns, missing_indexes, needs_unique = (
        migration._existing_table_repair_plan(inspector)
    )

    assert missing_columns == ["account_timezone", "connected_at"]
    assert missing_indexes == ["ix_meta_ads_connections_status"]
    assert needs_unique is True


def test_existing_table_rejects_missing_required_column():
    migration = _load_migration()
    columns = [
        column for column in _valid_columns() if column["name"] != "status"
    ]
    inspector = FakeInspector(columns=columns)

    with pytest.raises(RuntimeError, match="missing required columns: status"):
        migration._existing_table_repair_plan(inspector)


def test_existing_table_rejects_incompatible_column_type():
    migration = _load_migration()
    columns = _valid_columns()
    for column in columns:
        if column["name"] == "provider":
            column["type"] = sa.String(255)
    inspector = FakeInspector(columns=columns)

    with pytest.raises(RuntimeError, match="provider has incompatible type"):
        migration._existing_table_repair_plan(inspector)


def test_existing_table_rejects_incompatible_nullability():
    migration = _load_migration()
    columns = _valid_columns()
    for column in columns:
        if column["name"] == "status":
            column["nullable"] = True
    inspector = FakeInspector(columns=columns)

    with pytest.raises(RuntimeError, match="status has incompatible nullability"):
        migration._existing_table_repair_plan(inspector)


def test_existing_table_rejects_missing_foreign_key():
    migration = _load_migration()
    foreign_keys = [
        fk
        for fk in _valid_foreign_keys()
        if fk["constrained_columns"] != ["store_id"]
    ]
    inspector = FakeInspector(
        columns=_valid_columns(),
        foreign_keys=foreign_keys,
    )

    with pytest.raises(RuntimeError, match="missing the foreign key for store_id"):
        migration._existing_table_repair_plan(inspector)


def test_existing_table_rejects_incompatible_index():
    migration = _load_migration()
    indexes = _valid_indexes()
    for index in indexes:
        if index["name"] == "ix_meta_ads_connections_store_id":
            index["unique"] = False
    inspector = FakeInspector(columns=_valid_columns(), indexes=indexes)

    with pytest.raises(RuntimeError, match="incompatible index definition"):
        migration._existing_table_repair_plan(inspector)
