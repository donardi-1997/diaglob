"""add sales attribution audit

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i5d6e7f8a9b0"
down_revision: Union[str, None] = "h4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_sales_attribution_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("changed_by_label", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("previous_actor_type", sa.String(length=20), nullable=True),
        sa.Column("previous_actor_id", sa.Integer(), nullable=True),
        sa.Column("previous_actor_label", sa.String(length=255), nullable=True),
        sa.Column("new_actor_type", sa.String(length=20), nullable=True),
        sa.Column("new_actor_id", sa.Integer(), nullable=True),
        sa.Column("new_actor_label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "action IN ('assign', 'reassign', 'clear')",
            name="ck_order_sales_attribution_change_action",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_sales_attribution_changes_organization_id",
        "order_sales_attribution_changes",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_sales_attribution_changes_store_id",
        "order_sales_attribution_changes",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_sales_attribution_changes_order_id",
        "order_sales_attribution_changes",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_sales_attribution_changes_changed_by_user_id",
        "order_sales_attribution_changes",
        ["changed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_sales_attribution_changes_action",
        "order_sales_attribution_changes",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_order_sales_attribution_changes_created_at",
        "order_sales_attribution_changes",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_sales_attribution_changes_created_at",
        table_name="order_sales_attribution_changes",
    )
    op.drop_index(
        "ix_order_sales_attribution_changes_action",
        table_name="order_sales_attribution_changes",
    )
    op.drop_index(
        "ix_order_sales_attribution_changes_changed_by_user_id",
        table_name="order_sales_attribution_changes",
    )
    op.drop_index(
        "ix_order_sales_attribution_changes_order_id",
        table_name="order_sales_attribution_changes",
    )
    op.drop_index(
        "ix_order_sales_attribution_changes_store_id",
        table_name="order_sales_attribution_changes",
    )
    op.drop_index(
        "ix_order_sales_attribution_changes_organization_id",
        table_name="order_sales_attribution_changes",
    )
    op.drop_table("order_sales_attribution_changes")
