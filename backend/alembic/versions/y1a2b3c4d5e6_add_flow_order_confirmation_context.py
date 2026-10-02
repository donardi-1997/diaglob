"""add flow trigger context and order confirmation state

Revision ID: y1a2b3c4d5e6
Revises: x0f1a2b3c4d5
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "y1a2b3c4d5e6"
down_revision = "x0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "automation_flow_runs",
        sa.Column("trigger_context", sa.JSON(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("confirmation_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("confirmation_source", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_orders_confirmation_status",
        "orders",
        ["confirmation_status"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_orders_confirmation_status", table_name="orders")
    op.drop_column("orders", "confirmed_at")
    op.drop_column("orders", "confirmation_source")
    op.drop_column("orders", "confirmation_status")
    op.drop_column("automation_flow_runs", "trigger_context")
