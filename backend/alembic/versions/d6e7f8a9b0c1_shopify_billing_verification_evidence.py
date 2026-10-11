"""Append-only review evidence for verified Shopify subscriptions.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_billing_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=45), nullable=False),
        sa.Column("current_plan", sa.String(length=30), nullable=False),
        sa.Column("target_plan", sa.String(length=30), nullable=True),
        sa.Column("target_period_months", sa.Integer(), nullable=True),
        sa.Column("installation_connected_at", sa.DateTime(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
    )
    for column in ("organization_id", "store_id", "observed_at"):
        op.create_index(
            f"ix_shopify_billing_verifications_{column}",
            "shopify_billing_verifications", [column], unique=False,
        )


def downgrade():
    for column in ("observed_at", "store_id", "organization_id"):
        op.drop_index(
            f"ix_shopify_billing_verifications_{column}",
            table_name="shopify_billing_verifications",
        )
    op.drop_table("shopify_billing_verifications")
