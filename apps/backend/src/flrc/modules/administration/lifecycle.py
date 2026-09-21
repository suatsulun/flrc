import csv
import hashlib
import hmac
import io
import re
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.core.rate_limit import export_rate_limit
from flrc.core.spreadsheets import safe_spreadsheet_cell
from flrc.db.models import (
    AcademicYear,
    AuditEntry,
    ColumnDefinition,
    Enrollment,
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
from flrc.modules.academics.programme import allows_column_type, carries_over, uses_scale_only
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin/years", tags=["admin-lifecycle"])
log = structlog.get_logger()


class SemesterOut(BaseModel):
    id: int
    number: int
    status: str


class YearOut(BaseModel):
    id: int
    label: str
    status: str
    semesters: list[SemesterOut]
    missing_school_numbers: int


class YearCreate(BaseModel):
    label: str = Field(pattern=r"^\d{4}-\d{4}$")


class ReopenBody(BaseModel):
    number: int = Field(ge=1, le=2)
    confirm_label: str


class CloseYearBody(BaseModel):
    confirm_label: str
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


async def _lock_year(db: AsyncSession, year_id: int) -> AcademicYear:
    year = await db.scalar(select(AcademicYear).where(AcademicYear.id == year_id).with_for_update())
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    return year


async def _semesters(db: AsyncSession, year_id: int) -> list[Semester]:
    return list(
        await db.scalars(
            select(Semester)
            .where(Semester.year_id == year_id)
            .order_by(Semester.number)
            .with_for_update()
        )
    )


async def _year_out(db: AsyncSession, year: AcademicYear) -> YearOut:
    semesters = list(
        await db.scalars(
            select(Semester).where(Semester.year_id == year.id).order_by(Semester.number)
        )
    )
    missing_school_numbers = (
        await db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.year_id == year.id, Enrollment.school_number.is_(None))
        )
        or 0
    )
    return YearOut(
        id=year.id,
        label=year.label,
        status=year.status,
        semesters=[
            SemesterOut(id=item.id, number=item.number, status=item.status) for item in semesters
        ],
        missing_school_numbers=missing_school_numbers,
    )


