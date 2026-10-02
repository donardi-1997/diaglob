"""add carrier connections

Revision ID: z2b3c4d5e6f7
Revises: y1a2b3c4d5e6
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "z2b3c4d5e6f7"
down_revision = "y1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "carrier_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "store_id",
            sa.Integer(),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("carrier_key", sa.String(length=50), nullable=False),
        sa.Column(
            "integration_mode",
            sa.String(length=30),
            nullable=False,
            server_default="webhook",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="connected",
        ),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("webhook_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_config", sa.JSON(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "store_id",
            "carrier_key",
            name="uq_carrier_connection_store_key",
        ),
    )
    op.create_index(
        "ix_carrier_connections_organization_id",
        "carrier_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_connections_store_id",
        "carrier_connections",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_connections_carrier_key",
        "carrier_connections",
        ["carrier_key"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_connections_status",
        "carrier_connections",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_carrier_connections_status", table_name="carrier_connections")
    op.drop_index("ix_carrier_connections_carrier_key", table_name="carrier_connections")
    op.drop_index("ix_carrier_connections_store_id", table_name="carrier_connections")
    op.drop_index("ix_carrier_connections_organization_id", table_name="carrier_connections")
    op.drop_table("carrier_connections")
