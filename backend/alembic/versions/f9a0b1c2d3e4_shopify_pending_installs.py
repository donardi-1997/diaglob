"""Add a short-lived, unbound Shopify installation grant table.

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
"""
from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_pending_installs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("shop_domain", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("state_used", sa.Boolean(), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=True),
        sa.Column("claim_hash", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_shopify_pending_installs_state",
                    "shopify_pending_installs", ["state"], unique=True)
    op.create_index("ix_shopify_pending_installs_claim_hash",
                    "shopify_pending_installs", ["claim_hash"], unique=True)


def downgrade():
    op.drop_index("ix_shopify_pending_installs_claim_hash",
                  table_name="shopify_pending_installs")
    op.drop_index("ix_shopify_pending_installs_state",
                  table_name="shopify_pending_installs")
    op.drop_table("shopify_pending_installs")
