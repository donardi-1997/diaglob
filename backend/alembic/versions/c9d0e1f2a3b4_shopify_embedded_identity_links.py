"""Persist explicit per-user Shopify App Bridge identity links.

Revision ID: c9d0e1f2a3b4
Revises: b9c0d1e2f3a4
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_embedded_link_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("shop_domain", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("commerce_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "shopify_embedded_identity_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_domain", sa.String(255), nullable=False),
        sa.Column("subject_digest", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("commerce_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("shop_domain", "subject_digest", name="uq_shopify_embedded_subject_shop"),
    )
    op.create_index("ix_shopify_embedded_ticket_shop", "shopify_embedded_link_tickets", ["shop_domain", "store_id"])
    op.create_index("ix_shopify_embedded_binding_store", "shopify_embedded_identity_bindings", ["store_id", "revoked_at"])


def downgrade():
    op.drop_index("ix_shopify_embedded_binding_store", table_name="shopify_embedded_identity_bindings")
    op.drop_index("ix_shopify_embedded_ticket_shop", table_name="shopify_embedded_link_tickets")
    op.drop_table("shopify_embedded_identity_bindings")
    op.drop_table("shopify_embedded_link_tickets")
