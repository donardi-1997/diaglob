"""add dropshipping analytics fields

Revision ID: 9fb2e4283c46
Revises: ac7ed5866ece
Create Date: 2026-09-09 13:39:15.532317
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fb2e4283c46'
down_revision: Union[str, None] = 'ac7ed5866ece'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table)]
    return column in columns


def _index_exists(index: str, table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    indexes = [i["name"] for i in insp.get_indexes(table)]
    return index in indexes


def upgrade() -> None:
    # Add lifecycle_status and lifecycle_synced_at to orders
    if not _column_exists('orders', 'lifecycle_status'):
        op.add_column('orders', sa.Column('lifecycle_status', sa.String(30), nullable=True))
    if not _column_exists('orders', 'lifecycle_synced_at'):
        op.add_column('orders', sa.Column('lifecycle_synced_at', sa.DateTime(), nullable=True))
    if not _index_exists('ix_orders_lifecycle_status', 'orders'):
        op.create_index('ix_orders_lifecycle_status', 'orders', ['lifecycle_status'])

    # Add unit_cost to order_items
    if not _column_exists('order_items', 'unit_cost'):
        op.add_column('order_items', sa.Column('unit_cost', sa.Numeric(18, 4), nullable=True))

    # Add cost to products
    if not _column_exists('products', 'cost'):
        op.add_column('products', sa.Column('cost', sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    if _column_exists('products', 'cost'):
        op.drop_column('products', 'cost')
    if _column_exists('order_items', 'unit_cost'):
        op.drop_column('order_items', 'unit_cost')
    if _index_exists('ix_orders_lifecycle_status', 'orders'):
        op.drop_index('ix_orders_lifecycle_status', table_name='orders')
    if _column_exists('orders', 'lifecycle_synced_at'):
        op.drop_column('orders', 'lifecycle_synced_at')
    if _column_exists('orders', 'lifecycle_status'):
        op.drop_column('orders', 'lifecycle_status')
