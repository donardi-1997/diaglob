"""Record provenance of future legacy automation executions only.

Revision ID: ab6c73d4e5f9
Revises: e0f1a2b3c4d5
Historical rows remain unattributed; no backfill from payloads is performed.
"""
from alembic import op
import sqlalchemy as sa

revision = "ab6c73d4e5f9"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_execution_provenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("execution_id", sa.Integer(),
                  sa.ForeignKey("automation_executions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("organization_id", sa.Integer(),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("store_id", sa.Integer(),
                  sa.ForeignKey("stores.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("source_context", sa.String(40), nullable=False),
        sa.Column("subject_linkage", sa.String(48), nullable=False),
        sa.Column("provenance_version", sa.Integer(), nullable=False,
                  server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("execution_id",
                            name="uq_automation_execution_provenance_execution"),
    )
    for name in ("execution_id", "organization_id", "store_id", "customer_id"):
        op.create_index(
            f"ix_automation_execution_provenance_{name}",
            "automation_execution_provenance", [name],
        )


def downgrade():
    for name in ("customer_id", "store_id", "organization_id", "execution_id"):
        op.drop_index(
            f"ix_automation_execution_provenance_{name}",
            table_name="automation_execution_provenance",
        )
    op.drop_table("automation_execution_provenance")
