"""Class sheets: one page per middle-school English class for parent-teacher meetings.

A sheet lists every student of a grade 5-8 class with each active English field
of the semester. Middle-school English has no written notes (ADR-063), so the
sheet is one row per student, sized so a whole class prints on a single A4 page.
One builder feeds both the teacher app's preview and the printable PDF, so the
screen and the paper agree on columns and order.

Reads follow ADR-071: any signed-in teacher may read any class, exactly as the
grade grid does. The PDF route lives in the reports router and shares its
per-account rate limit; the preview is as cheap as a grid read and is not limited.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, tzinfo
from itertools import groupby
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.config import settings
from flrc.db.models import (
    AcademicYear,
    ColumnDefinition,
    Enrollment,
    GradeValue,
    SchoolClass,
    Semester,
    Student,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.fields import cell_value, field_name
from flrc.modules.academics.programme import stage_for_grade
from flrc.modules.auth.dependencies import current_user
from flrc.modules.grades.router import grid_semester
from flrc.modules.reports.render import env, render_pdf_document, school_brand

router = APIRouter(tags=["class-sheets"])

Locale = Literal["tr", "en", "de", "fr"]

# "All my classes" covers one teacher's classes; this bounds a single request's work.
MAX_CLASSES = 40
ROLE_ORDER = {"main": 0, "skills": 1}

# One class must fit one A4 landscape page. The template's margins leave 188 mm; the title
# block takes about 17 mm and the field headings at most 12 mm (clipped at three lines).
# Rows share what remains, less the one-line group row and the rating legend when present,
# with about 15 mm kept in reserve.
ROW_SPACE_MM = 144.0
GROUP_ROW_MM = 5.0
SCALE_LEGEND_MM = 6.0
ROW_MAX_MM = 7.5
# 34 students still fit at this height; a larger class continues on a second page.
ROW_MIN_MM = 4.2


class ClassSheetColumnOut(BaseModel):
    id: int
    label: str
    group: str | None
    value_type: Literal["score", "scale3"]


class ClassSheetStudentOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    # One entry per sheet column, in column order.
    values: list[int | None]


class ClassSheetOut(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    year_id: int
    year_label: str
    semester_id: int
    semester_number: int
    teachers: list[str]
    columns: list[ClassSheetColumnOut]
    students: list[ClassSheetStudentOut]


async def build_class_sheets(
    db: AsyncSession, *, semester: Semester, class_ids: Sequence[int]
) -> list[ClassSheetOut]:
    """Build one English sheet per class with a fixed number of queries, in request order."""
    classes = {
        item.id: item
        for item in await db.scalars(select(SchoolClass).where(SchoolClass.id.in_(class_ids)))
    }
    if len(classes) != len(set(class_ids)):
        raise HTTPException(404, {"code": "unknown_class"})
    if any(stage_for_grade(item.grade_level) != "middle" for item in classes.values()):
        raise HTTPException(409, {"code": "class_report_middle_english_only"})
    if any(item.year_id != semester.year_id for item in classes.values()):
        raise HTTPException(409, {"code": "class_not_in_semester"})
    year = await db.get(AcademicYear, semester.year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})

    columns = list(
        await db.scalars(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.subject == "english",
                ColumnDefinition.grade_level.in_({item.grade_level for item in classes.values()}),
                ColumnDefinition.is_active.is_(True),
                # ADR-063 retired middle-school English notes; none may reach the page.
                ColumnDefinition.value_type != "text",
            )
            .order_by(ColumnDefinition.position, ColumnDefinition.id)
        )
    )
    columns_by_grade: dict[int, list[ColumnDefinition]] = {}
    for column in columns:
        columns_by_grade.setdefault(column.grade_level, []).append(column)

    assignments = (
        await db.execute(
            select(TeachingAssignment.class_id, TeachingAssignment.role, User.full_name)
            .join(User, User.id == TeachingAssignment.user_id)
            .where(
                TeachingAssignment.class_id.in_(class_ids),
                TeachingAssignment.role.in_(tuple(ROLE_ORDER)),
            )
        )
    ).all()

    roster = (
        await db.execute(
            select(Enrollment.class_id, Student.id, Student.full_name, Enrollment.school_number)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.class_id.in_(class_ids))
            .order_by(Enrollment.school_number.asc().nulls_last(), Student.search_name)
        )
    ).all()

    student_ids = {row.id for row in roster}
    values = (
        {
            (grade.student_id, grade.column_definition_id): grade
            for grade in await db.scalars(
                select(GradeValue).where(
                    GradeValue.column_definition_id.in_([column.id for column in columns]),
                    GradeValue.student_id.in_(student_ids),
                )
            )
        }
        if columns and student_ids
        else {}
    )

    sheets: list[ClassSheetOut] = []
    for class_id in dict.fromkeys(class_ids):
        school_class = classes[class_id]
        class_columns = columns_by_grade.get(school_class.grade_level, [])
        teachers: list[str] = []
        for assignment in sorted(
            (item for item in assignments if item.class_id == class_id),
            key=lambda item: (ROLE_ORDER[item.role], item.full_name),
        ):
            if assignment.full_name not in teachers:
                teachers.append(assignment.full_name)
        students: list[ClassSheetStudentOut] = []
        for row in roster:
            if row.class_id != class_id:
                continue
            row_values: list[int | None] = []
            for column in class_columns:
                value = cell_value(values.get((row.id, column.id)), column.value_type)
                row_values.append(value if isinstance(value, int) else None)
            students.append(
                ClassSheetStudentOut(
                    student_id=row.id,
                    school_number=row.school_number,
                    full_name=row.full_name,
                    values=row_values,
                )
            )
        sheets.append(
            ClassSheetOut(
                class_id=class_id,
                class_name=class_label(school_class.grade_level, school_class.section),
                grade_level=school_class.grade_level,
                year_id=year.id,
                year_label=year.label,
                semester_id=semester.id,
                semester_number=semester.number,
                teachers=teachers,
                columns=[
                    ClassSheetColumnOut(
                        id=column.id,
                        label=field_name(column.labels, column.subject),
                        group=(
                            field_name(column.group_labels, column.subject)
                            if column.group_labels
                            else None
                        ),
                        value_type="scale3" if column.value_type == "scale3" else "score",
                    )
                    for column in class_columns
                ],
                students=students,
            )
        )
    return sheets


@router.get("/classes/{class_id}/sheet")
async def get_class_sheet(
    class_id: int,
    _: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester: int | None = None,
) -> ClassSheetOut:
    """The class report preview; semester selection matches the grade grid."""
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    term = await grid_semester(db, school_class.year_id, semester)
    (sheet,) = await build_class_sheets(db, semester=term, class_ids=[class_id])
    return sheet


# Printed wording. Field labels come from the data in English (ADR-072); everything
# else on the page follows the teacher's interface language.
PRINT_TEXT: dict[str, dict[str, str]] = {
    "tr": {
        "title": "Sınıf Raporu",
        "subject": "İngilizce",
        "number": "No",
        "student": "Öğrenci",
        "teacher": "Öğretmen",
        "teachers": "Öğretmenler",
        "semester": "{number}. dönem",
        "students": "{count} öğrenci",
        "rating": "Değerlendirme",
        "printed": "Yazdırma tarihi",
        "date": "%d.%m.%Y",
        "notice": "Öğretmen nüshası: sınıftaki tüm öğrencilerin bilgilerini içerir.",
        "scale1": "Geliştirilmeli",
        "scale2": "İyi",
        "scale3": "Çok iyi",
    },
    "en": {
        "title": "Class Report",
        "subject": "English",
        "number": "No.",
        "student": "Student",
        "teacher": "Teacher",
        "teachers": "Teachers",
        "semester": "Semester {number}",
        "students": "{count} students",
        "rating": "Rating",
        "printed": "Printed",
        "date": "%Y-%m-%d",
        "notice": "Teacher's copy: lists every student in the class.",
        "scale1": "Needs improvement",
        "scale2": "Good",
        "scale3": "Very good",
    },
    "de": {
        "title": "Klassenbericht",
        "subject": "Englisch",
        "number": "Nr.",
        "student": "Schüler/in",
        "teacher": "Lehrkraft",
        "teachers": "Lehrkräfte",
        "semester": "{number}. Halbjahr",
        "students": "{count} Schüler/innen",
        "rating": "Bewertung",
        "printed": "Gedruckt am",
        "date": "%d.%m.%Y",
        "notice": "Exemplar der Lehrkraft: enthält alle Schüler/innen der Klasse.",
        "scale1": "Aufbaufähig",
        "scale2": "Gut",
        "scale3": "Sehr gut",
    },
    "fr": {
        "title": "Rapport de classe",
        "subject": "Anglais",
        "number": "N°",
        "student": "Élève",
        "teacher": "Enseignant·e",
        "teachers": "Enseignant·es",
        "semester": "Semestre {number}",
        "students": "{count} élèves",
        "rating": "Évaluation",
        "printed": "Imprimé le",
        "date": "%d/%m/%Y",
        "notice": "Exemplaire de l’enseignant·e : contient tous les élèves de la classe.",
        "scale1": "À développer",
        "scale2": "Bien",
        "scale3": "Très bien",
    },
}


def row_height_mm(students: int, *, groups: bool, scale: bool) -> float:
    """The row height that fits the whole class on the page, within readable bounds."""
    space = ROW_SPACE_MM - (GROUP_ROW_MM if groups else 0) - (SCALE_LEGEND_MM if scale else 0)
    return round(min(ROW_MAX_MM, max(ROW_MIN_MM, space / max(students, 1))), 2)


def _page(sheet: ClassSheetOut, text: dict[str, str]) -> dict[str, object]:
    """Arrange one sheet for the template: heading spans, legend and row height."""
    group_spans = [
        (group, len(list(run))) for group, run in groupby(column.group for column in sheet.columns)
    ]
    has_groups = any(group for group, _ in group_spans)
    has_scale = any(column.value_type == "scale3" for column in sheet.columns)
    row_mm = row_height_mm(len(sheet.students), groups=has_groups, scale=has_scale)
    teachers_label = text["teacher"] if len(sheet.teachers) == 1 else text["teachers"]
    return {
        "heading": f"{sheet.class_name} · {text['subject']}",
        "context": " · ".join(
            [
                sheet.year_label,
                text["semester"].format(number=sheet.semester_number),
                text["students"].format(count=len(sheet.students)),
            ]
        ),
        "teachers": (f"{teachers_label}: {', '.join(sheet.teachers)}" if sheet.teachers else None),
        "columns": sheet.columns,
        "group_spans": group_spans if has_groups else [],
        "students": sheet.students,
        "has_scale": has_scale,
        "row_mm": row_mm,
        # Shrink the type with the row, so a full class stays on one page.
        "font_pt": 9 if row_mm >= 5.6 else 8 if row_mm >= 4.8 else 7.5,
    }


def _school_zone() -> tzinfo:
    """The school's local time zone, the one its nightly backups are scheduled in."""
    try:
        return ZoneInfo(settings.backup_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def render_class_sheets_html(sheets: Sequence[ClassSheetOut], locale: Locale) -> str:
    text = PRINT_TEXT[locale]
    first = sheets[0]
    return env.get_template("class_sheet.html").render(
        locale=locale,
        text=text,
        school=school_brand(),
        title=(
            f"{text['title']} · {first.class_name} · {text['subject']}"
            if len(sheets) == 1
            else f"{text['title']} · {text['subject']} · {first.year_label}"
        ),
        printed_on=datetime.now(_school_zone()).strftime(text["date"]),
        pages=[_page(sheet, text) for sheet in sheets],
    )


def render_class_sheets_pdf(sheets: Sequence[ClassSheetOut], locale: Locale) -> bytes:
    if not sheets:
        raise ValueError("empty_report_set")
    return render_pdf_document(render_class_sheets_html(sheets, locale))
