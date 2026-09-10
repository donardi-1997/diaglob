"""add customer risk moderation and disputes

Revision ID: l8f9a0b1c2d3
Revises: k7f8a9b0c1d2
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l8f9a0b1c2d3"
down_revision: Union[str, None] = "k7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_risk_report_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=30), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "actor_role IN ('reporter', 'platform_admin', 'system')",
            name="ck_customer_risk_report_event_actor_role",
        ),
        sa.CheckConstraint(
            "action IN ('report_submitted', 'report_updated', "
            "'report_withdrawn', 'moderation_confirmed', "
            "'moderation_dismissed', 'moderation_disputed', "
            "'moderation_reset_pending')",
            name="ck_customer_risk_report_event_action",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["customer_risk_reports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_risk_report_events_report_id",
        "customer_risk_report_events",
        ["report_id"],
    )
    op.create_index(
        "ix_customer_risk_report_events_organization_id",
        "customer_risk_report_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_risk_report_events_actor_user_id",
        "customer_risk_report_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_customer_risk_report_events_action",
        "customer_risk_report_events",
        ["action"],
    )
    op.create_index(
        "ix_customer_risk_report_events_created_at",
        "customer_risk_report_events",
        ["created_at"],
    )
    op.create_index(
        "ix_customer_risk_report_events_org_created",
        "customer_risk_report_events",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "customer_risk_disputes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requester_organization_id", sa.Integer(), nullable=False),
        sa.Column("requester_store_id", sa.Integer(), nullable=True),
        sa.Column("requester_user_id", sa.Integer(), nullable=True),
        sa.Column("local_customer_id", sa.Integer(), nullable=True),
        sa.Column("phone_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("email_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'withdrawn')",
            name="ck_customer_risk_dispute_status",
        ),
        sa.CheckConstraint(
            "phone_fingerprint IS NOT NULL OR email_fingerprint IS NOT NULL",
            name="ck_customer_risk_dispute_identifier",
        ),
        sa.ForeignKeyConstraint(
            ["requester_organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requester_store_id"], ["stores.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["local_customer_id"], ["customers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "requester_organization_id",
        "requester_store_id",
        "requester_user_id",
        "local_customer_id",
        "phone_fingerprint",
        "email_fingerprint",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_customer_risk_disputes_{column}",
            "customer_risk_disputes",
            [column],
        )
    op.create_index(
        "ix_customer_risk_disputes_phone_status",
        "customer_risk_disputes",
        ["phone_fingerprint", "status"],
    )
    op.create_index(
        "ix_customer_risk_disputes_email_status",
        "customer_risk_disputes",
        ["email_fingerprint", "status"],
    )
    op.create_index(
        "ix_customer_risk_disputes_org_customer_status",
        "customer_risk_disputes",
        ["requester_organization_id", "local_customer_id", "status"],
    )

    op.create_table(
        "customer_risk_dispute_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=30), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "actor_role IN ('requester', 'platform_admin', 'system')",
            name="ck_customer_risk_dispute_event_actor_role",
        ),
        sa.CheckConstraint(
            "action IN ('dispute_submitted', 'dispute_updated', "
            "'dispute_withdrawn', 'dispute_accepted', 'dispute_rejected')",
            name="ck_customer_risk_dispute_event_action",
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["customer_risk_disputes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_risk_dispute_events_dispute_id",
        "customer_risk_dispute_events",
        ["dispute_id"],
    )
    op.create_index(
        "ix_customer_risk_dispute_events_organization_id",
        "customer_risk_dispute_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_risk_dispute_events_actor_user_id",
        "customer_risk_dispute_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_customer_risk_dispute_events_action",
        "customer_risk_dispute_events",
        ["action"],
    )
    op.create_index(
        "ix_customer_risk_dispute_events_created_at",
        "customer_risk_dispute_events",
        ["created_at"],
    )
    op.create_index(
        "ix_customer_risk_dispute_events_org_created",
        "customer_risk_dispute_events",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_risk_dispute_events_org_created",
        table_name="customer_risk_dispute_events",
    )
    op.drop_index(
        "ix_customer_risk_dispute_events_created_at",
        table_name="customer_risk_dispute_events",
    )
    op.drop_index(
        "ix_customer_risk_dispute_events_action",
        table_name="customer_risk_dispute_events",
    )
    op.drop_index(
        "ix_customer_risk_dispute_events_actor_user_id",
        table_name="customer_risk_dispute_events",
    )
    op.drop_index(
        "ix_customer_risk_dispute_events_organization_id",
        table_name="customer_risk_dispute_events",
    )
    op.drop_index(
        "ix_customer_risk_dispute_events_dispute_id",
        table_name="customer_risk_dispute_events",
    )
    op.drop_table("customer_risk_dispute_events")

    op.drop_index(
        "ix_customer_risk_disputes_org_customer_status",
        table_name="customer_risk_disputes",
    )
    op.drop_index(
        "ix_customer_risk_disputes_email_status",
        table_name="customer_risk_disputes",
    )
    op.drop_index(
        "ix_customer_risk_disputes_phone_status",
        table_name="customer_risk_disputes",
    )
    for column in reversed((
        "requester_organization_id",
        "requester_store_id",
        "requester_user_id",
        "local_customer_id",
        "phone_fingerprint",
        "email_fingerprint",
        "status",
        "created_at",
    )):
        op.drop_index(
            f"ix_customer_risk_disputes_{column}",
            table_name="customer_risk_disputes",
        )
    op.drop_table("customer_risk_disputes")

    op.drop_index(
        "ix_customer_risk_report_events_org_created",
        table_name="customer_risk_report_events",
    )
    op.drop_index(
        "ix_customer_risk_report_events_created_at",
        table_name="customer_risk_report_events",
    )
    op.drop_index(
        "ix_customer_risk_report_events_action",
        table_name="customer_risk_report_events",
    )
    op.drop_index(
        "ix_customer_risk_report_events_actor_user_id",
        table_name="customer_risk_report_events",
    )
    op.drop_index(
        "ix_customer_risk_report_events_organization_id",
        table_name="customer_risk_report_events",
    )
    op.drop_index(
        "ix_customer_risk_report_events_report_id",
        table_name="customer_risk_report_events",
    )
    op.drop_table("customer_risk_report_events")
