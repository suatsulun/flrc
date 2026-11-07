import base64
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from flrc.db.models import (
    AcademicYear,
    ColumnDefinition,
    Enrollment,
    GradeValue,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.modules.academics.class_names import PREP_GRADE, class_label
from flrc.modules.academics.fields import SUBJECT_LOCALE, cell_value
from flrc.modules.academics.fields import pick_label as field_label
from flrc.modules.reports.models import ReportCard, ReportField, ReportSigner


@dataclass(frozen=True)
class ReportSetSpec:
    subject: str
    first_grade: int
    last_grade: int


REPORT_SETS = {
    "english_elementary": ReportSetSpec(subject="english", first_grade=PREP_GRADE, last_grade=4),
    "english_middle": ReportSetSpec(subject="english", first_grade=5, last_grade=8),
    "german_karne": ReportSetSpec(subject="german", first_grade=1, last_grade=8),
    "french_karne": ReportSetSpec(subject="french", first_grade=1, last_grade=8),
}
SUBJECT_LABELS = {
    "english": {"tr": "İngilizce", "en": "English", "de": "Englisch", "fr": "Anglais"},
    "german": {"tr": "Almanca", "en": "German", "de": "Deutsch", "fr": "Allemand"},
    "french": {"tr": "Fransızca", "en": "French", "de": "Französisch", "fr": "Français"},
}
SECOND_LANGUAGES = ("german", "french")


@dataclass(frozen=True)
class ReportEntry:
    """One student's card and the roster ids that place it in its class."""

    class_id: int
    student_id: int
    card: ReportCard


@dataclass(frozen=True)
class RosterStudent:
    id: int
    full_name: str
    school_number: int | None


@dataclass(frozen=True)
class RosterClass:
    id: int
    name: str
    grade_level: int
    students: list[RosterStudent]


def report_spec(kind: str) -> ReportSetSpec:
    spec = REPORT_SETS.get(kind)
    if spec is None:
        raise ValueError("unknown_report_kind")
    return spec


def report_classes_statement(spec: ReportSetSpec, year_id: int) -> Select[SchoolClass]:
    """The year's classes a report set covers, in the order the set prints them."""
    return (
        select(SchoolClass)
        .where(
            SchoolClass.year_id == year_id,
            SchoolClass.grade_level.between(spec.first_grade, spec.last_grade),
        )
        .order_by(SchoolClass.grade_level, SchoolClass.section, SchoolClass.id)
    )


def eligible_roster_filter[*Ts](
    statement: Select[*Ts], spec: ReportSetSpec, year_id: int
) -> Select[*Ts]:
    """Keep only students who get this card: a second-language card needs that language."""
    if spec.subject not in SECOND_LANGUAGES:
        return statement
    return statement.join(
        StudentLanguage,
        and_(
            StudentLanguage.student_id == Student.id,
            StudentLanguage.year_id == year_id,
            StudentLanguage.language == spec.subject,
        ),
    )


def roster_order[*Ts](statement: Select[*Ts]) -> Select[*Ts]:
    """Roster order inside a class: school number, then name."""
    return statement.order_by(
        Enrollment.class_id,
        Enrollment.school_number.asc().nulls_last(),
        Student.search_name,
        Student.id,
    )


def eligible_roster(db: Session, *, year_id: int, kind: str) -> list[RosterClass]:
    """Every class of a report set with the students who get its card, in print order.

    Two queries for the whole school; classes without an eligible student are left out
    because they produce no card.
    """
    spec = report_spec(kind)
    classes = list(db.scalars(report_classes_statement(spec, year_id)))
    if not classes:
        return []
    statement = (
        select(Enrollment.class_id, Student.id, Student.full_name, Enrollment.school_number)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.class_id.in_([item.id for item in classes]))
    )
    students: dict[int, list[RosterStudent]] = {}
    for class_id, student_id, full_name, school_number in db.execute(
        roster_order(eligible_roster_filter(statement, spec, year_id))
    ):
        students.setdefault(class_id, []).append(
            RosterStudent(id=student_id, full_name=full_name, school_number=school_number)
        )
    return [
        RosterClass(
            id=item.id,
            name=class_label(item.grade_level, item.section),
            grade_level=item.grade_level,
            students=students[item.id],
        )
        for item in classes
        if item.id in students
    ]


