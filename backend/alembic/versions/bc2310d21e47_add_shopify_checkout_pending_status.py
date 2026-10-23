"""Add explicit pending Shopify Checkout state for conversational sales.

Revision ID: bc2310d21e47
Revises: ab6c73d4e5f9

This migration does not transition any existing checkout, create a Shopify
draft, or change merchant orders/billing. Only the CHECK constraint changes.
"""

from alembic import op
import sqlalchemy as sa


revision = "bc2310d21e47"
down_revision = "ab6c73d4e5f9"
branch_labels = None
depends_on = None

_BASE_STATES = (
    "collecting_variant", "collecting_quantity", "collecting_name",
    "collecting_phone", "collecting_region", "collecting_city",
    "collecting_address", "collecting_neighborhood",
    "collecting_address_complement", "awaiting_address_confirmation",
    "collecting_delivery_reference", "awaiting_order_confirmation",
    "creating_order", "order_created", "cancelled", "failed", "expired",
)
_NEW_STATES = _BASE_STATES + ("awaiting_shopify_checkout",)
_NAME = "ck_conversational_checkout_status"


def _condition(values):
    return "status IN (" + ",".join("'" + value + "'" for value in values) + ")"


def _replace_constraint(values):
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(_NAME, "conversational_checkouts", type_="check")
        op.create_check_constraint(
            _NAME, "conversational_checkouts", _condition(values)
        )
    else:
        # SQLite does not support DROP CONSTRAINT directly. Batch mode
        # recreates just this local test table; production uses PostgreSQL.
        with op.batch_alter_table(
            "conversational_checkouts", recreate="always"
        ) as batch:
            batch.drop_constraint(_NAME, type_="check")
            batch.create_check_constraint(_NAME, _condition(values))


def upgrade():
    _replace_constraint(_NEW_STATES)


def downgrade():
    bind = op.get_bind()
    count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM conversational_checkouts "
            "WHERE status = 'awaiting_shopify_checkout'"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "SHOPIFY_CHECKOUT_PENDING_ROWS_REQUIRE_EXPLICIT_RECONCILIATION"
        )
    _replace_constraint(_BASE_STATES)
