"""Track unverified privacy evidence references without storing PII.

Revision ID: d0e1f2a3b4c5
Revises: c0d1e2f3a4b5
"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopify_privacy_control_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("control", sa.String(80), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "request_id", "control", "artifact_sha256",
            name="uq_shopify_privacy_control_evidence",
        ),
    )
    op.create_index(
        "ix_shopify_privacy_control_evidence_request_id",
        "shopify_privacy_control_evidence", ["request_id"],
    )


def downgrade():
    op.drop_index(
        "ix_shopify_privacy_control_evidence_request_id",
        table_name="shopify_privacy_control_evidence",
    )
    op.drop_table("shopify_privacy_control_evidence")
