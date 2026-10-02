"""add supplier variant mappings

Revision ID: s5a6b7c8d9e0
Revises: r4f5a6b7c8d9
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "s5a6b7c8d9e0"
down_revision = "r4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_variant_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_variant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_product_id", sa.String(length=255), nullable=False),
        sa.Column("external_variant_id", sa.String(length=255), nullable=False),
        sa.Column("external_sku", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_variant_id"],
            ["product_variants.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "store_id",
            "provider",
            "product_variant_id",
            name="uq_supplier_variant_mapping_store_provider_variant",
        ),
    )
    op.create_index(
        "ix_supplier_variant_mappings_organization_id",
        "supplier_variant_mappings",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_variant_mappings_store_id",
        "supplier_variant_mappings",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_variant_mappings_product_variant_id",
        "supplier_variant_mappings",
        ["product_variant_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_variant_mappings_provider",
        "supplier_variant_mappings",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_variant_mappings_external_variant_id",
        "supplier_variant_mappings",
        ["external_variant_id"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_variant_mappings_active",
        "supplier_variant_mappings",
        ["active"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_supplier_variant_mappings_active",
        table_name="supplier_variant_mappings",
    )
    op.drop_index(
        "ix_supplier_variant_mappings_external_variant_id",
        table_name="supplier_variant_mappings",
    )
    op.drop_index(
        "ix_supplier_variant_mappings_provider",
        table_name="supplier_variant_mappings",
    )
    op.drop_index(
        "ix_supplier_variant_mappings_product_variant_id",
        table_name="supplier_variant_mappings",
    )
    op.drop_index(
        "ix_supplier_variant_mappings_store_id",
        table_name="supplier_variant_mappings",
    )
    op.drop_index(
        "ix_supplier_variant_mappings_organization_id",
        table_name="supplier_variant_mappings",
    )
    op.drop_table("supplier_variant_mappings")
