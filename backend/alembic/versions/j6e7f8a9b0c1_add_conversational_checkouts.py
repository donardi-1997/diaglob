"""add conversational checkouts

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
        "conversational_checkouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("ai_agent_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("product_title", sa.String(length=255), nullable=True),
        sa.Column("variant_title", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=True),
        sa.Column("shipping_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("total", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("customer_name", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address_raw", sa.Text(), nullable=True),
        sa.Column("address_line", sa.String(length=300), nullable=True),
        sa.Column("address_complement", sa.String(length=200), nullable=True),
        sa.Column("neighborhood", sa.String(length=150), nullable=True),
        sa.Column("city", sa.String(length=150), nullable=True),
        sa.Column("region", sa.String(length=150), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=30), nullable=True),
        sa.Column("delivery_reference", sa.Text(), nullable=True),
        sa.Column("address_confidence_score", sa.Integer(), nullable=False),
        sa.Column("address_validation_status", sa.String(length=20), nullable=False),
        sa.Column("address_confirmed", sa.Boolean(), nullable=False),
        sa.Column("address_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("customer_confirmed", sa.Boolean(), nullable=False),
        sa.Column("customer_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_order_id", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'collecting_variant','collecting_quantity','collecting_name',"
            "'collecting_phone','collecting_region','collecting_city',"
            "'collecting_address','collecting_neighborhood',"
            "'collecting_address_complement','awaiting_address_confirmation',"
            "'collecting_delivery_reference','awaiting_order_confirmation',"
            "'creating_order','order_created','cancelled','failed','expired'"
            ")",
            name="ck_conversational_checkout_status",
        ),
        sa.CheckConstraint(
            "payment_method = 'cash_on_delivery'",
            name="ck_conversational_checkout_payment_method",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ai_agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "store_id",
        "conversation_id",
        "customer_id",
        "ai_agent_id",
        "status",
        "product_id",
        "variant_id",
        "created_order_id",
        "expires_at",
    ):
        op.create_index(
            f"ix_conversational_checkouts_{column}",
            "conversational_checkouts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in reversed(
        (
            "organization_id",
            "store_id",
            "conversation_id",
            "customer_id",
            "ai_agent_id",
            "status",
            "product_id",
            "variant_id",
            "created_order_id",
            "expires_at",
        )
    ):
        op.drop_index(
            f"ix_conversational_checkouts_{column}",
            table_name="conversational_checkouts",
        )
    op.drop_table("conversational_checkouts")
