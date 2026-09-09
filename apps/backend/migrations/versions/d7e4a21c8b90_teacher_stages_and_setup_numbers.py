"""teacher stages, one active semester, and setup-year numbers

Revision ID: d7e4a21c8b90
Revises: c6b1a98d42ef
Create Date: 2026-08-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e4a21c8b90"
down_revision: str | Sequence[str] | None = "c6b1a98d42ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("teaching_stage", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE users AS candidate
        SET teaching_stage = CASE
            WHEN candidate.teaching_field <> 'english' THEN NULL
            WHEN EXISTS (
                SELECT 1
                FROM teaching_assignments AS assignment
                JOIN school_classes AS class ON class.id = assignment.class_id
                WHERE assignment.user_id = candidate.id
                  AND assignment.role IN ('main', 'skills')
                  AND class.grade_level >= 5
            ) THEN 'middle'
            WHEN EXISTS (
                SELECT 1
                FROM teaching_assignments AS assignment
                JOIN school_classes AS class ON class.id = assignment.class_id
                WHERE assignment.user_id = candidate.id
                  AND assignment.role IN ('main', 'skills')
                  AND class.grade_level <= 4
            ) THEN 'primary'
            WHEN candidate.is_admin THEN 'middle'
            ELSE 'primary'
        END
        """
    )
    op.create_check_constraint(
        op.f("ck_users_teaching_stage_matches_field"),
        "users",
        "(teaching_field = 'english' AND teaching_stage IN ('primary','middle')) "
        "OR (teaching_field IN ('german','french') AND teaching_stage IS NULL)",
    )

    # Old rollover code intentionally left these numbers empty, which made an
    # otherwise complete setup year impossible to activate. Preserve any numbers
    # already entered by an administrator and append deterministic fresh values.
    op.execute(
        """
        WITH maxima AS (
            SELECT year_id, COALESCE(MAX(school_number), 0) AS base
            FROM enrollments
            GROUP BY year_id
        ),
        missing AS (
            SELECT
                enrollment.id,
                enrollment.year_id,
                ROW_NUMBER() OVER (
                    PARTITION BY enrollment.year_id
                    ORDER BY class.grade_level, class.section, student.search_name, student.id
                ) AS sequence_number
            FROM enrollments AS enrollment
            JOIN academic_years AS year ON year.id = enrollment.year_id
            JOIN school_classes AS class ON class.id = enrollment.class_id
            JOIN students AS student ON student.id = enrollment.student_id
            WHERE year.status = 'setup' AND enrollment.school_number IS NULL
        )
        UPDATE enrollments AS enrollment
        SET school_number = maxima.base + missing.sequence_number
        FROM missing
        JOIN maxima ON maxima.year_id = missing.year_id
        WHERE enrollment.id = missing.id
        """
    )

    # Repair legacy states defensively, preferring the later open semester, then
    # make the invariant database-enforced for every future transition.
    op.execute(
        """
        UPDATE semesters AS semester
        SET status = 'locked'
        WHERE semester.status = 'open'
          AND EXISTS (
              SELECT 1
              FROM semesters AS later
              WHERE later.year_id = semester.year_id
                AND later.status = 'open'
                AND later.number > semester.number
          )
        """
    )
    op.create_index(
        "uq_semesters_one_open_per_year",
        "semesters",
        ["year_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_semesters_one_open_per_year", table_name="semesters")
    op.drop_constraint(
        op.f("ck_users_teaching_stage_matches_field"),
        "users",
        type_="check",
    )
    op.drop_column("users", "teaching_stage")
