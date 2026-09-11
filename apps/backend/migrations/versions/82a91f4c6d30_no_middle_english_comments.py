"""Retire middle-school English opinion fields without deleting saved history.

Revision ID: 82a91f4c6d30
Revises: 7d26cb91a540
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "82a91f4c6d30"
down_revision: str | Sequence[str] | None = "7d26cb91a540"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        UPDATE column_definitions
        SET is_active = FALSE
        WHERE subject = 'english' AND grade_level BETWEEN 5 AND 8
          AND value_type = 'text' AND is_active
    """)
    )


def downgrade() -> None:
    # Do not reactivate fields an administrator may have independently disabled.
    pass
