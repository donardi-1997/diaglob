"""add Nuvemshop order fields

Revision ID: f6f002b05545
Revises: e63418b90903
Create Date: 2026-09-08 17:32:55.667916

Adds the three Nuvemshop-specific columns to the orders table:
  - external_order_id  (provider-native order ID)
  - payment_method     (e.g. pix, credit_card, boleto)
  - payment_status     (e.g. pending, paid, overdue)

Uses schema-aware idempotent guards so this migration is safe for:
  - Fresh databases (columns do not exist yet)
  - Already-repaired databases (columns already present)
  - Stamped-but-missing databases (columns absent, revision already recorded)

Do NOT include unrelated autogenerate drift in this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6f002b05545'
down_revision: Union[str, None] = 'e63418b90903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns this migration owns — nothing else.
_NUVEMSHOP_COLUMNS = [
    ("external_order_id", sa.String(length=255), True),
    ("payment_method", sa.String(length=50), True),
    ("payment_status", sa.String(length=50), True),
]

_NUVEMSHOP_INDEXES = [
    ("ix_orders_external_order_id", "orders", ["external_order_id"]),
    ("ix_orders_payment_method", "orders", ["payment_method"]),
    ("ix_orders_payment_status", "orders", ["payment_status"]),
]


def _existing_columns(table: str) -> set:
    """Return the set of column names for *table* via Alembic inspector."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set:
    """Return the set of index names for *table* via Alembic inspector."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    existing = _existing_columns("orders")

    for col_name, col_type, nullable in _NUVEMSHOP_COLUMNS:
        if col_name not in existing:
            op.add_column(
                "orders",
                sa.Column(col_name, col_type, nullable=nullable),
            )

    existing_idx = _existing_indexes("orders")
    for idx_name, table, columns in _NUVEMSHOP_INDEXES:
        if idx_name not in existing_idx:
            op.create_index(idx_name, table, columns, unique=False)


def downgrade() -> None:
    existing_idx = _existing_indexes("orders")
    for idx_name, table, columns in reversed(_NUVEMSHOP_INDEXES):
        if idx_name in existing_idx:
            op.drop_index(idx_name, table_name=table)

    existing = _existing_columns("orders")
    for col_name, _, _ in reversed(_NUVEMSHOP_COLUMNS):
        if col_name in existing:
            op.drop_column("orders", col_name)
