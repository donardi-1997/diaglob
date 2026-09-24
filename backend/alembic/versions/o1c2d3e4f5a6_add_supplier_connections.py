"""add supplier connections

Revision ID: o1c2d3e4f5a6
Revises: n0b1c2d3e4f5
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa


revision = "o1c2d3e4f5a6"
down_revision = "n0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("external_account_name", sa.String(length=500), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
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
        sa.UniqueConstraint(
            "store_id",
            "provider",
            name="uq_supplier_connection_store_provider",
        ),
    )
    op.create_index(
        "ix_supplier_connections_organization_id",
        "supplier_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_connections_store_id",
        "supplier_connections",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_connections_provider",
        "supplier_connections",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_connections_status",
        "supplier_connections",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_supplier_connections_status", table_name="supplier_connections")
    op.drop_index("ix_supplier_connections_provider", table_name="supplier_connections")
    op.drop_index("ix_supplier_connections_store_id", table_name="supplier_connections")
    op.drop_index(
        "ix_supplier_connections_organization_id",
        table_name="supplier_connections",
    )
    op.drop_table("supplier_connections")
