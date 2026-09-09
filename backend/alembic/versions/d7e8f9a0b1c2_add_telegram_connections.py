"""add telegram connections

Revision ID: d7e8f9a0b1c2
Revises: c4a5b6d7e8f9
Create Date: 2026-09-09 15:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c4a5b6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("telegram_connections"):
        return

    op.create_table(
        "telegram_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_username", sa.String(length=255), nullable=True),
        sa.Column("bot_name", sa.String(length=255), nullable=True),
        sa.Column("bot_token_encrypted", sa.Text(), nullable=False),
        sa.Column("webhook_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("webhook_path_token", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
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
        sa.UniqueConstraint("store_id", name="uq_telegram_connection_store"),
        sa.UniqueConstraint("bot_id", name="uq_telegram_connection_bot_id"),
        sa.UniqueConstraint(
            "webhook_path_token",
            name="uq_telegram_webhook_path_token",
        ),
    )
    op.create_index(
        "ix_telegram_connections_organization_id",
        "telegram_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_connections_store_id",
        "telegram_connections",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_connections_bot_id",
        "telegram_connections",
        ["bot_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_connections_webhook_path_token",
        "telegram_connections",
        ["webhook_path_token"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_connections_status",
        "telegram_connections",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists("telegram_connections"):
        return
    op.drop_table("telegram_connections")
