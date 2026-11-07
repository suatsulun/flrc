"""permanently deleted teacher accounts

A deleted account keeps its row so grades, grade history, save batches and jobs still point
at it, but its personal data is erased and ``deleted_at`` hides it from every list (ADR-080).
Downgrading drops the marker only; the erased data stays erased.

Revision ID: e5c2a8d4f7b1
Revises: d8b3f6a1c2e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5c2a8d4f7b1"
down_revision: str | Sequence[str] | None = "d8b3f6a1c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
