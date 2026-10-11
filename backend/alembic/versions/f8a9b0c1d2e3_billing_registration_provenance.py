"""Persist registration billing provenance without modifying legacy assignments.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("billing_onboarding_channel", sa.String(length=30), nullable=True),
    )


def downgrade():
    op.drop_column("organizations", "billing_onboarding_channel")
