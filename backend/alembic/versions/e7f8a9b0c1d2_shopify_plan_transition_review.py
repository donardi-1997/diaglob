"""Add Shopify plan transition *review* records, without changing paid access.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_plan_transition_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("verification_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("installation_connected_at", sa.DateTime(), nullable=False),
        sa.Column("baseline_plan", sa.String(length=30), nullable=False),
        sa.Column("target_plan", sa.String(length=30), nullable=False),
        sa.Column("target_period_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_shopify_plan_transition_reviews_organization_id",
        "shopify_plan_transition_reviews", ["organization_id"],
    )
    op.create_index(
        "ix_shopify_plan_transition_reviews_verification_id",
        "shopify_plan_transition_reviews", ["verification_id"], unique=True,
    )
    op.create_index(
        "uq_shopify_pending_transition_org",
        "shopify_plan_transition_reviews", ["organization_id"], unique=True,
        sqlite_where=sa.text("status = 'pending_review'"),
        postgresql_where=sa.text("status = 'pending_review'"),
    )


def downgrade():
    for index_name in (
        "uq_shopify_pending_transition_org",
        "ix_shopify_plan_transition_reviews_verification_id",
        "ix_shopify_plan_transition_reviews_organization_id",
    ):
        op.drop_index(
            index_name, table_name="shopify_plan_transition_reviews"
        )
    op.drop_table("shopify_plan_transition_reviews")
