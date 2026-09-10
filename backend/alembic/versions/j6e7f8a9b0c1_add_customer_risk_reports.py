"""add customer risk reports

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j6e7f8a9b0c1"
down_revision: Union[str, None] = "i5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_risk_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_organization_id", sa.Integer(), nullable=False),
        sa.Column("reporter_store_id", sa.Integer(), nullable=True),
        sa.Column("reporter_user_id", sa.Integer(), nullable=True),
        sa.Column("local_customer_id", sa.Integer(), nullable=True),
        sa.Column("phone_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("email_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'disputed', 'dismissed')",
            name="ck_customer_risk_report_status",
        ),
        sa.CheckConstraint(
            "reason IN ('suspected_fraud', 'payment_abuse', 'delivery_claim', "
            "'identity_mismatch', 'abusive_behavior', 'other')",
            name="ck_customer_risk_report_reason",
        ),
        sa.CheckConstraint(
            "phone_fingerprint IS NOT NULL OR email_fingerprint IS NOT NULL",
            name="ck_customer_risk_report_identifier",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_store_id"],
            ["stores.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["local_customer_id"],
            ["customers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    for column in (
        "reporter_organization_id",
        "reporter_store_id",
        "reporter_user_id",
        "local_customer_id",
        "phone_fingerprint",
        "email_fingerprint",
        "reason",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_customer_risk_reports_{column}",
            "customer_risk_reports",
            [column],
            unique=False,
        )

    op.create_index(
        "ix_customer_risk_reports_phone_status",
        "customer_risk_reports",
        ["phone_fingerprint", "status"],
        unique=False,
    )
    op.create_index(
        "ix_customer_risk_reports_email_status",
        "customer_risk_reports",
        ["email_fingerprint", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_risk_reports_email_status",
        table_name="customer_risk_reports",
    )
    op.drop_index(
        "ix_customer_risk_reports_phone_status",
        table_name="customer_risk_reports",
    )
    for column in reversed((
        "reporter_organization_id",
        "reporter_store_id",
        "reporter_user_id",
        "local_customer_id",
        "phone_fingerprint",
        "email_fingerprint",
        "reason",
        "status",
        "created_at",
    )):
        op.drop_index(
            f"ix_customer_risk_reports_{column}",
            table_name="customer_risk_reports",
        )
    op.drop_table("customer_risk_reports")
