"""Add non-destructive, durable Paddle billing mirror and event ledger.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
"""
from alembic import op
import sqlalchemy as sa

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paddle_billing_customers",
        sa.Column("customer_id", sa.String(100), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("last_event_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_paddle_billing_customers_organization_id", "paddle_billing_customers", ["organization_id"])
    op.create_table(
        "paddle_billing_subscriptions",
        sa.Column("subscription_id", sa.String(100), primary_key=True),
        sa.Column("customer_id", sa.String(100), sa.ForeignKey("paddle_billing_customers.customer_id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("price_id", sa.String(100), nullable=True),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("scheduled_change_action", sa.String(30), nullable=True),
        sa.Column("scheduled_change_at", sa.DateTime(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_paddle_billing_subscriptions_customer_id", "paddle_billing_subscriptions", ["customer_id"])
    op.create_index("ix_paddle_billing_subscriptions_organization_id", "paddle_billing_subscriptions", ["organization_id"])
    op.create_table(
        "paddle_webhook_events",
        sa.Column("event_id", sa.String(100), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "paddle_ai_reconciliations",
        sa.Column("transaction_id", sa.String(100), primary_key=True),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("customer_id", sa.String(100), nullable=True),
        sa.Column("claimed_organization_id", sa.String(100), nullable=True),
        sa.Column("package_key", sa.String(40), nullable=True),
        sa.Column("price_id", sa.String(100), nullable=True),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_paddle_ai_reconciliations_customer_id",
                    "paddle_ai_reconciliations", ["customer_id"])


def downgrade():
    # Paddle state and notification history are permanent operational data.
    # A downgrade needs a reviewed, non-destructive forward migration.
    raise RuntimeError("Refusing to delete persistent Paddle billing records")
