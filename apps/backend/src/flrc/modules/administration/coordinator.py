from typing import Annotated, Literal

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
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import require_coordinator_or_admin

router = APIRouter(prefix="/coordinator", tags=["coordinator"])
Subject = Literal["english", "german", "french"]


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
    subject: str
    roster_count: int
    active_columns: int
    expected_cells: int
    filled_cells: int
    missing_cells: int
    percent: float


@router.get("/overview")
async def coordinator_overview(
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> OverviewOut:
    del actor
    year = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active"))
    term = (
        await db.scalar(
            select(Semester).where(Semester.year_id == year.id, Semester.status == "open")
        )
        if year
        else None
    )
    class_count = (
        await db.scalar(
            select(func.count()).select_from(SchoolClass).where(SchoolClass.year_id == year.id)
        )
        if year
        else 0
    ) or 0
    student_count = (
        await db.scalar(
            select(func.count()).select_from(Enrollment).where(Enrollment.year_id == year.id)
        )
        if year
        else 0
    ) or 0
    assignments = (
        await db.scalar(
            select(func.count())
            .select_from(TeachingAssignment)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(SchoolClass.year_id == year.id)
        )
        if year
        else 0
    ) or 0
    return OverviewOut(
        year_label=year.label if year else None,
        semester_id=term.id if term else None,
        semester_number=term.number if term else None,
        students=student_count,
        classes=class_count,
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
        missing_assignments=max(0, class_count * 4 - assignments),
    )


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
    classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == term.year_id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    enrollments = list(
        await db.scalars(select(Enrollment).where(Enrollment.year_id == term.year_id))
    )
    languages = {
        (item.student_id, item.language)
        for item in (
            await db.scalars(select(StudentLanguage).where(StudentLanguage.year_id == term.year_id))
        )
    }
    columns = list(
        await db.scalars(
            select(ColumnDefinition).where(
                ColumnDefinition.semester_id == term.id,
                ColumnDefinition.is_active.is_(True),
            )
        )
    )
    grades = (
        list(
            await db.scalars(
                select(GradeValue).where(
                    GradeValue.column_definition_id.in_([column.id for column in columns])
                )
            )
        )
        if columns
        else []
    )
    roster_by_class: dict[int, set[int]] = {}
    for enrollment in enrollments:
        roster_by_class.setdefault(enrollment.class_id, set()).add(enrollment.student_id)
    grade_map = {(grade.student_id, grade.column_definition_id): grade for grade in grades}
    result: list[CompletenessRow] = []
    for school_class in classes:
        base_roster = roster_by_class.get(school_class.id, set())
        for subject in ("english", "german", "french"):
            roster = (
                base_roster
                if subject == "english"
                else {student for student in base_roster if (student, subject) in languages}
            )
            subject_columns = [
                column
                for column in columns
                if column.grade_level == school_class.grade_level and column.subject == subject
            ]
            expected = len(roster) * len(subject_columns)
            filled = 0
            for student_id in roster:
                for column in subject_columns:
                    grade = grade_map.get((student_id, column.id))
                    if grade is not None and any(
                        value is not None for value in (grade.score, grade.scale, grade.text_value)
                    ):
                        filled += 1
            result.append(
                CompletenessRow(
                    class_id=school_class.id,
                    class_name=f"{school_class.grade_level}/{school_class.section}",
                    subject=subject,
                    roster_count=len(roster),
                    active_columns=len(subject_columns),
                    expected_cells=expected,
                    filled_cells=filled,
                    missing_cells=expected - filled,
                    percent=round((filled / expected * 100) if expected else 100.0, 1),
                )
            )
    return result


@router.get("/classes/{class_id}/missing")
async def coordinator_missing_cells(
    class_id: int,
    subject: Subject,
    semester_id: int,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, int]]:
    del actor
    term = await db.get(Semester, semester_id)
    school_class = await db.get(SchoolClass, class_id)
    if term is None or school_class is None or school_class.year_id != term.year_id:
        raise HTTPException(404, {"code": "unknown_class"})
    roster_query = select(Enrollment.student_id).where(Enrollment.class_id == class_id)
    if subject in {"german", "french"}:
        roster_query = roster_query.join(
            StudentLanguage,
            (StudentLanguage.student_id == Enrollment.student_id)
            & (StudentLanguage.year_id == term.year_id),
        ).where(StudentLanguage.language == subject)
    student_ids = list(await db.scalars(roster_query))
    column_ids = list(
        await db.scalars(
            select(ColumnDefinition.id).where(
                ColumnDefinition.semester_id == semester_id,
                ColumnDefinition.grade_level == school_class.grade_level,
                ColumnDefinition.subject == subject,
                ColumnDefinition.is_active.is_(True),
            )
        )
    )
    if not student_ids or not column_ids:
        return []
    filled = set(
        (
            await db.execute(
                select(GradeValue.student_id, GradeValue.column_definition_id).where(
                    GradeValue.student_id.in_(student_ids),
                    GradeValue.column_definition_id.in_(column_ids),
                    (
                        GradeValue.score.is_not(None)
                        | GradeValue.scale.is_not(None)
                        | GradeValue.text_value.is_not(None)
                    ),
                )
            )
        ).tuples()
    )
    return [
        {"student_id": student_id, "column_id": column_id}
        for student_id in student_ids
        for column_id in column_ids
        if (student_id, column_id) not in filled
    ]