def pick_label(labels: dict[str, str] | None, locale: str) -> str | None:
    """Reports distinguish an absent optional label from an empty field label."""
    return field_label(labels, locale) if labels else None


def bilingual_field(
    column: ColumnDefinition, value: int | str | None, language: str
) -> ReportField:
    """A field carrying its Turkish label and the card language's label.

    The printed cards do not follow the caller's UI locale: every card is a
    fixed bilingual document (Turkish plus the subject's own language), so
    both labels come along and the template decides which side to show where.
    """
    label = pick_label(column.labels, "tr") or ""
    alt = pick_label(column.labels, language)
    group = pick_label(column.group_labels, "tr")
    group_alt = pick_label(column.group_labels, language)
    return ReportField(
        label=label,
        label_alt=alt if alt and alt != label else None,
        group=group,
        group_alt=group_alt if group_alt and group_alt != group else None,
        value_type=column.value_type,
        value=value,
    )


def score_average(columns: list[ColumnDefinition], values: dict[int, GradeValue]) -> float | None:
    scores: list[int] = []
    for column in columns:
        row = values.get(column.id)
        if column.counts_in_average and row is not None and row.score is not None:
            scores.append(row.score)
    return round(sum(scores) / len(scores), 2) if scores else None


def build_report_set(
    db: Session, *, semester_id: int, kind: str, locale: str, class_id: int | None = None
) -> list[ReportCard]:
    """Build a school or class report set with a fixed number of queries."""
    return [
        entry.card
        for entry in build_report_entries(
            db,
            semester_id=semester_id,
            kind=kind,
            locale=locale,
            class_ids=None if class_id is None else [class_id],
        )
    ]


