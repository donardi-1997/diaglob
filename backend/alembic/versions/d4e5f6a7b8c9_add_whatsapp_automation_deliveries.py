"""add WhatsApp automation delivery receipts

Revision ID: d4e5f6a7b8c9
Revises: bc2310d21e47
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "bc2310d21e47"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_automation_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("campaign_recipient_execution_id", sa.Integer(), sa.ForeignKey("automation_recipient_executions.id", ondelete="CASCADE")),
        sa.Column("flow_node_execution_id", sa.Integer(), sa.ForeignKey("automation_node_executions.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="sent"),
        sa.Column("error_code", sa.String(length=50)),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()), sa.Column("read_at", sa.DateTime()), sa.Column("failed_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "store_id", "provider_message_id", name="uq_whatsapp_automation_delivery_provider"),
    )
    for name, columns in (("ix_whatsapp_automation_deliveries_organization_id", ["organization_id"]), ("ix_whatsapp_automation_deliveries_store_id", ["store_id"]), ("ix_whatsapp_automation_deliveries_provider_message_id", ["provider_message_id"]), ("ix_whatsapp_automation_deliveries_status", ["status"]), ("ix_whatsapp_automation_deliveries_campaign_recipient_execution_id", ["campaign_recipient_execution_id"]), ("ix_whatsapp_automation_deliveries_flow_node_execution_id", ["flow_node_execution_id"])):
        op.create_index(name, "whatsapp_automation_deliveries", columns)


def downgrade():
    op.drop_table("whatsapp_automation_deliveries")
