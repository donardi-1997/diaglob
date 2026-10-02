"""add agent action approvals

Revision ID: u7c8d9e0f1a2
Revises: t6b7c8d9e0f1
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "u7c8d9e0f1a2"
down_revision = "t6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_action_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("risk", sa.String(length=30), nullable=False),
        sa.Column("confirmation", sa.String(length=30), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["organization_memberships.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], ondelete="CASCADE"
        ),
    )
    for column in (
        "organization_id",
        "membership_id",
        "user_id",
        "store_id",
        "tool_name",
        "action",
        "arguments_hash",
        "status",
        "expires_at",
    ):
        op.create_index(
            f"ix_agent_action_approvals_{column}",
            "agent_action_approvals",
            [column],
            unique=False,
        )


def downgrade():
    for column in (
        "expires_at",
        "status",
        "arguments_hash",
        "action",
        "tool_name",
        "store_id",
        "user_id",
        "membership_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_agent_action_approvals_{column}",
            table_name="agent_action_approvals",
        )
    op.drop_table("agent_action_approvals")
