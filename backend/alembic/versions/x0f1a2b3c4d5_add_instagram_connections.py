"""add instagram messaging connections

Revision ID: x0f1a2b3c4d5
Revises: w9e0f1a2b3c4
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "x0f1a2b3c4d5"
down_revision = "w9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instagram_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("instagram_account_id", sa.String(length=100), nullable=False),
        sa.Column("page_id", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("store_id", name="uq_instagram_connection_store"),
        sa.UniqueConstraint(
            "instagram_account_id",
            name="uq_instagram_connection_account",
        ),
    )
    op.create_index(
        "ix_instagram_connections_organization_id",
        "instagram_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_instagram_connections_store_id",
        "instagram_connections",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_instagram_connections_instagram_account_id",
        "instagram_connections",
        ["instagram_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_instagram_connections_status",
        "instagram_connections",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_table("instagram_connections")
