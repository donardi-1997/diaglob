"""add meta ads connections

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "meta_ads_connections"
_REQUIRED_COLUMNS = {
    "id",
    "organization_id",
    "store_id",
    "provider",
    "external_account_id",
    "access_token_encrypted",
    "status",
    "created_at",
    "updated_at",
}
_REPAIRABLE_COLUMNS = {
    "external_account_name",
    "account_currency",
    "account_timezone",
    "last_sync_at",
    "last_sync_status",
    "last_error_category",
    "connected_at",
}
_COLUMN_CONTRACTS = {
    "id": ("integer", None, False),
    "organization_id": ("integer", None, False),
    "store_id": ("integer", None, False),
    "provider": ("string", 30, False),
    "external_account_id": ("string", 255, False),
    "external_account_name": ("string", 500, True),
    "account_currency": ("string", 10, True),
    "account_timezone": ("string", 100, True),
    "access_token_encrypted": ("text", None, False),
    "status": ("string", 30, False),
    "last_sync_at": ("datetime", None, True),
    "last_sync_status": ("string", 30, True),
    "last_error_category": ("string", 50, True),
    "connected_at": ("datetime", None, True),
    "created_at": ("datetime", None, False),
    "updated_at": ("datetime", None, False),
}
_INDEX_CONTRACTS = {
    "ix_meta_ads_connections_organization_id": (["organization_id"], False),
    "ix_meta_ads_connections_status": (["status"], False),
    "ix_meta_ads_connections_store_id": (["store_id"], True),
}
_UNIQUE_CONSTRAINT = "uq_meta_ads_connection_store"


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table)


def _column_type_matches(
    actual_type: sa.types.TypeEngine,
    kind: str,
    length: int | None,
) -> bool:
    if kind == "integer":
        return isinstance(actual_type, sa.Integer)
    if kind == "text":
        return isinstance(actual_type, sa.Text)
    if kind == "datetime":
        return isinstance(actual_type, sa.DateTime)
    if kind == "string":
        return (
            isinstance(actual_type, sa.String)
            and not isinstance(actual_type, sa.Text)
            and actual_type.length == length
        )
    raise AssertionError(f"Unknown column contract type: {kind}")


def _repairable_column(name: str) -> sa.Column:
    columns = {
        "external_account_name": sa.Column(
            "external_account_name",
            sa.String(length=500),
            nullable=True,
        ),
        "account_currency": sa.Column(
            "account_currency",
            sa.String(length=10),
            nullable=True,
        ),
        "account_timezone": sa.Column(
            "account_timezone",
            sa.String(length=100),
            nullable=True,
        ),
        "last_sync_at": sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        "last_sync_status": sa.Column(
            "last_sync_status",
            sa.String(length=30),
            nullable=True,
        ),
        "last_error_category": sa.Column(
            "last_error_category",
            sa.String(length=50),
            nullable=True,
        ),
        "connected_at": sa.Column("connected_at", sa.DateTime(), nullable=True),
    }
    return columns[name]


def _existing_table_repair_plan(inspector) -> tuple[list[str], list[str], bool]:
    columns = {
        column["name"]: column
        for column in inspector.get_columns(_TABLE)
    }

    missing_required = sorted(_REQUIRED_COLUMNS - columns.keys())
    if missing_required:
        raise RuntimeError(
            f"{_TABLE} exists but is missing required columns: "
            f"{', '.join(missing_required)}. Manual schema repair is required "
            "before this migration can be stamped."
        )

    missing_repairable = sorted(_REPAIRABLE_COLUMNS - columns.keys())

    for name, column in columns.items():
        contract = _COLUMN_CONTRACTS.get(name)
        if contract is None:
            continue
        kind, length, expected_nullable = contract
        if not _column_type_matches(column["type"], kind, length):
            raise RuntimeError(
                f"{_TABLE}.{name} has incompatible type {column['type']!s}; "
                f"expected {kind}"
                + (f"({length})" if length is not None else "")
                + "."
            )
        if bool(column["nullable"]) != expected_nullable:
            raise RuntimeError(
                f"{_TABLE}.{name} has incompatible nullability; "
                f"expected nullable={expected_nullable}."
            )

    primary_key = inspector.get_pk_constraint(_TABLE)
    if primary_key.get("constrained_columns") != ["id"]:
        raise RuntimeError(
            f"{_TABLE} has an incompatible primary key; expected ['id']."
        )

    foreign_keys = {
        tuple(fk.get("constrained_columns") or []): fk
        for fk in inspector.get_foreign_keys(_TABLE)
    }
    expected_foreign_keys = {
        ("organization_id",): ("organizations", ["id"]),
        ("store_id",): ("stores", ["id"]),
    }
    for constrained, (table, referred_columns) in expected_foreign_keys.items():
        foreign_key = foreign_keys.get(constrained)
        if foreign_key is None:
            raise RuntimeError(
                f"{_TABLE} is missing the foreign key for {constrained[0]}."
            )
        ondelete = (foreign_key.get("options") or {}).get("ondelete")
        if (
            foreign_key.get("referred_table") != table
            or foreign_key.get("referred_columns") != referred_columns
            or str(ondelete or "").upper() != "CASCADE"
        ):
            raise RuntimeError(
                f"{_TABLE} has an incompatible foreign key for {constrained[0]}."
            )

    constraints = {
        constraint.get("name"): constraint
        for constraint in inspector.get_unique_constraints(_TABLE)
        if constraint.get("name")
    }
    unique_constraint = constraints.get(_UNIQUE_CONSTRAINT)
    needs_unique_constraint = unique_constraint is None
    if (
        unique_constraint is not None
        and unique_constraint.get("column_names") != ["store_id"]
    ):
        raise RuntimeError(
            f"{_TABLE}.{_UNIQUE_CONSTRAINT} has incompatible columns."
        )

    indexes = {
        index.get("name"): index
        for index in inspector.get_indexes(_TABLE)
        if index.get("name")
    }
    missing_indexes: list[str] = []
    for name, (columns_expected, unique_expected) in _INDEX_CONTRACTS.items():
        index = indexes.get(name)
        if index is None:
            missing_indexes.append(name)
            continue
        if (
            index.get("column_names") != columns_expected
            or bool(index.get("unique")) != unique_expected
        ):
            raise RuntimeError(
                f"{_TABLE}.{name} has an incompatible index definition."
            )

    return missing_repairable, missing_indexes, needs_unique_constraint


def _create_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("external_account_name", sa.String(length=500), nullable=True),
        sa.Column("account_currency", sa.String(length=10), nullable=True),
        sa.Column("account_timezone", sa.String(length=100), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sa.String(length=30), nullable=True),
        sa.Column("last_error_category", sa.String(length=50), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name=_UNIQUE_CONSTRAINT),
    )


def _create_index(name: str) -> None:
    columns, unique = _INDEX_CONTRACTS[name]
    op.create_index(name, _TABLE, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_TABLE):
        _create_table()
        for name in _INDEX_CONTRACTS:
            _create_index(name)
        return

    missing_columns, missing_indexes, needs_unique_constraint = (
        _existing_table_repair_plan(inspector)
    )

    for name in missing_columns:
        op.add_column(_TABLE, _repairable_column(name))

    if needs_unique_constraint:
        op.create_unique_constraint(_UNIQUE_CONSTRAINT, _TABLE, ["store_id"])

    for name in missing_indexes:
        _create_index(name)


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return

    op.drop_index(
        "ix_meta_ads_connections_store_id",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_meta_ads_connections_status",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_meta_ads_connections_organization_id",
        table_name=_TABLE,
    )
    op.drop_table(_TABLE)
