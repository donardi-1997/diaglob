"""Retain signed Shopify shop identity after uninstall (no buyer PII).

Revision ID: a9b0c1d2e3f4
Revises: f9a0b1c2d3e4
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b0c1d2e3f4"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_shop_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.String(80), nullable=False),
        sa.Column("shop_domain", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.String(40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("uninstalled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "shop_id", "shop_domain", name="uq_shopify_privacy_shop_identity",
        ),
    )
    for name in ("shop_id", "shop_domain", "organization_id", "store_id"):
        op.create_index(
            "ix_shopify_privacy_shop_identities_" + name,
            "shopify_privacy_shop_identities", [name],
        )


def downgrade():
    for name in ("store_id", "organization_id", "shop_domain", "shop_id"):
        op.drop_index(
            "ix_shopify_privacy_shop_identities_" + name,
            table_name="shopify_privacy_shop_identities",
        )
    op.drop_table("shopify_privacy_shop_identities")
