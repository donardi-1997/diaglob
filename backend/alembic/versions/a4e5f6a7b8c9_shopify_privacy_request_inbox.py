"""add durable Shopify privacy request inbox

Revision ID: a4e5f6a7b8c9
Revises: z2b3c4d5e6f7
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "a4e5f6a7b8c9"
down_revision = "z2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=50), nullable=False),
        sa.Column("shop_id", sa.String(length=80), nullable=False),
        sa.Column("shop_domain", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("selector_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=40), nullable=False,
            server_default="pending_policy_review",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("request_id", name="uq_shopify_privacy_request_id"),
    )
    for name in ("request_id", "topic", "shop_domain", "organization_id", "store_id", "status"):
        op.create_index(
            f"ix_shopify_privacy_requests_{name}",
            "shopify_privacy_requests",
            [name],
            unique=False,
        )


def downgrade():
    for name in ("status", "store_id", "organization_id", "shop_domain", "topic", "request_id"):
        op.drop_index(
            f"ix_shopify_privacy_requests_{name}",
            table_name="shopify_privacy_requests",
        )
    op.drop_table("shopify_privacy_requests")
