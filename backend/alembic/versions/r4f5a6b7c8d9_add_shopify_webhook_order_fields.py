"""add Shopify webhook order ingestion fields

Revision ID: r4f5a6b7c8d9
Revises: q3e4f5a6b7c8
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "r4f5a6b7c8d9"
down_revision = "q3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("shipping_address", sa.JSON(), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("shopify_line_item_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_order_items_shopify_line_item_id",
        "order_items",
        ["shopify_line_item_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_order_item_order_shopify_line_item",
        "order_items",
        ["order_id", "shopify_line_item_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_order_item_order_shopify_line_item",
        "order_items",
        type_="unique",
    )
    op.drop_index(
        "ix_order_items_shopify_line_item_id",
        table_name="order_items",
    )
    op.drop_column("order_items", "shopify_line_item_id")
    op.drop_column("orders", "shipping_address")
