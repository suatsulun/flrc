from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from flrc.db.base import Base, TimestampMixin


def _default_teaching_stage(context: DefaultExecutionContext) -> str | None:
    """Choose the ORM insert default from the accompanying teaching field."""
    field = context.get_current_parameters().get("teaching_field", "english")
    return "primary" if field == "english" else None


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "teaching_field IN ('english','german','french')",
            name="teaching_field_valid",
        ),
        CheckConstraint(
            "(teaching_field = 'english' AND teaching_stage IN ('primary','middle')) "
            "OR (teaching_field IN ('german','french') AND teaching_stage IS NULL)",
            name="teaching_stage_matches_field",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    # Bound on first successful allowlisted Google login. Google's `sub` is
    # stable even if the Workspace email address later changes.
    google_subject: Mapped[str | None] = mapped_column(unique=True, index=True)
    full_name: Mapped[str]
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_coordinator: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    teaching_field: Mapped[str] = mapped_column(default="english")
    teaching_stage: Mapped[str | None] = mapped_column(default=_default_teaching_stage)


class AcademicYear(TimestampMixin, Base):
    __tablename__ = "academic_years"
    __table_args__ = (
        CheckConstraint("status IN ('setup','active','archived')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    label: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="setup")


class Semester(TimestampMixin, Base):
    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("year_id", "number"),
        CheckConstraint("number IN (1, 2)", name="number_valid"),
        CheckConstraint("status IN ('open','locked')", name="status_valid"),
        Index(
            "uq_semesters_one_open_per_year",
            "year_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(default="open")


class SchoolClass(TimestampMixin, Base):
    __tablename__ = "school_classes"
    __table_args__ = (
        UniqueConstraint("year_id", "grade_level", "section"),
        CheckConstraint("grade_level BETWEEN 1 AND 8", name="grade_level_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    grade_level: Mapped[int]
    section: Mapped[str]


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str]
    search_name: Mapped[str] = mapped_column(index=True)


class Enrollment(TimestampMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "year_id"),
        UniqueConstraint("year_id", "school_number"),
        CheckConstraint(
            "school_number IS NULL OR school_number > 0",
            name="school_number_positive",
        ),
        Index("ix_enrollments_class_number", "class_id", "school_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    # A school number identifies an enrollment, not a person. It remains empty
    # while a rolled-over setup year is being prepared and is required before
    # that year can be activated.
    school_number: Mapped[int | None] = mapped_column(BigInteger)


class StudentLanguage(TimestampMixin, Base):
    __tablename__ = "student_languages"
    __table_args__ = (
        UniqueConstraint("student_id", "year_id"),
        CheckConstraint("language IN ('german','french')", name="language_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    language: Mapped[str]


class TeachingAssignment(TimestampMixin, Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (
        UniqueConstraint("class_id", "role"),
        CheckConstraint("role IN ('main','skills','german','french')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    role: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ColumnDefinition(TimestampMixin, Base):
    __tablename__ = "column_definitions"
    __table_args__ = (
        CheckConstraint("grade_level BETWEEN 1 AND 8", name="grade_level_valid"),
        CheckConstraint("subject IN ('english', 'german', 'french')", name="subject_valid"),
        CheckConstraint("value_type IN ('score','scale3','text')", name="value_type_valid"),
        CheckConstraint(
            "owner_role IN ('main','skills','german','french')", name="owner_role_valid"
        ),
        Index(
            "ix_column_definitions_scope_position",
            "semester_id",
            "grade_level",
            "subject",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    grade_level: Mapped[int]
    subject: Mapped[str]
    value_type: Mapped[str]
    owner_role: Mapped[str]
    labels: Mapped[dict[str, str]] = mapped_column(JSONB)
    group_labels: Mapped[dict[str, str] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    counts_in_average: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class GradeValue(TimestampMixin, Base):
    __tablename__ = "grade_values"
    __table_args__ = (
        UniqueConstraint("student_id", "column_definition_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("scale BETWEEN 1 AND 3", name="scale_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    column_definition_id: Mapped[int] = mapped_column(
        ForeignKey("column_definitions.id"), index=True
    )
    score: Mapped[int | None] = mapped_column(SmallInteger)
    scale: Mapped[int | None] = mapped_column(SmallInteger)
    text_value: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SaveBatch(TimestampMixin, Base):
    __tablename__ = "save_batches"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    is_undo: Mapped[bool] = mapped_column(default=False)
    undone: Mapped[bool] = mapped_column(default=False)


class AuditEntry(TimestampMixin, Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("save_batches.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    column_definition_id: Mapped[int] = mapped_column(ForeignKey("column_definitions.id"))
    old_existed: Mapped[bool]
    old_score: Mapped[int | None] = mapped_column(SmallInteger)
    old_scale: Mapped[int | None] = mapped_column(SmallInteger)
    old_text: Mapped[str | None]
    new_score: Mapped[int | None] = mapped_column(SmallInteger)
    new_scale: Mapped[int | None] = mapped_column(SmallInteger)
    new_text: Mapped[str | None]
    forced: Mapped[bool] = mapped_column(default=False)
    via_grant_id: Mapped[int | None] = mapped_column(ForeignKey("override_grants.id"))


class OverrideGrant(TimestampMixin, Base):
    __tablename__ = "override_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "class_id", "role"),
        CheckConstraint("role IN ('main','skills','german','french')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    role: Mapped[str]
    expires_at: Mapped[datetime]


class JobRun(TimestampMixin, Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('progress_pdf','german_karne','french_karne','year_export')",
            name="kind_valid",
        ),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="status_valid"),
        CheckConstraint("progress >= 0", name="progress_nonnegative"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    output_filename: Mapped[str | None]
    output_mime: Mapped[str | None]
    output_size: Mapped[int | None] = mapped_column(BigInteger)
    output_blob: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    output_expires_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None]
    error_detail: Mapped[str | None] = mapped_column(Text)


class DemoVisitor(TimestampMixin, Base):
    """A temporary public-demo administrator (ADR-051).

    Links a users row to a keyed hash of Google's stable subject so a repeat
    login within the 24-hour lifetime reuses the same account. Scrubbing nulls
    the hash; the nightly demo reset removes the rows. School mode never
    creates one.
    """

    __tablename__ = "demo_visitors"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    subject_hash: Mapped[str | None] = mapped_column(unique=True, index=True)
    expires_at: Mapped[datetime]
    scrubbed_at: Mapped[datetime | None]
