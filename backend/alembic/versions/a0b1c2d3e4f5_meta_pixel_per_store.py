"""Create tenant-scoped Meta Pixel configuration; tracking disabled.

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
"""
from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meta_pixel_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("pixel_id", sa.String(length=30), nullable=False),
        sa.Column("existing_tracking", sa.String(length=30), nullable=False, server_default="unknown"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=35), nullable=False, server_default="awaiting_extension"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("store_id", name="uq_meta_pixel_store"),
    )
    op.create_index("ix_meta_pixel_configurations_organization_id",
                    "meta_pixel_configurations", ["organization_id"])
    op.create_index("ix_meta_pixel_configurations_store_id",
                    "meta_pixel_configurations", ["store_id"], unique=True)


def downgrade():
    op.drop_index("ix_meta_pixel_configurations_store_id", table_name="meta_pixel_configurations")
    op.drop_index("ix_meta_pixel_configurations_organization_id", table_name="meta_pixel_configurations")
    op.drop_table("meta_pixel_configurations")
