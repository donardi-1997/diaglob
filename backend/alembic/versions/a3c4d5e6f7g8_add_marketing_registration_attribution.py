"""add marketing registration attribution

Revision ID: a3c4d5e6f7g8
Revises: z2b3c4d5e6f7
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "a3c4d5e6f7g8"
down_revision = "z2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_registration_attributions",
        sa.Column("id", sa.Integer(), primary_key=True),
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
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("medium", sa.String(length=120), nullable=True),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("content", sa.String(length=255), nullable=True),
        sa.Column("term", sa.String(length=255), nullable=True),
        sa.Column("fbclid", sa.String(length=500), nullable=True),
        sa.Column("first_touch", sa.JSON(), nullable=True),
        sa.Column("last_touch", sa.JSON(), nullable=True),
        sa.Column("event_source_url", sa.Text(), nullable=True),
        sa.Column(
            "consented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "meta_delivery_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("meta_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "event_id",
            name="uq_marketing_registration_event_id",
        ),
    )
    op.create_index(
        "ix_marketing_registration_organization_id",
        "marketing_registration_attributions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_registration_user_id",
        "marketing_registration_attributions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_registration_source",
        "marketing_registration_attributions",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_registration_campaign",
        "marketing_registration_attributions",
        ["campaign"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_registration_meta_status",
        "marketing_registration_attributions",
        ["meta_delivery_status"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_registration_created_at",
        "marketing_registration_attributions",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_registration_created_at",
        table_name="marketing_registration_attributions",
    )
    op.drop_index(
        "ix_marketing_registration_meta_status",
        table_name="marketing_registration_attributions",
    )
    op.drop_index(
        "ix_marketing_registration_campaign",
        table_name="marketing_registration_attributions",
    )
    op.drop_index(
        "ix_marketing_registration_source",
        table_name="marketing_registration_attributions",
    )
    op.drop_index(
        "ix_marketing_registration_user_id",
        table_name="marketing_registration_attributions",
    )
    op.drop_index(
        "ix_marketing_registration_organization_id",
        table_name="marketing_registration_attributions",
    )
    op.drop_table("marketing_registration_attributions")
