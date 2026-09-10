"""Add missing teacher comment fields to configured, non-archived subjects.

Revision ID: 7d26cb91a540
Revises: e2a91c743b60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d26cb91a540"
down_revision: str | Sequence[str] | None = "e2a91c743b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The old grade-4 correction disabled text as well as numeric scores. A new
    # field avoids reactivating a column that an administrator may have removed.
    # Keep all existing definitions, saved values, audit rows and archives intact.
    op.execute(
        sa.text(
            """
            INSERT INTO column_definitions
                (semester_id, grade_level, subject, value_type, owner_role,
                 labels, counts_in_average, position, is_active)
            SELECT c.semester_id, c.grade_level, c.subject, 'text',
                   CASE WHEN c.subject = 'english' THEN 'main' ELSE c.subject END,
                   CAST(:labels AS jsonb), FALSE, MAX(c.position) + 1, TRUE
            FROM column_definitions c
            JOIN semesters s ON s.id = c.semester_id
            JOIN academic_years y ON y.id = s.year_id
            WHERE y.status <> 'archived'
              AND NOT EXISTS (
                  SELECT 1 FROM column_definitions note
                  WHERE note.semester_id = c.semester_id
                    AND note.grade_level = c.grade_level AND note.subject = c.subject
                    AND note.value_type = 'text' AND note.is_active
              )
            GROUP BY c.semester_id, c.grade_level, c.subject
            HAVING BOOL_OR(c.is_active AND c.value_type IN ('score', 'scale3'))
            """
        ).bindparams(
            labels='{"tr":"Öğretmen görüşleri","en":"Teacher\'s comments",'
            '"de":"Lehrerkommentare","fr":"Commentaires du professeur"}'
        )
    )


def downgrade() -> None:
    # These fields may now hold comments. Rolling back code must not erase them.
    pass
