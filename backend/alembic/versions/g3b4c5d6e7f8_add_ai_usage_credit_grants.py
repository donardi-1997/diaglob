"""add ai usage credit grants

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_credit_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("package_key", sa.String(length=40), nullable=False),
        sa.Column("responses_total", sa.Integer(), nullable=False),
        sa.Column("responses_remaining", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("purchased_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "responses_total > 0",
            name="ck_ai_credit_grant_total_positive",
        ),
        sa.CheckConstraint(
            "responses_remaining >= 0 AND responses_remaining <= responses_total",
            name="ck_ai_credit_grant_remaining_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_transaction_id",
            name="uq_ai_credit_grant_provider_transaction",
        ),
    )
    op.create_index(
        "ix_ai_usage_credit_grants_organization_id",
        "ai_usage_credit_grants",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_credit_grants_package_key",
        "ai_usage_credit_grants",
        ["package_key"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_credit_grants_status",
        "ai_usage_credit_grants",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_usage_credit_grants_status",
        table_name="ai_usage_credit_grants",
    )
    op.drop_index(
        "ix_ai_usage_credit_grants_package_key",
        table_name="ai_usage_credit_grants",
    )
    op.drop_index(
        "ix_ai_usage_credit_grants_organization_id",
        table_name="ai_usage_credit_grants",
    )
    op.drop_table("ai_usage_credit_grants")
