"""add supplier fulfillment orders

Revision ID: p2d3e4f5a6b7
Revises: o1c2d3e4f5a6
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa


revision = "p2d3e4f5a6b7"
down_revision = "o1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("supplier_connection_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_order_number", sa.String(length=50), nullable=False),
        sa.Column("external_order_id", sa.String(length=255), nullable=True),
        sa.Column("shipment_order_id", sa.String(length=255), nullable=True),
        sa.Column("supplier_status", sa.String(length=50), nullable=True),
        sa.Column("supplier_substatus", sa.String(length=50), nullable=True),
        sa.Column("creation_status", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("product_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("postage_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("order_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("actual_payment", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supplier_connection_id"],
            ["supplier_connections.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "store_id",
            "provider",
            "idempotency_key",
            name="uq_supplier_order_store_provider_idempotency",
        ),
        sa.UniqueConstraint(
            "supplier_connection_id",
            "external_order_id",
            name="uq_supplier_order_connection_external",
        ),
    )
    for column in (
        "organization_id",
        "store_id",
        "order_id",
        "supplier_connection_id",
        "provider",
        "provider_order_number",
        "external_order_id",
        "shipment_order_id",
        "supplier_status",
        "supplier_substatus",
        "creation_status",
    ):
        op.create_index(
            f"ix_supplier_orders_{column}",
            "supplier_orders",
            [column],
            unique=False,
        )

    op.create_table(
        "supplier_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_order_id", sa.Integer(), nullable=False),
        sa.Column("order_item_id", sa.Integer(), nullable=True),
        sa.Column("external_variant_id", sa.String(length=255), nullable=False),
        sa.Column("provider_line_item_id", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"],
            ["supplier_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "supplier_order_id",
            "order_item_id",
            name="uq_supplier_order_item_order_item",
        ),
    )
    op.create_index(
        "ix_supplier_order_items_supplier_order_id",
        "supplier_order_items",
        ["supplier_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_order_items_order_item_id",
        "supplier_order_items",
        ["order_item_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_supplier_order_items_order_item_id",
        table_name="supplier_order_items",
    )
    op.drop_index(
        "ix_supplier_order_items_supplier_order_id",
        table_name="supplier_order_items",
    )
    op.drop_table("supplier_order_items")

    for column in reversed(
        (
            "organization_id",
            "store_id",
            "order_id",
            "supplier_connection_id",
            "provider",
            "provider_order_number",
            "external_order_id",
            "shipment_order_id",
            "supplier_status",
            "supplier_substatus",
            "creation_status",
        )
    ):
        op.drop_index(
            f"ix_supplier_orders_{column}",
            table_name="supplier_orders",
        )
    op.drop_table("supplier_orders")
