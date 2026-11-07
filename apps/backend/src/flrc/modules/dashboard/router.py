"""Where the school year stands and what needs attention next (ADR-079)."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.programme import L2_START_GRADE
from flrc.modules.administration.coordinator import (
    ClassRoster,
    ColumnsByScope,
    CompletenessRow,
    OverviewOut,
    Role,
    ScopeColumn,
    Subject,
    active_columns_by_scope,
    assigned_roles,
    completeness_rows,
    scope_filled_cells,
    unassigned_roles,
    year_overview,
    year_rosters,
)
from flrc.modules.administration.lifecycle import SemesterOut
from flrc.modules.auth.dependencies import require_coordinator_or_admin
from flrc.modules.reports.builder import REPORT_SETS, SECOND_LANGUAGES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Each problem reports its full count but lists only the first items; the page links to the
# screen that lists and fixes them all.
ITEM_LIMIT = 50

NextStepCode = Literal[
    "create_year",
    "activate_year",
    "collect_grades",
    "advance_semester",
    "lock_semester",
    "close_year",
]
ReportKind = Literal["english_elementary", "english_middle", "german_karne", "french_karne"]
REPORT_KINDS: tuple[ReportKind, ...] = (
    "english_elementary",
    "english_middle",
    "german_karne",
    "french_karne",
)


class TermStatus(BaseModel):
    year_id: int | None
    year_label: str | None
    year_status: Literal["setup", "active"] | None
    # The semester the completion, readiness and field checks describe: the open one, else
    # the last locked one of an active year, else semester 1 of a year in setup.
    semester_id: int | None
    semester_number: int | None
    semester_status: Literal["open", "locked"] | None
    semesters: list[SemesterOut]


class StepBlocker(BaseModel):
    code: Literal["missing_school_numbers", "classes_without_fields"]
    count: int


class NextStep(BaseModel):
    code: NextStepCode
    semester_number: int | None
    completion_percent: float | None
    missing_cells: int | None
    # Non-empty when the step cannot be taken until these are fixed.
    blockers: list[StepBlocker]


class CompletionSummary(BaseModel):
    semester_id: int
    semester_number: int
    expected_cells: int
    filled_cells: int
    missing_cells: int
    percent: float | None
    complete_rows: int
    incomplete_rows: int
    rows: list[CompletenessRow]


class RoleGap(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    role: Role


class RoleGaps(BaseModel):
    count: int
    items: list[RoleGap]


class FieldGap(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    subject: Subject


class FieldGaps(BaseModel):
    count: int
    items: list[FieldGap]


class TeacherRef(BaseModel):
    user_id: int
    full_name: str


class TeacherGaps(BaseModel):
    count: int
    items: list[TeacherRef]


class StudentRef(BaseModel):
    student_id: int
    full_name: str
    school_number: int | None
    class_id: int
    class_name: str
    grade_level: int


class StudentGaps(BaseModel):
    count: int
    items: list[StudentRef]


class SetupProblems(BaseModel):
    # The semester whose fields were checked; None when the year has no semesters.
    semester_id: int | None
    unassigned_roles: RoleGaps
    classes_without_fields: FieldGaps
    teachers_without_report_name: TeacherGaps
    teachers_without_signature: TeacherGaps
    students_without_number: StudentGaps
    students_without_language: StudentGaps


class ReportReadiness(BaseModel):
    kind: ReportKind
    # Classes in the card's grades with at least one pupil on that card.
    eligible_classes: int
    complete_classes: int
    students: int
    expected_cells: int
    filled_cells: int
    percent: float | None


class DashboardOut(BaseModel):
    term: TermStatus
    next_step: NextStep
    overview: OverviewOut
    completion: CompletionSummary | None
    problems: SetupProblems | None
    readiness: list[ReportReadiness]


def _percent(filled: int, expected: int) -> float | None:
    """Nothing expected is not complete: a field-less grid must not read as 100 %."""
    return round(filled / expected * 100, 1) if expected else None


async def _focus_year(db: AsyncSession) -> AcademicYear | None:
    active = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active"))
    if active is not None:
        return active
    return await db.scalar(
        select(AcademicYear)
        .where(AcademicYear.status == "setup")
        .order_by(AcademicYear.label.desc())
        .limit(1)
    )


def _completion(term: Semester, rows: list[CompletenessRow]) -> CompletionSummary:
    expected = sum(row.expected_cells for row in rows)
    filled = sum(row.filled_cells for row in rows)
    return CompletionSummary(
        semester_id=term.id,
        semester_number=term.number,
        expected_cells=expected,
        filled_cells=filled,
        missing_cells=expected - filled,
        percent=_percent(filled, expected),
        complete_rows=sum(row.expected_cells > 0 and row.missing_cells == 0 for row in rows),
        # A grid with pupils but no fields has nothing to fill yet: it is not done either.
        incomplete_rows=sum(
            row.roster_count > 0 and (row.expected_cells == 0 or row.missing_cells > 0)
            for row in rows
        ),
        rows=rows,
    )


def _card_cells(
    kind: ReportKind, roster: ClassRoster, columns_by_scope: ColumnsByScope
) -> list[tuple[set[int], list[ScopeColumn]]]:
    """The (pupils, fields) groups whose values one class's cards of this kind print."""
    spec = REPORT_SETS[kind]
    grade = roster.school_class.grade_level
    cells = [(roster.subject_roster(spec.subject), columns_by_scope.get((grade, spec.subject), []))]
    if kind == "english_middle":
        # The middle-school English card also prints each pupil's own second-language score
        # fields (its DEUTSCH/FRANÇAIS block), as the report builder does.
        cells += [
            (
                roster.subject_roster(language),
                [
                    column
                    for column in columns_by_scope.get((grade, language), [])
                    if column.value_type == "score"
                ],
            )
            for language in SECOND_LANGUAGES
        ]
    return cells


