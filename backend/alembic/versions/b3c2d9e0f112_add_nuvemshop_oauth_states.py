"""add nuvemshop_oauth_states table

Revision ID: b3c2d9e0f112
Revises: f6f002b05545
Create Date: 2026-09-08 18:00:00.000000

Creates the nuvemshop_oauth_states table for persisting
OAuth state during Nuvemshop authorization flow.

Uses idempotent guards for safe re-application.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c2d9e0f112'
down_revision: Union[str, None] = 'f6f002b05545'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("nuvemshop_oauth_states"):
        return

    op.create_table(
        "nuvemshop_oauth_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("state", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.Integer, nullable=False),
        sa.Column("store_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
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
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_nuvemshop_oauth_states_state",
        "nuvemshop_oauth_states",
        ["state"],
        unique=True,
    )
    op.create_index(
        "ix_nuvemshop_oauth_states_organization_id",
        "nuvemshop_oauth_states",
        ["organization_id"],
    )
    op.create_index(
        "ix_nuvemshop_oauth_states_store_id",
        "nuvemshop_oauth_states",
        ["store_id"],
    )
    op.create_index(
        "ix_nuvemshop_oauth_states_user_id",
        "nuvemshop_oauth_states",
        ["user_id"],
    )
    op.create_index(
        "ix_nuvemshop_oauth_states_expires_at",
        "nuvemshop_oauth_states",
        ["expires_at"],
    )
    op.create_index(
        "ix_nuvemshop_oauth_states_used",
        "nuvemshop_oauth_states",
        ["used"],
    )


def downgrade() -> None:
    if not _table_exists("nuvemshop_oauth_states"):
        return

    op.drop_index("ix_nuvemshop_oauth_states_used", table_name="nuvemshop_oauth_states")
    op.drop_index("ix_nuvemshop_oauth_states_expires_at", table_name="nuvemshop_oauth_states")
    op.drop_index("ix_nuvemshop_oauth_states_user_id", table_name="nuvemshop_oauth_states")
    op.drop_index("ix_nuvemshop_oauth_states_store_id", table_name="nuvemshop_oauth_states")
    op.drop_index("ix_nuvemshop_oauth_states_organization_id", table_name="nuvemshop_oauth_states")
    op.drop_index("ix_nuvemshop_oauth_states_state", table_name="nuvemshop_oauth_states")
    op.drop_table("nuvemshop_oauth_states")
