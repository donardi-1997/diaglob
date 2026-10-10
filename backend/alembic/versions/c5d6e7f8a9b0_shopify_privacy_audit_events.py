"""Record PII-free Shopify privacy processing events.

Revision ID: c5d6e7f8a9b0
Revises: a4e5f6a7b8c9
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "a4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_shopify_privacy_audit_events_request_id",
        "shopify_privacy_audit_events",
        ["request_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_shopify_privacy_audit_events_request_id",
        table_name="shopify_privacy_audit_events",
    )
    op.drop_table("shopify_privacy_audit_events")
