"""Hazırlık classes: grade 0 with named sections.

Revision ID: 3c7f1a9d2b64
Revises: 82a91f4c6d30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3c7f1a9d2b64"
down_revision: str | Sequence[str] | None = "82a91f4c6d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRADE_CONSTRAINTS = (
    ("school_classes", "ck_school_classes_grade_level_valid"),
    ("column_definitions", "ck_column_definitions_grade_level_valid"),
)


def _set_grade_range(lowest: int) -> None:
    for table, name in GRADE_CONSTRAINTS:
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"grade_level BETWEEN {lowest} AND 8")


def upgrade() -> None:
    _set_grade_range(0)


def downgrade() -> None:
    # Fails while Hazırlık rows exist: a downgrade must not silently drop classes.
    _set_grade_range(1)
