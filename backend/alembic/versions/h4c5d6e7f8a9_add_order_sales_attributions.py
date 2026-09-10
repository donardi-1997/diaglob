"""add order sales attributions

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4c5d6e7f8a9"
down_revision: Union[str, None] = "g3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_sales_attributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_label", sa.String(length=255), nullable=False),
        sa.Column("human_user_id", sa.Integer(), nullable=True),
        sa.Column("ai_agent_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('human', 'ai')",
            name="ck_order_sales_attribution_actor_type",
        ),
        sa.CheckConstraint(
            "NOT (human_user_id IS NOT NULL AND ai_agent_id IS NOT NULL)",
            name="ck_order_sales_attribution_single_identity",
        ),
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
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["human_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ai_agent_id"],
            ["agents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            name="uq_order_sales_attribution_order",
        ),
    )

    for column in (
        "organization_id",
        "store_id",
        "order_id",
        "actor_type",
        "human_user_id",
        "ai_agent_id",
        "conversation_id",
    ):
        op.create_index(
            f"ix_order_sales_attributions_{column}",
            "order_sales_attributions",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("order_sales_attributions")
