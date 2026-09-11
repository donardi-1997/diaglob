"""add merchant trial entitlement and anti-abuse identity ledger

Revision ID: m9a0b1c2d3e4
Revises: l8f9a0b1c2d3
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa


revision = "m9a0b1c2d3e4"
down_revision = "l8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trial_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("blocked_at", sa.DateTime(), nullable=True),
        sa.Column("activated_by_provider", sa.String(length=30), nullable=True),
        sa.Column("activated_by_identity_hash", sa.String(length=64), nullable=True),
        sa.Column("ai_response_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            name="uq_trial_entitlement_organization",
        ),
    )
    op.create_index(
        "ix_trial_entitlements_organization_id",
        "trial_entitlements",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_trial_entitlements_status",
        "trial_entitlements",
        ["status"],
        unique=False,
    )

    op.create_table(
        "trial_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("first_organization_id", sa.Integer(), nullable=False),
        sa.Column("first_store_id", sa.Integer(), nullable=True),
        sa.Column("trial_entitlement_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("trial_consumed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "identity_hash",
            name="uq_trial_identity_provider_hash",
        ),
    )
    op.create_index(
        "ix_trial_identities_provider",
        "trial_identities",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_trial_identities_identity_hash",
        "trial_identities",
        ["identity_hash"],
        unique=False,
    )
    op.create_index(
        "ix_trial_identities_first_organization_id",
        "trial_identities",
        ["first_organization_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_trial_identities_first_organization_id",
        table_name="trial_identities",
    )
    op.drop_index("ix_trial_identities_identity_hash", table_name="trial_identities")
    op.drop_index("ix_trial_identities_provider", table_name="trial_identities")
    op.drop_table("trial_identities")

    op.drop_index("ix_trial_entitlements_status", table_name="trial_entitlements")
    op.drop_index(
        "ix_trial_entitlements_organization_id",
        table_name="trial_entitlements",
    )
    op.drop_table("trial_entitlements")
