from dataclasses import dataclass, field
from typing import Annotated, Literal, NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    ColumnDefinition,
    Enrollment,
    GradeValue,
    OverrideGrant,
    SaveBatch,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.fields import field_name
from flrc.modules.auth.dependencies import require_coordinator_or_admin

router = APIRouter(prefix="/coordinator", tags=["coordinator"])
Subject = Literal["english", "german", "french"]
SecondLanguage = Literal["german", "french"]
Role = Literal["main", "skills", "german", "french"]
SUBJECTS: tuple[Subject, ...] = ("english", "german", "french")
SECOND_LANGUAGES: tuple[SecondLanguage, ...] = ("german", "french")
ENGLISH_ROLES: tuple[Role, ...] = ("main", "skills")


class OverviewOut(BaseModel):
    year_label: str | None
    semester_id: int | None
    semester_number: int | None
    students: int
    classes: int
    active_teachers: int
    active_grants: int
    recent_saves: int
    missing_assignments: int


class CompletenessRow(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    subject: str
    roster_count: int
    active_columns: int
    expected_cells: int
    filled_cells: int
    missing_cells: int
    percent: float


class MissingCell(BaseModel):
    student_id: int
    school_number: int | None
    student_name: str
    column_id: int
    field_name: str
    owner_role: str
    teacher_id: int | None
    teacher_name: str | None


@dataclass
class ClassRoster:
    """One class of a year with the pupils each subject's grid lists."""

    school_class: SchoolClass
    students: set[int] = field(default_factory=set)
    languages: dict[str, set[int]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return class_label(self.school_class.grade_level, self.school_class.section)

    def subject_roster(self, subject: str) -> set[int]:
        if subject == "english":
            return self.students
        return self.languages.get(subject, set())

    def expected_roles(self) -> list[Role]:
        """Roles this class needs a teacher for.

        English main and skills teach every class; a second language needs its teacher once
        the class has pupils taking it (ADR-079).
        """
        return [
            *ENGLISH_ROLES,
            *(language for language in SECOND_LANGUAGES if self.languages.get(language)),
        ]

    def expected_subjects(self) -> list[Subject]:
        return [
            "english",
            *(language for language in SECOND_LANGUAGES if self.languages.get(language)),
        ]


async def year_rosters(db: AsyncSession, year_id: int) -> list[ClassRoster]:
    classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == year_id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    rosters = {item.id: ClassRoster(item) for item in classes}
    class_of: dict[int, int] = {}
    # Only the classes read above: an import may commit a new class and its pupils in between.
    for student_id, class_id in await db.execute(
        select(Enrollment.student_id, Enrollment.class_id).where(
            Enrollment.year_id == year_id, Enrollment.class_id.in_(list(rosters))
        )
    ):
        rosters[class_id].students.add(student_id)
        class_of[student_id] = class_id
    for student_id, language in await db.execute(
        select(StudentLanguage.student_id, StudentLanguage.language).where(
            StudentLanguage.year_id == year_id
        )
    ):
        language_class = class_of.get(student_id)
        if language_class is not None:
            rosters[language_class].languages.setdefault(language, set()).add(student_id)
    return list(rosters.values())


async def assigned_roles(db: AsyncSession, year_id: int) -> set[tuple[int, str]]:
    return {
        (class_id, role)
        for class_id, role in await db.execute(
            select(TeachingAssignment.class_id, TeachingAssignment.role)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(SchoolClass.year_id == year_id)
        )
    }


def unassigned_roles(
    rosters: list[ClassRoster], assigned: set[tuple[int, str]]
) -> list[tuple[ClassRoster, Role]]:
    return [
        (roster, role)
        for roster in rosters
        for role in roster.expected_roles()
        if (roster.school_class.id, role) not in assigned
    ]


async def filled_cell_ids(
    db: AsyncSession, column_ids: list[int], student_ids: list[int] | None = None
) -> set[tuple[int, int]]:
    if not column_ids or student_ids == []:
        return set()
    # Completeness needs existence, never the potentially large comment bodies.
    statement = select(GradeValue.student_id, GradeValue.column_definition_id).where(
        GradeValue.column_definition_id.in_(column_ids),
        GradeValue.score.is_not(None)
        | GradeValue.scale.is_not(None)
        | GradeValue.text_value.is_not(None),
    )
    if student_ids is not None:
        statement = statement.where(GradeValue.student_id.in_(student_ids))
    return {(student_id, column_id) for student_id, column_id in await db.execute(statement)}


class ScopeColumn(NamedTuple):
    id: int
    value_type: str


ColumnsByScope = dict[tuple[int, str], list[ScopeColumn]]


async def active_columns_by_scope(db: AsyncSession, semester_id: int) -> ColumnsByScope:
    """A semester's active fields per (grade level, subject)."""
    columns_by_scope: ColumnsByScope = {}
    for column_id, grade_level, subject, value_type in await db.execute(
        select(
            ColumnDefinition.id,
            ColumnDefinition.grade_level,
            ColumnDefinition.subject,
            ColumnDefinition.value_type,
        ).where(
            ColumnDefinition.semester_id == semester_id,
            ColumnDefinition.is_active.is_(True),
        )
    ):
        columns_by_scope.setdefault((grade_level, subject), []).append(
            ScopeColumn(column_id, value_type)
        )
    return columns_by_scope


async def scope_filled_cells(
    db: AsyncSession, columns_by_scope: ColumnsByScope
) -> set[tuple[int, int]]:
    return await filled_cell_ids(
        db, [column.id for columns in columns_by_scope.values() for column in columns]
    )


def completeness_rows(
    rosters: list[ClassRoster],
    columns_by_scope: ColumnsByScope,
    filled_cells: set[tuple[int, int]],
) -> list[CompletenessRow]:
    result: list[CompletenessRow] = []
    for roster in rosters:
        school_class = roster.school_class
        for subject in SUBJECTS:
            students = roster.subject_roster(subject)
            subject_columns = columns_by_scope.get((school_class.grade_level, subject), [])
            expected = len(students) * len(subject_columns)
            filled = sum(
                (student_id, column.id) in filled_cells
                for student_id in students
                for column in subject_columns
            )
            result.append(
                CompletenessRow(
                    class_id=school_class.id,
                    class_name=roster.name,
                    grade_level=school_class.grade_level,
                    subject=subject,
                    roster_count=len(students),
                    active_columns=len(subject_columns),
                    expected_cells=expected,
                    filled_cells=filled,
                    missing_cells=expected - filled,
                    percent=round((filled / expected * 100) if expected else 100.0, 1),
                )
            )
    return result


async def year_overview(
    db: AsyncSession,
    year: AcademicYear | None,
    rosters: list[ClassRoster],
    assigned: set[tuple[int, str]],
) -> OverviewOut:
    term = (
        await db.scalar(
            select(Semester).where(Semester.year_id == year.id, Semester.status == "open")
        )
        if year
        else None
    )
    return OverviewOut(
        year_label=year.label if year else None,
        semester_id=term.id if term else None,
        semester_number=term.number if term else None,
        students=sum(len(roster.students) for roster in rosters),
        classes=len(rosters),
        active_teachers=(
            await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)))
            or 0
        ),
        active_grants=(
            await db.scalar(
                select(func.count())
                .select_from(OverrideGrant)
                .where(OverrideGrant.expires_at > func.now())
            )
            or 0
        ),
        recent_saves=(
            await db.scalar(
                select(func.count())
                .select_from(SaveBatch)
                .where(SaveBatch.created_at > func.now() - func.make_interval(0, 0, 0, 1))
            )
            or 0
        ),
        missing_assignments=len(unassigned_roles(rosters, assigned)),
    )


