"""add automatic fulfillment orchestration

Revision ID: t6b7c8d9e0f1
Revises: s5a6b7c8d9e0
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "t6b7c8d9e0f1"
down_revision = "s5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "supplier_connections",
        sa.Column(
            "auto_fulfillment_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "supplier_connections",
        sa.Column(
            "auto_origin_country_code",
            sa.String(length=2),
            nullable=False,
            server_default="CN",
        ),
    )
    op.add_column(
        "supplier_connections",
        sa.Column(
            "auto_notify_customer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.create_table(
        "auto_fulfillment_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("supplier_order_id", sa.Integer(), nullable=True),
        sa.Column("shipment_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("origin_country_code", sa.String(length=2), nullable=False),
        sa.Column("logistic_name", sa.String(length=100), nullable=True),
        sa.Column("tracking_number", sa.String(length=255), nullable=True),
        sa.Column("shopify_fulfillment_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"], ["supplier_orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["shipment_id"], ["shipments.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "store_id",
            "order_id",
            "provider",
            name="uq_auto_fulfillment_store_order_provider",
        ),
    )
    for column in (
        "organization_id",
        "store_id",
        "order_id",
        "supplier_order_id",
        "shipment_id",
        "provider",
        "status",
    ):
        op.create_index(
            f"ix_auto_fulfillment_jobs_{column}",
            "auto_fulfillment_jobs",
            [column],
            unique=False,
        )


def downgrade():
    for column in (
        "status",
        "provider",
        "shipment_id",
        "supplier_order_id",
        "order_id",
        "store_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_auto_fulfillment_jobs_{column}",
            table_name="auto_fulfillment_jobs",
        )
    op.drop_table("auto_fulfillment_jobs")
    op.drop_column("supplier_connections", "auto_notify_customer")
    op.drop_column("supplier_connections", "auto_origin_country_code")
    op.drop_column("supplier_connections", "auto_fulfillment_enabled")
