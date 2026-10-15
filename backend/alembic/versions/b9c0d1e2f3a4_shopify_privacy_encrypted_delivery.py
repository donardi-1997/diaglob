"""Encrypted synthetic Shopify merchant delivery transport.

Revision ID: b9c0d1e2f3a4
Revises: a9b0c1d2e3f4
No migration copies or processes customer data.
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_delivery_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("ciphertext_encrypted", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("synthetic_only", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.UniqueConstraint("token_digest", name="uq_shopify_privacy_delivery_token"),
    )
    for name in ("request_id", "organization_id", "store_id", "token_digest", "expires_at"):
        op.create_index(
            f"ix_shopify_privacy_delivery_artifacts_{name}",
            "shopify_privacy_delivery_artifacts", [name],
        )
    op.create_table(
        "shopify_privacy_delivery_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("actor_type", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_shopify_privacy_delivery_audit_request_id",
                    "shopify_privacy_delivery_audit", ["request_id"])


def downgrade():
    op.drop_index("ix_shopify_privacy_delivery_audit_request_id",
                  table_name="shopify_privacy_delivery_audit")
    op.drop_table("shopify_privacy_delivery_audit")
    for name in ("expires_at", "token_digest", "store_id", "organization_id", "request_id"):
        op.drop_index(f"ix_shopify_privacy_delivery_artifacts_{name}",
                      table_name="shopify_privacy_delivery_artifacts")
    op.drop_table("shopify_privacy_delivery_artifacts")
