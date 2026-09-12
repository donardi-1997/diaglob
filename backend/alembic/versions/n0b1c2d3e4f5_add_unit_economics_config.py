"""add unit economics configuration

Revision ID: n0b1c2d3e4f5
Revises: m9a0b1c2d3e4
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "n0b1c2d3e4f5"
down_revision = "m9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store_unit_economics_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("outbound_shipping_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("return_logistics_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("default_payment_fee_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("default_payment_fee_fixed", sa.Numeric(18, 4), nullable=True),
        sa.Column("default_cod_fee_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("store_id", name="uq_store_unit_economics_store_id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "store_id",
            name="uq_unit_economics_config_identity_scope",
        ),
    )
    op.create_index(
        "ix_store_unit_economics_configs_organization_id",
        "store_unit_economics_configs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_store_unit_economics_configs_store_id",
        "store_unit_economics_configs",
        ["store_id"],
        unique=True,
    )

    op.create_table(
        "payment_method_cost_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("unit_economics_config_id", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column("fee_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("fee_fixed", sa.Numeric(18, 4), nullable=True),
        sa.Column("is_cod", sa.Boolean(), nullable=False),
        sa.Column("cod_fee_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["unit_economics_config_id", "organization_id", "store_id"],
            [
                "store_unit_economics_configs.id",
                "store_unit_economics_configs.organization_id",
                "store_unit_economics_configs.store_id",
            ],
            name="fk_unit_economics_rule_parent_scope",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "store_id",
            "payment_method",
            name="uq_unit_economics_store_payment_method",
        ),
    )
    op.create_index(
        "ix_payment_method_cost_rules_organization_id",
        "payment_method_cost_rules",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_method_cost_rules_store_id",
        "payment_method_cost_rules",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_method_cost_rules_unit_economics_config_id",
        "payment_method_cost_rules",
        ["unit_economics_config_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_payment_method_cost_rules_unit_economics_config_id",
        table_name="payment_method_cost_rules",
    )
    op.drop_index(
        "ix_payment_method_cost_rules_store_id",
        table_name="payment_method_cost_rules",
    )
    op.drop_index(
        "ix_payment_method_cost_rules_organization_id",
        table_name="payment_method_cost_rules",
    )
    op.drop_table("payment_method_cost_rules")

    op.drop_index(
        "ix_store_unit_economics_configs_store_id",
        table_name="store_unit_economics_configs",
    )
    op.drop_index(
        "ix_store_unit_economics_configs_organization_id",
        table_name="store_unit_economics_configs",
    )
    op.drop_table("store_unit_economics_configs")