def _readiness(
    rosters: list[ClassRoster],
    columns_by_scope: ColumnsByScope,
    filled_cells: set[tuple[int, int]],
) -> list[ReportReadiness]:
    result: list[ReportReadiness] = []
    for kind in REPORT_KINDS:
        spec = REPORT_SETS[kind]
        eligible = complete = students = expected = filled = 0
        for roster in rosters:
            on_card = roster.subject_roster(spec.subject)
            if not on_card or not spec.first_grade <= roster.school_class.grade_level <= (
                spec.last_grade
            ):
                continue
            eligible += 1
            students += len(on_card)
            groups = _card_cells(kind, roster, columns_by_scope)
            # Without fields of its own subject the card prints the no-fields warning: it stays
            # incomplete, whatever second-language scores it would also print.
            if not groups[0][1]:
                continue
            class_expected = sum(len(pupils) * len(columns) for pupils, columns in groups)
            class_filled = sum(
                (student_id, column.id) in filled_cells
                for pupils, columns in groups
                for student_id in pupils
                for column in columns
            )
            complete += class_expected > 0 and class_filled == class_expected
            expected += class_expected
            filled += class_filled
        result.append(
            ReportReadiness(
                kind=kind,
                eligible_classes=eligible,
                complete_classes=complete,
                students=students,
                expected_cells=expected,
                filled_cells=filled,
                percent=_percent(filled, expected),
            )
        )
    return result


async def _teacher_gaps(db: AsyncSession, year_id: int) -> tuple[TeacherGaps, TeacherGaps]:
    """Teachers printed on this year's cards whose report name or signature is missing."""
    teachers = (
        await db.execute(
            select(
                User.id,
                User.full_name,
                User.report_name,
                User.signature_png.is_(None).label("unsigned"),
            )
            .where(
                User.id.in_(
                    select(TeachingAssignment.user_id)
                    .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                    .where(SchoolClass.year_id == year_id)
                )
            )
            .order_by(User.full_name, User.id)
        )
    ).all()
    unnamed = [
        TeacherRef(user_id=row.id, full_name=row.full_name)
        for row in teachers
        if not (row.report_name or "").strip()
    ]
    unsigned = [
        TeacherRef(user_id=row.id, full_name=row.full_name) for row in teachers if row.unsigned
    ]
    return (
        TeacherGaps(count=len(unnamed), items=unnamed[:ITEM_LIMIT]),
        TeacherGaps(count=len(unsigned), items=unsigned[:ITEM_LIMIT]),
    )


async def _student_gaps(db: AsyncSession, year_id: int, *conditions: Any) -> StudentGaps:
    where = (Enrollment.year_id == year_id, *conditions)
    count = await db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
        .where(*where)
    )
    rows = (
        await db.execute(
            select(
                Student.id,
                Student.full_name,
                Enrollment.school_number,
                SchoolClass.id.label("class_id"),
                SchoolClass.grade_level,
                SchoolClass.section,
            )
            .select_from(Enrollment)
            .join(Student, Student.id == Enrollment.student_id)
            .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .where(*where)
            .order_by(SchoolClass.grade_level, SchoolClass.section, Student.search_name, Student.id)
            .limit(ITEM_LIMIT)
        )
    ).all()
    return StudentGaps(
        count=count or 0,
        items=[
            StudentRef(
                student_id=row.id,
                full_name=row.full_name,
                school_number=row.school_number,
                class_id=row.class_id,
                class_name=class_label(row.grade_level, row.section),
                grade_level=row.grade_level,
            )
            for row in rows
        ],
    )


