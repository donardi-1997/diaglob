"""Add staged Shopify WebPixel identity for each Diaglob store.

Revision ID: a1b2c3d4e5f6
Revises: a0b1c2d3e4f5
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("meta_pixel_configurations", sa.Column("web_pixel_gid", sa.String(128), nullable=True))
    op.add_column("meta_pixel_configurations", sa.Column("source_id", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("meta_pixel_configurations", "source_id")
    op.drop_column("meta_pixel_configurations", "web_pixel_gid")
