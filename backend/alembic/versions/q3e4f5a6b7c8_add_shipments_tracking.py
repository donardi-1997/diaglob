"""add shipments and CJ webhook receipts

Revision ID: q3e4f5a6b7c8
Revises: p2d3e4f5a6b7
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa


revision = "q3e4f5a6b7c8"
down_revision = "p2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("supplier_order_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("tracking_number", sa.String(length=255), nullable=False),
        sa.Column("logistic_name", sa.String(length=255), nullable=True),
        sa.Column("tracking_provider", sa.String(length=255), nullable=True),
        sa.Column("tracking_url", sa.Text(), nullable=True),
        sa.Column("origin_country_code", sa.String(length=20), nullable=True),
        sa.Column("destination_country_code", sa.String(length=20), nullable=True),
        sa.Column("last_mile_carrier", sa.String(length=255), nullable=True),
        sa.Column("last_mile_tracking_number", sa.String(length=255), nullable=True),
        sa.Column("normalized_status", sa.String(length=40), nullable=False),
        sa.Column("provider_status_code", sa.Integer(), nullable=True),
        sa.Column("provider_status_label", sa.String(length=255), nullable=True),
        sa.Column("delivery_days", sa.String(length=50), nullable=True),
        sa.Column("delivery_time", sa.DateTime(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"], ["supplier_orders.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "store_id",
            "provider",
            "tracking_number",
            name="uq_shipment_store_provider_tracking",
        ),
    )
    for column in (
        "organization_id",
        "store_id",
        "order_id",
        "supplier_order_id",
        "provider",
        "tracking_number",
        "normalized_status",
        "provider_status_code",
    ):
        op.create_index(
            f"ix_shipments_{column}",
            "shipments",
            [column],
            unique=False,
        )

    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("provider_event_key", sa.String(length=64), nullable=False),
        sa.Column("provider_status_code", sa.Integer(), nullable=True),
        sa.Column("normalized_status", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shipment_id"], ["shipments.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "shipment_id",
            "provider_event_key",
            name="uq_tracking_event_shipment_provider_key",
        ),
    )
    op.create_index(
        "ix_tracking_events_shipment_id",
        "tracking_events",
        ["shipment_id"],
        unique=False,
    )
    op.create_index(
        "ix_tracking_events_normalized_status",
        "tracking_events",
        ["normalized_status"],
        unique=False,
    )
    op.create_index(
        "ix_tracking_events_event_at",
        "tracking_events",
        ["event_at"],
        unique=False,
    )

    op.create_table(
        "cj_webhook_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_connection_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=50), nullable=False),
        sa.Column("message_type", sa.String(length=30), nullable=True),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_connection_id"],
            ["supplier_connections.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "supplier_connection_id",
            "message_id",
            name="uq_cj_webhook_connection_message",
        ),
    )
    op.create_index(
        "ix_cj_webhook_receipts_supplier_connection_id",
        "cj_webhook_receipts",
        ["supplier_connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_cj_webhook_receipts_topic",
        "cj_webhook_receipts",
        ["topic"],
        unique=False,
    )
    op.create_index(
        "ix_cj_webhook_receipts_processing_status",
        "cj_webhook_receipts",
        ["processing_status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_cj_webhook_receipts_processing_status",
        table_name="cj_webhook_receipts",
    )
    op.drop_index(
        "ix_cj_webhook_receipts_topic",
        table_name="cj_webhook_receipts",
    )
    op.drop_index(
        "ix_cj_webhook_receipts_supplier_connection_id",
        table_name="cj_webhook_receipts",
    )
    op.drop_table("cj_webhook_receipts")

    op.drop_index("ix_tracking_events_event_at", table_name="tracking_events")
    op.drop_index(
        "ix_tracking_events_normalized_status",
        table_name="tracking_events",
    )
    op.drop_index(
        "ix_tracking_events_shipment_id",
        table_name="tracking_events",
    )
    op.drop_table("tracking_events")

    for column in reversed(
        (
            "organization_id",
            "store_id",
            "order_id",
            "supplier_order_id",
            "provider",
            "tracking_number",
            "normalized_status",
            "provider_status_code",
        )
    ):
        op.drop_index(f"ix_shipments_{column}", table_name="shipments")
    op.drop_table("shipments")
