"""add meta ads connections

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    if _table_exists("meta_ads_connections"):
        return

    op.create_table(
        "meta_ads_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("external_account_name", sa.String(length=500), nullable=True),
        sa.Column("account_currency", sa.String(length=10), nullable=True),
        sa.Column("account_timezone", sa.String(length=100), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sa.String(length=30), nullable=True),
        sa.Column("last_error_category", sa.String(length=50), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            name="uq_meta_ads_connection_store",
        ),
    )
    op.create_index(
        "ix_meta_ads_connections_organization_id",
        "meta_ads_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_ads_connections_status",
        "meta_ads_connections",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_meta_ads_connections_store_id",
        "meta_ads_connections",
        ["store_id"],
        unique=True,
    )


def downgrade() -> None:
    if not _table_exists("meta_ads_connections"):
        return

    op.drop_index(
        "ix_meta_ads_connections_store_id",
        table_name="meta_ads_connections",
    )
    op.drop_index(
        "ix_meta_ads_connections_status",
        table_name="meta_ads_connections",
    )
    op.drop_index(
        "ix_meta_ads_connections_organization_id",
        table_name="meta_ads_connections",
    )
    op.drop_table("meta_ads_connections")
