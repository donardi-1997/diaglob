"""repair Nuvemshop order schema drift

Revision ID: c4a5b6d7e8f9
Revises: b3c2d9e0f112
Create Date: 2026-09-09 10:00:00.000000

Production repair migration for stamped-but-missing Nuvemshop order columns.

Root cause: production was stamped at b3c2d9e0f112 but the earlier migration
f6f002b05545 (which adds external_order_id, payment_method, payment_status
to the orders table) was never actually applied against the production database.

This migration inspects the live orders table and adds ONLY the missing columns
and indexes. It is idempotent and safe for:
  - Production-like stamped-but-missing databases
  - Already-correct databases (no-op)
  - Fresh databases upgraded through full migration history

Do NOT modify historical migrations. Do NOT drop columns or tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4a5b6d7e8f9"
down_revision: Union[str, None] = "b3c2d9e0f112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS_TO_REPAIR = [
    ("external_order_id", sa.String(length=255), True),
    ("payment_method", sa.String(length=50), True),
    ("payment_status", sa.String(length=50), True),
]

_INDEXES_TO_REPAIR = [
    ("ix_orders_external_order_id", "orders", ["external_order_id"]),
    ("ix_orders_payment_method", "orders", ["payment_method"]),
    ("ix_orders_payment_status", "orders", ["payment_status"]),
]


def _existing_columns(table: str) -> set:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    existing_cols = _existing_columns("orders")
    for col_name, col_type, nullable in _COLUMNS_TO_REPAIR:
        if col_name not in existing_cols:
            op.add_column(
                "orders",
                sa.Column(col_name, col_type, nullable=nullable),
            )

    existing_idx = _existing_indexes("orders")
    for idx_name, table, columns in _INDEXES_TO_REPAIR:
        if idx_name not in existing_idx:
            op.create_index(idx_name, table, columns, unique=False)


def downgrade() -> None:
    existing_idx = _existing_indexes("orders")
    for idx_name, table, columns in reversed(_INDEXES_TO_REPAIR):
        if idx_name in existing_idx:
            op.drop_index(idx_name, table_name=table)

    existing_cols = _existing_columns("orders")
    for col_name, _, _ in reversed(_COLUMNS_TO_REPAIR):
        if col_name in existing_cols:
            op.drop_column("orders", col_name)
