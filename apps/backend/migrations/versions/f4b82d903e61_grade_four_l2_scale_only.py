"""Grade 4 second languages use only the 1–2–3 rubric.

Revision ID: f4b82d903e61
Revises: d7e4a21c8b90
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4b82d903e61"
down_revision: str | Sequence[str] | None = "d7e4a21c8b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve definitions, grade values, audit history, and archived years.
    op.execute(
        """
        UPDATE column_definitions AS column_def
        SET is_active = CASE
                WHEN column_def.value_type = 'scale3' THEN column_def.is_active
                ELSE FALSE
            END,
            counts_in_average = FALSE
        FROM semesters AS semester
        JOIN academic_years AS year ON year.id = semester.year_id
        WHERE column_def.semester_id = semester.id
          AND year.status <> 'archived'
          AND column_def.grade_level = 4
          AND column_def.subject IN ('german', 'french')
        """
    )


def downgrade() -> None:
    # Do not resurrect columns an administrator may already have removed.
    # Saved values remain available for a deliberate, reviewed restoration.
    pass