@router.get("")
async def list_years(
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[YearOut]:
    del actor
    years = list(await db.scalars(select(AcademicYear).order_by(AcademicYear.label.desc())))
    return [await _year_out(db, year) for year in years]


@router.post("", status_code=201)
async def create_year(
    body: YearCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    del actor
    label = body.label.strip()
    start, end = (int(part) for part in label.split("-"))
    if end != start + 1:
        raise HTTPException(422, {"code": "invalid_year_label"})
    if await db.scalar(select(AcademicYear.id).where(AcademicYear.label == label)) is not None:
        raise HTTPException(409, {"code": "duplicate_year"})
    year = AcademicYear(label=label, status="setup")
    db.add(year)
    await db.flush()
    db.add_all(
        [
            Semester(year_id=year.id, number=1, status="locked"),
            Semester(year_id=year.id, number=2, status="locked"),
        ]
    )
    await db.commit()
    return await _year_out(db, year)


@router.post("/{year_id}/activate")
async def activate_year(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    await db.execute(select(AcademicYear).with_for_update())
    year = await _lock_year(db, year_id)
    if year.status != "setup":
        raise HTTPException(409, {"code": "invalid_year_transition"})
    other = await db.scalar(
        select(AcademicYear.id).where(AcademicYear.status == "active", AcademicYear.id != year.id)
    )
    if other is not None:
        raise HTTPException(409, {"code": "active_year_exists"})
    semesters = await _semesters(db, year.id)
    if len(semesters) != 2:
        raise HTTPException(409, {"code": "semester_missing"})
    missing_numbers = await db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.year_id == year.id, Enrollment.school_number.is_(None))
    )
    if missing_numbers:
        raise HTTPException(
            409,
            {
                "code": "student_numbers_incomplete",
                "count": missing_numbers,
            },
        )
    year.status = "active"
    semesters[0].status = "open"
    semesters[1].status = "locked"
    await db.commit()
    return await _year_out(db, year)


@router.post("/{year_id}/advance-semester")
async def advance_semester(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    year = await _lock_year(db, year_id)
    semesters = await _semesters(db, year_id)
    if year.status != "active" or len(semesters) != 2 or semesters[0].status != "open":
        raise HTTPException(409, {"code": "invalid_semester_transition"})
    semesters[0].status = "locked"
    semesters[1].status = "open"
    await db.commit()
    return await _year_out(db, year)


@router.post("/{year_id}/lock-semester-2")
async def lock_semester_two(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    year = await _lock_year(db, year_id)
    semesters = await _semesters(db, year_id)
    if year.status != "active" or len(semesters) != 2 or semesters[1].status != "open":
        raise HTTPException(409, {"code": "invalid_semester_transition"})
    semesters[1].status = "locked"
    await db.commit()
    return await _year_out(db, year)


@router.post("/{year_id}/reopen-semester")
async def reopen_semester(
    year_id: int,
    body: ReopenBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    year = await _lock_year(db, year_id)
    if year.status != "active" or body.confirm_label != year.label:
        raise HTTPException(409, {"code": "reopen_confirmation_failed"})
    semesters = await _semesters(db, year_id)
    for semester in semesters:
        semester.status = "locked"
    await db.flush()
    selected = next((semester for semester in semesters if semester.number == body.number), None)
    if selected is None:
        raise HTTPException(409, {"code": "semester_missing"})
    selected.status = "open"
    await db.commit()
    log.info(
        "semester_reopened",
        actor_id=actor.id,
        year_id=year_id,
        semester_number=body.number,
    )
    return await _year_out(db, year)


def _value(score: int | None, scale: int | None, text_value: str | None) -> str:
    return str(next((item for item in (score, scale, text_value) if item is not None), ""))


async def _audit_payload(db: AsyncSession, year_id: int) -> bytes:
    rows = (
        await db.execute(
            select(
                AuditEntry,
                SaveBatch,
                User.email,
                User.full_name.label("actor_name"),
                Enrollment.school_number,
                Student.full_name.label("student_name"),
                ColumnDefinition,
                SchoolClass.grade_level,
                SchoolClass.section,
            )
            .join(SaveBatch, SaveBatch.id == AuditEntry.batch_id)
            .join(User, User.id == AuditEntry.actor_id)
            .join(Student, Student.id == AuditEntry.student_id)
            .join(ColumnDefinition, ColumnDefinition.id == AuditEntry.column_definition_id)
            .join(Semester, Semester.id == ColumnDefinition.semester_id)
            .join(
                Enrollment,
                (Enrollment.student_id == Student.id) & (Enrollment.year_id == Semester.year_id),
            )
            .join(SchoolClass, SchoolClass.id == SaveBatch.class_id)
            .where(Semester.year_id == year_id)
            .order_by(AuditEntry.id)
        )
    ).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "audit_id",
            "timestamp",
            "actor_email",
            "actor_name",
            "student_number",
            "student_name",
            "class",
            "subject",
            "column",
            "old",
            "new",
            "forced",
            "grant_id",
            "batch_id",
        ]
    )
    for row in rows:
        entry = row.AuditEntry
        column = row.ColumnDefinition
        writer.writerow(
            [
                safe_spreadsheet_cell(value)
                for value in [
                    entry.id,
                    entry.created_at.isoformat(),
                    row.email,
                    row.actor_name,
                    row.school_number,
                    row.student_name,
                    class_label(row.grade_level, row.section),
                    column.subject,
                    column.labels.get("tr", ""),
                    _value(entry.old_score, entry.old_scale, entry.old_text),
                    _value(entry.new_score, entry.new_scale, entry.new_text),
                    entry.forced,
                    entry.via_grant_id or "",
                    row.SaveBatch.id,
                ]
            ]
        )
    return output.getvalue().encode("utf-8")


def _next_year_label(label: str) -> str | None:
    match = re.fullmatch(r"(\d{4})-(\d{4})", label)
    if match is None:
        return None
    start, end = (int(part) for part in match.groups())
    if end != start + 1:
        return None
    return f"{end}-{end + 1}"


async def _create_rollover_year(
    db: AsyncSession,
    source: AcademicYear,
) -> AcademicYear | None:
    """Create next year's empty-number roster while preserving student identity.

    Class structure, teacher assignments, column templates, and second-language
    choices are copied. Grades and school numbers are deliberately not copied.
    Grade-eight students are left unenrolled because they have graduated, and
    Hazırlık and grade-four students wait for the school's placement into
    grade 1 and grade 5, which the roster import applies (ADR-066).
    """

    label = _next_year_label(source.label)
    if label is None:
        return None
    existing = await db.scalar(select(AcademicYear).where(AcademicYear.label == label))
    if existing is not None:
        return existing

    target = AcademicYear(label=label, status="setup")
    db.add(target)
    await db.flush()
    target_terms = {
        number: Semester(year_id=target.id, number=number, status="locked") for number in (1, 2)
    }
    db.add_all(target_terms.values())
    await db.flush()

    source_classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == source.id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    target_classes: dict[tuple[int, str], SchoolClass] = {}
    class_by_id = {item.id: item for item in source_classes}
    for item in source_classes:
        copied = SchoolClass(
            year_id=target.id,
            grade_level=item.grade_level,
            section=item.section,
        )
        db.add(copied)
        target_classes[(item.grade_level, item.section)] = copied
    await db.flush()

    if source_classes:
        assignments = list(
            await db.scalars(
                select(TeachingAssignment).where(TeachingAssignment.class_id.in_(class_by_id))
            )
        )
        for assignment in assignments:
            old_class = class_by_id[assignment.class_id]
            new_class = target_classes[(old_class.grade_level, old_class.section)]
            db.add(
                TeachingAssignment(
                    class_id=new_class.id,
                    role=assignment.role,
                    user_id=assignment.user_id,
                )
            )

    source_terms = {
        item.id: item.number
        for item in (await db.scalars(select(Semester).where(Semester.year_id == source.id)))
    }
    if source_terms:
        columns = list(
            await db.scalars(
                select(ColumnDefinition)
                .where(ColumnDefinition.semester_id.in_(source_terms))
                .order_by(ColumnDefinition.semester_id, ColumnDefinition.position)
            )
        )
        for column in columns:
            if not allows_column_type(column.grade_level, column.subject, column.value_type):
                continue
            db.add(
                ColumnDefinition(
                    semester_id=target_terms[source_terms[column.semester_id]].id,
                    grade_level=column.grade_level,
                    subject=column.subject,
                    value_type=column.value_type,
                    owner_role=column.owner_role,
                    labels=column.labels,
                    group_labels=column.group_labels,
                    counts_in_average=(
                        column.counts_in_average
                        and not uses_scale_only(column.grade_level, column.subject)
                    ),
                    position=column.position,
                    is_active=column.is_active,
                )
            )

    enrollments = list(
        await db.scalars(
            select(Enrollment)
            .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .where(Enrollment.year_id == source.id)
            .order_by(
                SchoolClass.grade_level,
                SchoolClass.section,
                Enrollment.school_number.asc().nulls_last(),
                Enrollment.student_id,
            )
        )
    )
    promoted_ids: set[int] = set()
    next_school_number = 1
    for enrollment in enrollments:
        old_class = class_by_id[enrollment.class_id]
        if not carries_over(old_class.grade_level):
            continue
        next_class = target_classes.get((old_class.grade_level + 1, old_class.section))
        if next_class is None:
            continue
        db.add(
            Enrollment(
                student_id=enrollment.student_id,
                year_id=target.id,
                class_id=next_class.id,
                school_number=next_school_number,
            )
        )
        next_school_number += 1
        promoted_ids.add(enrollment.student_id)

    if promoted_ids:
        languages = list(
            await db.scalars(
                select(StudentLanguage).where(
                    StudentLanguage.year_id == source.id,
                    StudentLanguage.student_id.in_(promoted_ids),
                )
            )
        )
        db.add_all(
            [
                StudentLanguage(
                    student_id=item.student_id,
                    year_id=target.id,
                    language=item.language,
                )
                for item in languages
            ]
        )
    return target


@router.get("/{year_id}/audit-export.csv", dependencies=[Depends(export_rate_limit)])
async def export_year_audit(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    del actor
    year = await db.get(AcademicYear, year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    payload = await _audit_payload(db, year_id)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="flrc-audit-{year.label}.csv"',
            "X-Audit-SHA256": hashlib.sha256(payload).hexdigest(),
        },
    )


@router.post("/{year_id}/close")
async def close_year(
    year_id: int,
    body: CloseYearBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> YearOut:
    year = await _lock_year(db, year_id)
    semesters = await _semesters(db, year_id)
    if year.status != "active" or any(item.status != "locked" for item in semesters):
        raise HTTPException(409, {"code": "year_not_ready_to_close"})
    if body.confirm_label != year.label:
        raise HTTPException(409, {"code": "close_confirmation_failed"})
    digest = hashlib.sha256(await _audit_payload(db, year_id)).hexdigest()
    if not hmac.compare_digest(digest, body.audit_sha256):
        raise HTTPException(409, {"code": "audit_changed_since_export"})
    year.status = "archived"
    rollover = await _create_rollover_year(db, year)
    await db.commit()
    log.info(
        "year_archived",
        actor_id=actor.id,
        year_id=year_id,
        audit_sha256=digest,
        rollover_year_id=rollover.id if rollover else None,
    )
    return await _year_out(db, year)