@router.get("/overview")
async def coordinator_overview(
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OverviewOut:
    del actor
    year = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active"))
    rosters = await year_rosters(db, year.id) if year else []
    assigned = await assigned_roles(db, year.id) if year else set()
    return await year_overview(db, year, rosters, assigned)


@router.get("/completeness")
async def coordinator_completeness(
    semester_id: int,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[CompletenessRow]:
    del actor
    term = await db.get(Semester, semester_id)
    if term is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    rosters = await year_rosters(db, term.year_id)
    columns_by_scope = await active_columns_by_scope(db, term.id)
    return completeness_rows(
        rosters, columns_by_scope, await scope_filled_cells(db, columns_by_scope)
    )


@router.get("/classes/{class_id}/missing")
async def coordinator_missing_cells(
    class_id: int,
    subject: Subject,
    semester_id: int,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[MissingCell]:
    """Every empty cell of one class grid: the pupil, the field and the teacher who owns it."""
    del actor
    term = await db.get(Semester, semester_id)
    school_class = await db.get(SchoolClass, class_id)
    if term is None or school_class is None or school_class.year_id != term.year_id:
        raise HTTPException(404, {"code": "unknown_class"})
    roster_query = (
        select(Student.id, Student.full_name, Enrollment.school_number)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == class_id)
        .order_by(Enrollment.school_number.asc().nulls_last(), Student.search_name, Student.id)
    )
    if subject in SECOND_LANGUAGES:
        roster_query = roster_query.join(
            StudentLanguage,
            (StudentLanguage.student_id == Enrollment.student_id)
            & (StudentLanguage.year_id == term.year_id),
        ).where(StudentLanguage.language == subject)
    students = (await db.execute(roster_query)).all()
    columns = list(
        await db.scalars(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == semester_id,
                ColumnDefinition.grade_level == school_class.grade_level,
                ColumnDefinition.subject == subject,
                ColumnDefinition.is_active.is_(True),
            )
            .order_by(ColumnDefinition.position, ColumnDefinition.id)
        )
    )
    if not students or not columns:
        return []
    teachers = {
        role: (user_id, full_name)
        for role, user_id, full_name in await db.execute(
            select(TeachingAssignment.role, User.id, User.full_name)
            .join(User, User.id == TeachingAssignment.user_id)
            .where(TeachingAssignment.class_id == class_id)
        )
    }
    filled = await filled_cell_ids(
        db, [column.id for column in columns], [student.id for student in students]
    )
    result: list[MissingCell] = []
    for student in students:
        for column in columns:
            if (student.id, column.id) in filled:
                continue
            teacher_id, teacher_name = teachers.get(column.owner_role, (None, None))
            result.append(
                MissingCell(
                    student_id=student.id,
                    school_number=student.school_number,
                    student_name=student.full_name,
                    column_id=column.id,
                    field_name=field_name(column.labels, column.subject),
                    owner_role=column.owner_role,
                    teacher_id=teacher_id,
                    teacher_name=teacher_name,
                )
            )
    return result
