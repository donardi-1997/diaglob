"""add post-sales cases

Revision ID: w9e0f1a2b3c4
Revises: v8d9e0f1a2b3
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "w9e0f1a2b3c4"
down_revision = "v8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "post_sales_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
        sa.Column("case_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("source_channel", sa.String(length=30), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "case_type IN ('warranty','return','refund','damaged','wrong_product','delivery_issue','other')",
            name="ck_post_sales_case_type",
        ),
        sa.CheckConstraint(
            "status IN ('open','waiting_customer','investigating','approved','rejected','resolved','closed')",
            name="ck_post_sales_case_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low','normal','high','urgent')",
            name="ck_post_sales_case_priority",
        ),
    )
    for column in (
        "organization_id", "store_id", "order_id", "customer_id",
        "created_by_user_id", "assigned_agent_id", "case_type", "status",
        "priority", "created_at", "updated_at",
    ):
        op.create_index(
            f"ix_post_sales_cases_{column}",
            "post_sales_cases",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_post_sales_cases_store_status_updated",
        "post_sales_cases",
        ["store_id", "status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "post_sales_case_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["post_sales_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("case_id", "organization_id", "actor_user_id", "event_type", "created_at"):
        op.create_index(
            f"ix_post_sales_case_events_{column}",
            "post_sales_case_events",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_post_sales_case_events_case_created",
        "post_sales_case_events",
        ["case_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_table("post_sales_case_events")
    op.drop_table("post_sales_cases")
