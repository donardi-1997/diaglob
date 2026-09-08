"""Baseline: adopt existing production schema.

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-09-08

This is a NO-OP baseline revision for adopting the existing
production database schema. The production database predates
Alembic and already contains all required tables.

To adopt an existing production database:
    alembic stamp 0001_baseline

This revision does NOT create, drop, or modify any tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op. Existing production schema is already current."""
    pass


def downgrade() -> None:
    """No-op. Cannot reverse baseline adoption."""
    pass
