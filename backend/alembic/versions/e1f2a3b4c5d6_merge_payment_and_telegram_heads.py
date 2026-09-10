"""merge payment and telegram migration heads

Revision ID: e1f2a3b4c5d6
Revises: 9fb2e4283c46, d7e8f9a0b1c2
Create Date: 2026-09-09
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = (
    "9fb2e4283c46",
    "d7e8f9a0b1c2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
