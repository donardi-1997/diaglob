"""Persist managed Shopify token-exchange credentials in pending installation grants.

Revision ID: d9e0f1a2b3c4
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shopify_pending_installs", sa.Column(
        "grant_method", sa.String(30), nullable=False, server_default="oauth_code"
    ))
    op.add_column("shopify_pending_installs", sa.Column(
        "refresh_token_encrypted", sa.Text(), nullable=True
    ))
    op.add_column("shopify_pending_installs", sa.Column(
        "access_token_expires_at", sa.DateTime(), nullable=True
    ))
    op.add_column("shopify_pending_installs", sa.Column(
        "refresh_token_expires_at", sa.DateTime(), nullable=True
    ))


def downgrade():
    op.drop_column("shopify_pending_installs", "refresh_token_expires_at")
    op.drop_column("shopify_pending_installs", "access_token_expires_at")
    op.drop_column("shopify_pending_installs", "refresh_token_encrypted")
    op.drop_column("shopify_pending_installs", "grant_method")