async def _setup_problems(
    db: AsyncSession,
    year: AcademicYear,
    term: Semester | None,
    rosters: list[ClassRoster],
    assigned: set[tuple[int, str]],
    columns_by_scope: ColumnsByScope,
) -> SetupProblems:
    role_gaps = [
        RoleGap(
            class_id=roster.school_class.id,
            class_name=roster.name,
            grade_level=roster.school_class.grade_level,
            role=role,
        )
        for roster, role in unassigned_roles(rosters, assigned)
    ]
    field_gaps = [
        FieldGap(
            class_id=roster.school_class.id,
            class_name=roster.name,
            grade_level=roster.school_class.grade_level,
            subject=subject,
        )
        for roster in rosters
        for subject in roster.expected_subjects()
        if not columns_by_scope.get((roster.school_class.grade_level, subject))
    ]
    unnamed, unsigned = await _teacher_gaps(db, year.id)
    return SetupProblems(
        semester_id=term.id if term else None,
        unassigned_roles=RoleGaps(count=len(role_gaps), items=role_gaps[:ITEM_LIMIT]),
        classes_without_fields=FieldGaps(count=len(field_gaps), items=field_gaps[:ITEM_LIMIT]),
        teachers_without_report_name=unnamed,
        teachers_without_signature=unsigned,
        students_without_number=await _student_gaps(
            db, year.id, Enrollment.school_number.is_(None)
        ),
        students_without_language=await _student_gaps(
            db,
            year.id,
            SchoolClass.grade_level >= L2_START_GRADE,
            ~exists().where(
                StudentLanguage.student_id == Enrollment.student_id,
                StudentLanguage.year_id == Enrollment.year_id,
            ),
        ),
    )


def _next_step(
    year: AcademicYear,
    open_term: Semester | None,
    completion: CompletionSummary | None,
    problems: SetupProblems,
) -> NextStep:
    if year.status == "setup":
        missing_numbers = problems.students_without_number.count
        return NextStep(
            code="activate_year",
            semester_number=None,
            completion_percent=None,
            missing_cells=None,
            blockers=(
                [StepBlocker(code="missing_school_numbers", count=missing_numbers)]
                if missing_numbers
                else []
            ),
        )
    if open_term is None or completion is None:
        return NextStep(
            code="close_year",
            semester_number=None,
            completion_percent=None,
            missing_cells=None,
            blockers=[],
        )
    # Every grid with pupils must have fields and all of them filled; zero missing cells in a
    # grid without fields is not an all-clear.
    without_fields = sum(
        row.roster_count > 0 and row.expected_cells == 0 for row in completion.rows
    )
    complete = completion.complete_rows > 0 and completion.incomplete_rows == 0
    code: NextStepCode = "collect_grades"
    if complete:
        code = "advance_semester" if open_term.number == 1 else "lock_semester"
    return NextStep(
        code=code,
        semester_number=open_term.number,
        completion_percent=completion.percent,
        missing_cells=completion.missing_cells,
        blockers=(
            [StepBlocker(code="classes_without_fields", count=without_fields)]
            if without_fields
            else []
        ),
    )


@router.get("")
async def get_dashboard(
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardOut:
    """The active year (else the newest year in setup): its term, next step and open problems."""
    del actor
    year = await _focus_year(db)
    if year is None:
        return DashboardOut(
            term=TermStatus(
                year_id=None,
                year_label=None,
                year_status=None,
                semester_id=None,
                semester_number=None,
                semester_status=None,
                semesters=[],
            ),
            next_step=NextStep(
                code="create_year",
                semester_number=None,
                completion_percent=None,
                missing_cells=None,
                blockers=[],
            ),
            overview=await year_overview(db, None, [], set()),
            completion=None,
            problems=None,
            readiness=[],
        )

    semesters = list(
        await db.scalars(
            select(Semester).where(Semester.year_id == year.id).order_by(Semester.number)
        )
    )
    open_term = next((item for item in semesters if item.status == "open"), None)
    focus = open_term or (
        (semesters[-1] if year.status == "active" else semesters[0]) if semesters else None
    )
    rosters = await year_rosters(db, year.id)
    assigned = await assigned_roles(db, year.id)
    columns_by_scope = await active_columns_by_scope(db, focus.id) if focus else {}

    completion: CompletionSummary | None = None
    readiness: list[ReportReadiness] = []
    if year.status == "active" and focus is not None:
        filled_cells = await scope_filled_cells(db, columns_by_scope)
        rows = completeness_rows(rosters, columns_by_scope, filled_cells)
        completion = _completion(focus, rows)
        readiness = _readiness(rosters, columns_by_scope, filled_cells)
    problems = await _setup_problems(db, year, focus, rosters, assigned, columns_by_scope)

    return DashboardOut(
        term=TermStatus(
            year_id=year.id,
            year_label=year.label,
            year_status="active" if year.status == "active" else "setup",
            semester_id=focus.id if focus else None,
            semester_number=focus.number if focus else None,
            semester_status=(("open" if focus.status == "open" else "locked") if focus else None),
            semesters=[
                SemesterOut(id=item.id, number=item.number, status=item.status)
                for item in semesters
            ],
        ),
        next_step=_next_step(year, open_term, completion, problems),
        overview=await year_overview(db, year, rosters, assigned),
        completion=completion,
        problems=problems,
        readiness=readiness,
    )
