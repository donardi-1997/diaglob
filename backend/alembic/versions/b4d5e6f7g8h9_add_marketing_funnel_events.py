"""add marketing funnel events

Revision ID: b4d5e6f7g8h9
Revises: a3c4d5e6f7g8
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "b4d5e6f7g8h9"
down_revision = "a3c4d5e6f7g8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_funnel_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "registration_attribution_id",
            sa.Integer(),
            sa.ForeignKey(
                "marketing_registration_attributions.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("event_name", sa.String(length=60), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("medium", sa.String(length=120), nullable=True),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("content", sa.String(length=255), nullable=True),
        sa.Column("value", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column(
            "meta_delivery_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("meta_error", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "event_key",
            name="uq_marketing_funnel_event_key",
        ),
    )
    op.create_index(
        "ix_marketing_funnel_organization_id",
        "marketing_funnel_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_user_id",
        "marketing_funnel_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_registration_attribution_id",
        "marketing_funnel_events",
        ["registration_attribution_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_event_name",
        "marketing_funnel_events",
        ["event_name"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_campaign",
        "marketing_funnel_events",
        ["campaign"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_meta_status",
        "marketing_funnel_events",
        ["meta_delivery_status"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_funnel_occurred_at",
        "marketing_funnel_events",
        ["occurred_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_funnel_occurred_at",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_meta_status",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_campaign",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_event_name",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_registration_attribution_id",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_user_id",
        table_name="marketing_funnel_events",
    )
    op.drop_index(
        "ix_marketing_funnel_organization_id",
        table_name="marketing_funnel_events",
    )
    op.drop_table("marketing_funnel_events")