def build_report_entries(
    db: Session,
    *,
    semester_id: int,
    kind: str,
    locale: str,
    class_ids: Collection[int] | None = None,
    student_ids: Collection[int] | None = None,
) -> list[ReportEntry]:
    """Build a report set, optionally narrowed to classes or students, in print order.

    The query count is fixed however many classes or students the set covers.
    """
    spec = report_spec(kind)

    semester = db.get(Semester, semester_id)
    if semester is None:
        raise ValueError("unknown_semester")
    year = db.get(AcademicYear, semester.year_id)
    if year is None:
        raise ValueError("unknown_year")

    class_query = report_classes_statement(spec, year.id)
    if class_ids is not None:
        class_query = class_query.where(SchoolClass.id.in_(list(class_ids)))
    if student_ids is not None:
        class_query = class_query.where(
            SchoolClass.id.in_(
                select(Enrollment.class_id).where(
                    Enrollment.year_id == year.id, Enrollment.student_id.in_(list(student_ids))
                )
            )
        )
    classes = list(db.scalars(class_query))
    if not classes:
        return []

    # The middle-school English card also shows the student's German/French
    # score columns, so those subjects ride along in the same column query.
    subjects = {spec.subject}
    if kind == "english_middle":
        subjects.update(SECOND_LANGUAGES)
    columns = list(
        db.scalars(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.subject.in_(sorted(subjects)),
                ColumnDefinition.grade_level.in_({item.grade_level for item in classes}),
                ColumnDefinition.is_active.is_(True),
            )
            .order_by(
                ColumnDefinition.grade_level,
                ColumnDefinition.position,
                ColumnDefinition.id,
            )
        )
    )
    columns_by_scope: dict[tuple[str, int], list[ColumnDefinition]] = {}
    for column in columns:
        columns_by_scope.setdefault((column.subject, column.grade_level), []).append(column)

    selected_class_ids = [school_class.id for school_class in classes]
    # One batch query, never one image/teacher query per student. Select only
    # the subject's assigned teachers; an English card includes main + skills.
    roles = ("main", "skills") if spec.subject == "english" else (spec.subject,)
    teachers_by_class: dict[int, dict[int, ReportSigner]] = {}
    for class_id, role, user_id, full_name, report_name, png in db.execute(
        select(
            TeachingAssignment.class_id,
            TeachingAssignment.role,
            User.id,
            User.full_name,
            User.report_name,
            User.signature_png,
        )
        .join(User, User.id == TeachingAssignment.user_id)
        .where(
            TeachingAssignment.class_id.in_(selected_class_ids),
            TeachingAssignment.role.in_(roles),
        )
        .order_by(TeachingAssignment.class_id, TeachingAssignment.role, User.id)
    ):
        assigned = teachers_by_class.setdefault(class_id, {})
        if user_id in assigned:
            assigned[user_id].roles.append(role)
        else:
            assigned[user_id] = ReportSigner(
                user_id=user_id,
                name=report_name or full_name,
                roles=[role],
                signature="data:image/png;base64," + base64.b64encode(png).decode("ascii")
                if png
                else None,
            )

    roster_statement = (
        select(Enrollment.class_id, Student, Enrollment.school_number)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.class_id.in_(selected_class_ids))
    )
    if student_ids is not None:
        roster_statement = roster_statement.where(Student.id.in_(list(student_ids)))
    roster_statement = roster_order(eligible_roster_filter(roster_statement, spec, year.id))

    students_by_class: dict[int, list[Student]] = {class_id: [] for class_id in selected_class_ids}
    school_numbers: dict[int, int | None] = {}
    for class_id, student, school_number in db.execute(roster_statement).all():
        students_by_class[class_id].append(student)
        school_numbers[student.id] = school_number

    students = [student for rows in students_by_class.values() for student in rows]
    roster_ids = [student.id for student in students]

    student_language: dict[int, str] = {}
    if kind == "english_middle" and roster_ids:
        student_language = {
            student_id: language
            for student_id, language in db.execute(
                select(StudentLanguage.student_id, StudentLanguage.language).where(
                    StudentLanguage.year_id == year.id,
                    StudentLanguage.student_id.in_(roster_ids),
                )
            )
        }

    column_ids = [column.id for column in columns]
    grade_values = (
        list(
            db.scalars(
                select(GradeValue).where(
                    GradeValue.student_id.in_(roster_ids),
                    GradeValue.column_definition_id.in_(column_ids),
                )
            )
        )
        if roster_ids and column_ids
        else []
    )
    values_by_student: dict[int, dict[int, GradeValue]] = {}
    for value in grade_values:
        values_by_student.setdefault(value.student_id, {})[value.column_definition_id] = value

    subject_language = SUBJECT_LOCALE[spec.subject]

    entries: list[ReportEntry] = []
    for school_class in classes:
        # Never silently omit a class because its column setup is incomplete.
        # An empty field list remains visible in the set and in completeness checks.
        class_columns = columns_by_scope.get((spec.subject, school_class.grade_level), [])
        for student in students_by_class[school_class.id]:
            student_values = values_by_student.get(student.id, {})
            fields = [
                bilingual_field(
                    column,
                    cell_value(student_values.get(column.id), column.value_type),
                    subject_language,
                )
                for column in class_columns
            ]

            language_label: str | None = None
            language_fields: list[ReportField] = []
            language = student_language.get(student.id)
            if language is not None:
                second_language = SUBJECT_LOCALE[language]
                language_label = pick_label(SUBJECT_LABELS[language], second_language)
                language_fields = [
                    bilingual_field(
                        column,
                        cell_value(student_values.get(column.id), column.value_type),
                        second_language,
                    )
                    for column in columns_by_scope.get((language, school_class.grade_level), [])
                    if column.value_type == "score"
                ]

            card = ReportCard(
                kind=kind,
                locale=locale,
                year_label=year.label,
                semester_number=semester.number,
                grade_level=school_class.grade_level,
                class_name=class_label(school_class.grade_level, school_class.section),
                school_number=school_numbers[student.id] or 0,
                student_name=student.full_name,
                subject=spec.subject,
                subject_label=pick_label(SUBJECT_LABELS[spec.subject], locale) or spec.subject,
                fields=fields,
                average=score_average(class_columns, student_values),
                language_label=language_label,
                language_fields=language_fields,
                teachers=list(teachers_by_class.get(school_class.id, {}).values()),
            )
            entries.append(ReportEntry(class_id=school_class.id, student_id=student.id, card=card))
    return entries
