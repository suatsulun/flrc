"""year scoped student numbers and teacher fields

Revision ID: a4f93b7c2d10
Revises: 5e9c1e0f2a44
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4f93b7c2d10"
down_revision: str | Sequence[str] | None = "5e9c1e0f2a44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "teaching_field",
            sa.String(),
            nullable=False,
            server_default="english",
        ),
    )
    # Preserve the obvious teaching fields in existing installations. Mixed-role
    # legacy users remain English so an admin can resolve ambiguous assignments
    # explicitly instead of this migration silently deleting them.
    op.execute(
        """
        UPDATE users AS candidate
        SET teaching_field = CASE
            WHEN EXISTS (
                SELECT 1 FROM teaching_assignments AS assignment
                WHERE assignment.user_id = candidate.id AND assignment.role = 'german'
            ) AND NOT EXISTS (
                SELECT 1 FROM teaching_assignments AS assignment
                WHERE assignment.user_id = candidate.id
                  AND assignment.role IN ('main', 'skills', 'french')
            ) THEN 'german'
            WHEN EXISTS (
                SELECT 1 FROM teaching_assignments AS assignment
                WHERE assignment.user_id = candidate.id AND assignment.role = 'french'
            ) AND NOT EXISTS (
                SELECT 1 FROM teaching_assignments AS assignment
                WHERE assignment.user_id = candidate.id
                  AND assignment.role IN ('main', 'skills', 'german')
            ) THEN 'french'
            ELSE 'english'
        END
        """
    )
    op.create_check_constraint(
        op.f("ck_users_teaching_field_valid"),
        "users",
        "teaching_field IN ('english','german','french')",
    )

    op.add_column(
        "enrollments",
        sa.Column("school_number", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE enrollments
        SET school_number = students.school_number
        FROM students
        WHERE students.id = enrollments.student_id
        """
    )
    op.create_check_constraint(
        op.f("ck_enrollments_school_number_positive"),
        "enrollments",
        "school_number IS NULL OR school_number > 0",
    )
    op.create_unique_constraint(
        op.f("uq_enrollments_year_id_school_number"),
        "enrollments",
        ["year_id", "school_number"],
    )
    op.create_index(
        "ix_enrollments_class_number",
        "enrollments",
        ["class_id", "school_number"],
        unique=False,
    )
    op.create_index(
        "ix_column_definitions_scope_position",
        "column_definitions",
        ["semester_id", "grade_level", "subject", "position"],
        unique=False,
    )
    op.drop_constraint(op.f("uq_students_school_number"), "students", type_="unique")
    op.drop_column("students", "school_number")


def downgrade() -> None:
    op.drop_index("ix_column_definitions_scope_position", table_name="column_definitions")
    op.drop_index("ix_enrollments_class_number", table_name="enrollments")
    op.add_column(
        "students",
        sa.Column("school_number", sa.BigInteger(), nullable=True),
    )
    # The old schema cannot represent a number reused by different students in
    # different years. Student ids provide a deterministic, unique fallback so
    # the downgrade remains executable without corrupting relationships.
    op.execute("UPDATE students SET school_number = id")
    op.alter_column("students", "school_number", nullable=False)
    op.create_unique_constraint(
        op.f("uq_students_school_number"),
        "students",
        ["school_number"],
    )
    op.drop_constraint(
        op.f("uq_enrollments_year_id_school_number"),
        "enrollments",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_enrollments_school_number_positive"),
        "enrollments",
        type_="check",
    )
    op.drop_column("enrollments", "school_number")

    op.drop_constraint(op.f("ck_users_teaching_field_valid"), "users", type_="check")
    op.drop_column("users", "teaching_field")
