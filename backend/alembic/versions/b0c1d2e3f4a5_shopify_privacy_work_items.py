"""Add durable Shopify privacy work items.

Revision ID: b0c1d2e3f4a5
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = "b0c1d2e3f4a5"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("area", sa.String(80), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("blocker_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "request_id", "area", name="uq_shopify_privacy_work_item_area"
        ),
    )
    op.create_index(
        "ix_shopify_privacy_work_items_request_id",
        "shopify_privacy_work_items",
        ["request_id"],
    )


def downgrade():
    op.drop_index(
        "ix_shopify_privacy_work_items_request_id",
        table_name="shopify_privacy_work_items",
    )
    op.drop_table("shopify_privacy_work_items")
