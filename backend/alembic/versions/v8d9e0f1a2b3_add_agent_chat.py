"""add operations copilot chat persistence

Revision ID: v8d9e0f1a2b3
Revises: u7c8d9e0f1a2
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "v8d9e0f1a2b3"
down_revision = "u7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("pending_capacity", sa.JSON(), nullable=True),
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
        "status",
        "updated_at",
    ):
        op.create_index(
            f"ix_agent_chat_sessions_{column}",
            "agent_chat_sessions",
            [column],
            unique=False,
        )

    op.create_table(
        "agent_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("provider_role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("stop_reason", sa.String(length=50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_chat_sessions.id"], ondelete="CASCADE"
        ),
    )
    for column in ("session_id", "billable", "created_at"):
        op.create_index(
            f"ix_agent_chat_messages_{column}",
            "agent_chat_messages",
            [column],
            unique=False,
        )

    op.create_table(
        "agent_chat_tool_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("tool_use_id", sa.String(length=255), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["agent_chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["agent_action_approvals.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "session_id",
            "tool_use_id",
            name="uq_agent_chat_tool_call_session_use",
        ),
    )
    for column in (
        "session_id",
        "message_id",
        "tool_name",
        "approval_id",
        "status",
    ):
        op.create_index(
            f"ix_agent_chat_tool_calls_{column}",
            "agent_chat_tool_calls",
            [column],
            unique=False,
        )


def downgrade():
    for column in (
        "status",
        "approval_id",
        "tool_name",
        "message_id",
        "session_id",
    ):
        op.drop_index(
            f"ix_agent_chat_tool_calls_{column}",
            table_name="agent_chat_tool_calls",
        )
    op.drop_table("agent_chat_tool_calls")

    for column in ("created_at", "billable", "session_id"):
        op.drop_index(
            f"ix_agent_chat_messages_{column}",
            table_name="agent_chat_messages",
        )
    op.drop_table("agent_chat_messages")

    for column in (
        "updated_at",
        "status",
        "store_id",
        "user_id",
        "membership_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_agent_chat_sessions_{column}",
            table_name="agent_chat_sessions",
        )
    op.drop_table("agent_chat_sessions")
