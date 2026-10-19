"""stage-scoped school numbers

Primary school (Hazırlık to grade 4) and middle school (grades 5-8) number
their pupils independently, so a school number is unique per year and stage.
The stage is derived by the database from the enrollment's class, including
when an enrollment changes class or its class changes grade.

Revision ID: 9b3e5d7f1c20
Revises: 3c7f1a9d2b64
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b3e5d7f1c20"
down_revision: str | Sequence[str] | None = "3c7f1a9d2b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors flrc.modules.academics.programme.MIDDLE_START_GRADE at this revision;
# migrations must not import application constants that may later change.
STAGE_FUNCTION = """
CREATE FUNCTION stage_for_grade(grade_level integer) RETURNS text
LANGUAGE sql IMMUTABLE STRICT
AS $$ SELECT CASE WHEN grade_level >= 5 THEN 'middle' ELSE 'primary' END $$
"""

# Re-derived on every insert, class change, and direct stage write, so the
# stored stage can never disagree with the enrollment's class.
ENROLLMENT_TRIGGER_FUNCTION = """
CREATE FUNCTION enrollments_derive_stage() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.stage := (
        SELECT stage_for_grade(grade_level) FROM school_classes WHERE id = NEW.class_id
    );
    RETURN NEW;
END
$$
"""

ENROLLMENT_TRIGGER = """
CREATE TRIGGER enrollments_derive_stage
BEFORE INSERT OR UPDATE OF class_id, stage ON enrollments
FOR EACH ROW EXECUTE FUNCTION enrollments_derive_stage()
"""

# A class moved across the grade 4/5 boundary carries its pupils into the
# other stage; a number clash there fails the whole class update.
CLASS_TRIGGER_FUNCTION = """
CREATE FUNCTION school_classes_sync_enrollment_stage() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE enrollments SET stage = stage_for_grade(NEW.grade_level) WHERE class_id = NEW.id;
    RETURN NULL;
END
$$
"""

CLASS_TRIGGER = """
CREATE TRIGGER school_classes_sync_enrollment_stage
AFTER UPDATE OF grade_level ON school_classes
FOR EACH ROW
WHEN (stage_for_grade(OLD.grade_level) IS DISTINCT FROM stage_for_grade(NEW.grade_level))
EXECUTE FUNCTION school_classes_sync_enrollment_stage()
"""


def upgrade() -> None:
    op.execute(STAGE_FUNCTION)
    op.add_column("enrollments", sa.Column("stage", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE enrollments
        SET stage = stage_for_grade(school_classes.grade_level)
        FROM school_classes
        WHERE school_classes.id = enrollments.class_id
        """
    )
    op.alter_column("enrollments", "stage", nullable=False)
    op.create_check_constraint(
        op.f("ck_enrollments_stage_valid"),
        "enrollments",
        "stage IN ('primary','middle')",
    )
    op.drop_constraint(
        op.f("uq_enrollments_year_id_school_number"),
        "enrollments",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_enrollments_year_id_stage_school_number"),
        "enrollments",
        ["year_id", "stage", "school_number"],
    )
    op.execute(ENROLLMENT_TRIGGER_FUNCTION)
    op.execute(ENROLLMENT_TRIGGER)
    op.execute(CLASS_TRIGGER_FUNCTION)
    op.execute(CLASS_TRIGGER)


def downgrade() -> None:
    # Fails while a primary and a middle-school pupil share a number in one
    # year: a downgrade must not silently renumber pupils.
    op.create_unique_constraint(
        op.f("uq_enrollments_year_id_school_number"),
        "enrollments",
        ["year_id", "school_number"],
    )
    op.execute("DROP TRIGGER school_classes_sync_enrollment_stage ON school_classes")
    op.execute("DROP FUNCTION school_classes_sync_enrollment_stage()")
    op.execute("DROP TRIGGER enrollments_derive_stage ON enrollments")
    op.execute("DROP FUNCTION enrollments_derive_stage()")
    op.drop_constraint(
        op.f("uq_enrollments_year_id_stage_school_number"),
        "enrollments",
        type_="unique",
    )
    op.drop_constraint(op.f("ck_enrollments_stage_valid"), "enrollments", type_="check")
    op.drop_column("enrollments", "stage")
    op.execute("DROP FUNCTION stage_for_grade(integer)")
