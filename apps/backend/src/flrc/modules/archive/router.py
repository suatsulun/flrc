from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    ColumnDefinition,
    Enrollment,
    GradeValue,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.fields import cell_value, pick_label
from flrc.modules.academics.programme import has_teacher_comments
from flrc.modules.auth.dependencies import require_coordinator_or_admin

router = APIRouter(prefix="/archive", tags=["archive"])
Subject = Literal["english", "german", "french"]


class ArchiveYearOut(BaseModel):
    id: int
    label: str
    status: str


class ArchiveClassOut(BaseModel):
    id: int
    name: str
    grade_level: int


class ArchiveColumnOut(BaseModel):
    id: int
    label: str
    value_type: str


class ArchiveRowOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    cells: dict[str, int | str | None]


class ArchiveGridOut(BaseModel):
    class_name: str
    semester: int
    subject: str
    columns: list[ArchiveColumnOut]
    rows: list[ArchiveRowOut]


class HistoryCell(BaseModel):
    column_id: int
    label: str
    subject: str
    value_type: str
    value: int | str | None


class HistorySemester(BaseModel):
    number: int
    status: str
    cells: list[HistoryCell]


class HistoryYear(BaseModel):
    year_id: int
    label: str
    year_status: str
    school_number: int | None
    class_name: str | None
    language: str | None
    semesters: list[HistorySemester]


class StudentHistoryOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    years: list[HistoryYear]


@router.get("/years")
async def list_archive_years(
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ArchiveYearOut]:
    del actor
    years = list(
        await db.scalars(
            select(AcademicYear)
            .where(AcademicYear.status == "archived")
            .order_by(AcademicYear.label.desc())
        )
    )
    return [ArchiveYearOut(id=year.id, label=year.label, status=year.status) for year in years]


@router.get("/years/{year_id}/classes")
async def list_archive_classes(
    year_id: int,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ArchiveClassOut]:
    del actor
    classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == year_id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    return [
        ArchiveClassOut(
            id=item.id,
            name=f"{item.grade_level}/{item.section}",
            grade_level=item.grade_level,
        )
        for item in classes
    ]


@router.get("/classes/{class_id}/grid")
async def get_archive_grid(
    class_id: int,
    semester: int,
    subject: Subject,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    locale: str = "tr",
) -> ArchiveGridOut:
    del actor
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    term = await db.scalar(
        select(Semester).where(
            Semester.year_id == school_class.year_id, Semester.number == semester
        )
    )
    if term is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    columns = list(
        await db.scalars(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == term.id,
                ColumnDefinition.grade_level == school_class.grade_level,
                ColumnDefinition.subject == subject,
            )
            .order_by(ColumnDefinition.position)
        )
    )
    columns = [
        c
        for c in columns
        if c.value_type != "text" or has_teacher_comments(c.grade_level, c.subject)
    ]
    roster_rows = list(
        (
            await db.execute(
                select(Student, Enrollment.school_number)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .where(Enrollment.class_id == class_id)
                .order_by(Enrollment.school_number.asc().nulls_last(), Student.search_name)
            )
        ).all()
    )
    if subject in ("german", "french"):
        allowed = set(
            await db.scalars(
                select(StudentLanguage.student_id).where(
                    StudentLanguage.year_id == school_class.year_id,
                    StudentLanguage.language == subject,
                )
            )
        )
        roster_rows = [row for row in roster_rows if row[0].id in allowed]
    roster = [student for student, _school_number in roster_rows]
    values = (
        list(
            await db.scalars(
                select(GradeValue).where(
                    GradeValue.student_id.in_([student.id for student in roster]),
                    GradeValue.column_definition_id.in_([column.id for column in columns]),
                )
            )
        )
        if roster and columns
        else []
    )
    value_map = {(value.student_id, value.column_definition_id): value for value in values}
    return ArchiveGridOut(
        class_name=f"{school_class.grade_level}/{school_class.section}",
        semester=semester,
        subject=subject,
        columns=[
            ArchiveColumnOut(
                id=column.id,
                label=pick_label(column.labels, locale),
                value_type=column.value_type,
            )
            for column in columns
        ],
        rows=[
            ArchiveRowOut(
                student_id=student.id,
                school_number=school_number,
                full_name=student.full_name,
                cells={
                    str(column.id): cell_value(
                        value_map[(student.id, column.id)], column.value_type
                    )
                    for column in columns
                    if (student.id, column.id) in value_map
                },
            )
            for student, school_number in roster_rows
        ],
    )


@router.get("/students/{student_id}/history")
async def get_student_history(
    student_id: int,
    actor: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StudentHistoryOut:
    del actor
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(404, {"code": "unknown_student"})
    enrollments = (
        await db.execute(
            select(Enrollment, SchoolClass, AcademicYear)
            .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .join(AcademicYear, AcademicYear.id == Enrollment.year_id)
            .where(Enrollment.student_id == student_id)
            .order_by(AcademicYear.label)
        )
    ).all()
    languages = {
        item.year_id: item.language
        for item in (
            await db.scalars(
                select(StudentLanguage).where(StudentLanguage.student_id == student_id)
            )
        )
    }
    grade_rows = (
        await db.execute(
            select(GradeValue, ColumnDefinition, Semester)
            .join(
                ColumnDefinition,
                ColumnDefinition.id == GradeValue.column_definition_id,
            )
            .join(Semester, Semester.id == ColumnDefinition.semester_id)
            .where(GradeValue.student_id == student_id)
            .order_by(Semester.year_id, Semester.number, ColumnDefinition.position)
        )
    ).all()
    cells_by_term: dict[int, list[HistoryCell]] = {}
    terms: dict[int, Semester] = {}
    for grade, column, term in grade_rows:
        if column.value_type == "text" and not has_teacher_comments(
            column.grade_level, column.subject
        ):
            continue
        terms[term.id] = term
        cells_by_term.setdefault(term.id, []).append(
            HistoryCell(
                column_id=column.id,
                label=pick_label(column.labels, "tr"),
                subject=column.subject,
                value_type=column.value_type,
                value=cell_value(grade, column.value_type),
            )
        )
    years: list[HistoryYear] = []
    for enrollment, school_class, year in enrollments:
        year_terms = [term for term in terms.values() if term.year_id == year.id]
        if not year_terms:
            year_terms = list(
                await db.scalars(
                    select(Semester).where(Semester.year_id == year.id).order_by(Semester.number)
                )
            )
        years.append(
            HistoryYear(
                year_id=year.id,
                label=year.label,
                year_status=year.status,
                school_number=enrollment.school_number,
                class_name=f"{school_class.grade_level}/{school_class.section}",
                language=languages.get(year.id),
                semesters=[
                    HistorySemester(
                        number=term.number,
                        status=term.status,
                        cells=cells_by_term.get(term.id, []),
                    )
                    for term in sorted(year_terms, key=lambda item: item.number)
                ],
            )
        )
    return StudentHistoryOut(
        student_id=student.id,
        school_number=enrollments[-1][0].school_number if enrollments else None,
        full_name=student.full_name,
        years=years,
    )
