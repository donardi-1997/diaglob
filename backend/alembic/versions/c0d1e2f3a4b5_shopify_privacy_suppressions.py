"""Add store-scoped keyed privacy suppression tombstones.

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a5
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_suppressions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("selector_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="staged"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "store_id", "kind", "selector_digest",
            name="uq_shopify_privacy_suppression_subject",
        ),
    )
    for col in ("organization_id", "store_id", "request_id", "status"):
        op.create_index(
            "ix_shopify_privacy_suppressions_" + col,
            "shopify_privacy_suppressions",
            [col],
        )


def downgrade():
    for col in ("status", "request_id", "store_id", "organization_id"):
        op.drop_index(
            "ix_shopify_privacy_suppressions_" + col,
            table_name="shopify_privacy_suppressions",
        )
    op.drop_table("shopify_privacy_suppressions")
