from typing import Annotated

import httpx2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from flrc.config import settings
from flrc.core.rate_limit import export_rate_limit, report_rate_limit, report_single_rate_limit
from flrc.db.models import AcademicYear, SchoolClass, Semester, User
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import current_user, require_admin, require_coordinator_or_admin
from flrc.modules.jobs.router import JobOut
from flrc.modules.jobs.service import create_job, pending_jobs, publish_job
from flrc.modules.reports.branding import ReportKind
from flrc.modules.reports.builder import RosterClass, build_report_entries, eligible_roster
from flrc.modules.reports.class_sheet import (
    MAX_CLASSES,
    Locale,
    build_class_sheets,
    render_class_sheets_pdf,
)
from flrc.modules.reports.filenames import (
    SELECTED_CLASSES,
    SELECTED_STUDENTS,
    WHOLE_SCHOOL,
    class_sheet_filename,
    content_disposition,
    report_filename,
    student_scope,
)
from flrc.modules.reports.models import ReportMonthRange, report_month_range
from flrc.modules.reports.packaging import ReportFormat
from flrc.modules.reports.render import render_report_pdf
from flrc.workers.tasks.exports import export_year_job
from flrc.workers.tasks.reports import ReportJobPayload, report_set_job

router = APIRouter(tags=["reports"])

# A direct download is one class or some students of one class; classes stay well below this.
MAX_DIRECT_STUDENTS = 100
# Bounds a job request; the whole school is an empty selection, not a list of every id.
MAX_JOB_CLASSES = 200
MAX_JOB_STUDENTS = 2000
# Report jobs an account may have waiting or running at once. The single-process worker takes
# a whole school in about a minute, so the per-minute request budget (`REPORT_LIMIT`) alone
# would let one account's backlog grow without end; three covers all three card languages.
MAX_PENDING_REPORT_JOBS = 3


async def ping_worker_best_effort() -> None:
    if not settings.worker_health_url:
        return
    try:
        async with httpx2.AsyncClient(timeout=3.0) as client:
            await client.get(settings.worker_health_url)
    except httpx2.HTTPError:
        return


def pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": content_disposition(filename, inline=True),
            "X-Content-Type-Options": "nosniff",
        },
    )


def requested_period(
    kind: ReportKind, start_month: int | None, end_month: int | None
) -> ReportMonthRange | None:
    try:
        return report_month_range(kind, start_month, end_month)
    except ValueError as error:
        raise HTTPException(422, {"code": "invalid_report_period"}) from error


@router.get("/reports/pdf", dependencies=[Depends(report_single_rate_limit)])
async def download_report_set(
    _: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int,
    kind: ReportKind,
    locale: Locale = "tr",
    class_id: Annotated[int | None, Query(ge=1)] = None,
    student_id: Annotated[list[int] | None, Query(max_length=MAX_DIRECT_STUDENTS)] = None,
    start_month: Annotated[int | None, Query(ge=1, le=12)] = None,
    end_month: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> Response:
    """One class's cards, or the cards of one or more students of one class.

    Larger sets are background jobs (`POST /api/reports/jobs`, ADR-077).
    """
    period = requested_period(kind, start_month, end_month)
    if class_id is None and not student_id:
        raise HTTPException(422, {"code": "report_scope_required"})
    if class_id is not None and student_id:
        raise HTTPException(422, {"code": "report_scope_conflict"})
    if await db.get(Semester, semester_id) is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    students = set(student_id or ())
    entries = await db.run_sync(
        lambda session: build_report_entries(
            session,
            semester_id=semester_id,
            kind=kind,
            locale=locale,
            class_ids=None if class_id is None else [class_id],
            student_ids=students or None,
            report_period=period,
        )
    )
    if not entries:
        raise HTTPException(409, {"code": "empty_report_set"})
    if students and len(entries) != len(students):
        raise HTTPException(409, {"code": "student_not_in_report_set"})
    if len({entry.class_id for entry in entries}) > 1:
        raise HTTPException(422, {"code": "report_students_span_classes"})

    cards = [entry.card for entry in entries]
    first = cards[0]
    if len(students) == 1:
        scope = student_scope(first.class_name, first.school_number, first.student_name)
    elif students:
        scope = f"{first.class_name} {SELECTED_STUDENTS}"
    else:
        scope = first.class_name
    pdf = await run_in_threadpool(render_report_pdf, cards)
    return pdf_response(
        pdf, report_filename(scope, kind, first.year_label, first.semester_number, "pdf")
    )


@router.get("/reports/roster")
async def get_report_roster(
    _: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int,
    kind: ReportKind,
) -> list[RosterClass]:
    """Every class of a report set with the students who get its card, in print order.

    Second-language cards list only the students taking that language; classes without an
    eligible student are left out.
    """
    semester = await db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    return await db.run_sync(
        lambda session: eligible_roster(session, year_id=semester.year_id, kind=kind)
    )


class ReportJobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semester_id: int
    kind: ReportKind
    locale: Locale = "tr"
    format: ReportFormat
    class_ids: list[int] = Field(default_factory=list, max_length=MAX_JOB_CLASSES)
    student_ids: list[int] = Field(default_factory=list, max_length=MAX_JOB_STUDENTS)
    start_month: int | None = Field(default=None, ge=1, le=12)
    end_month: int | None = Field(default=None, ge=1, le=12)


def job_scope(body: ReportJobIn, roster: list[RosterClass]) -> str:
    if body.student_ids:
        if len(set(body.student_ids)) > 1:
            return SELECTED_STUDENTS
        (school_class,) = roster
        (student,) = school_class.students
        return student_scope(school_class.name, student.school_number, student.full_name)
    if body.class_ids:
        return roster[0].name if len(roster) == 1 else SELECTED_CLASSES
    return WHOLE_SCHOOL


@router.post("/reports/jobs", status_code=202, dependencies=[Depends(report_rate_limit)])
async def create_report_job(
    body: ReportJobIn,
    background: BackgroundTasks,
    user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> JobOut:
    """Queue a report set as a background job: the whole school, classes, or students.

    Empty `class_ids` and `student_ids` mean every eligible class. The finished file waits
    in the downloads list for 24 hours (ADR-024, ADR-077). An account with
    `MAX_PENDING_REPORT_JOBS` report jobs still waiting or running is refused with
    `report_jobs_pending` until one finishes.
    """
    if settings.env == "demo":
        raise HTTPException(422, {"code": "demo_report_class_required"})
    requested_period(body.kind, body.start_month, body.end_month)
    if body.class_ids and body.student_ids:
        raise HTTPException(422, {"code": "report_scope_conflict"})
    semester = await db.get(Semester, body.semester_id)
    if semester is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    year = await db.get(AcademicYear, semester.year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})

    class_ids = set(body.class_ids)
    if class_ids:
        found = list(
            await db.scalars(select(SchoolClass.year_id).where(SchoolClass.id.in_(class_ids)))
        )
        if len(found) != len(class_ids):
            raise HTTPException(404, {"code": "unknown_class"})
        if any(year_id != semester.year_id for year_id in found):
            raise HTTPException(409, {"code": "class_not_in_semester"})

    roster = await db.run_sync(
        lambda session: eligible_roster(session, year_id=semester.year_id, kind=body.kind)
    )
    if class_ids:
        roster = [item for item in roster if item.id in class_ids]
        if len(roster) != len(class_ids):
            raise HTTPException(409, {"code": "class_not_in_report_set"})
    students = set(body.student_ids)
    if students:
        roster = [
            RosterClass(
                id=item.id,
                name=item.name,
                grade_level=item.grade_level,
                students=[student for student in item.students if student.id in students],
            )
            for item in roster
        ]
        roster = [item for item in roster if item.students]
        if sum(len(item.students) for item in roster) != len(students):
            raise HTTPException(409, {"code": "student_not_in_report_set"})
    if not roster:
        raise HTTPException(409, {"code": "empty_report_set"})
    if await pending_jobs(db, kind="report_set", requested_by=user.id) >= MAX_PENDING_REPORT_JOBS:
        raise HTTPException(409, {"code": "report_jobs_pending"})

    payload = ReportJobPayload(
        semester_id=semester.id,
        kind=body.kind,
        locale=body.locale,
        format=body.format,
        class_ids=sorted(class_ids),
        student_ids=sorted(students),
        start_month=body.start_month,
        end_month=body.end_month,
    )
    job = await create_job(
        db,
        kind="report_set",
        requested_by=user.id,
        payload=payload.model_dump(),
        filename=report_filename(
            job_scope(body, roster),
            body.kind,
            year.label,
            semester.number,
            "pdf" if body.format == "combined" else "zip",
        ),
        total=len(roster),
    )
    await publish_job(db, job, report_set_job.delay)
    background.add_task(ping_worker_best_effort)
    return JobOut.from_model(job)


@router.get("/reports/class-sheets", dependencies=[Depends(report_single_rate_limit)])
async def download_class_sheets(
    _: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int,
    class_id: Annotated[list[int], Query(min_length=1, max_length=MAX_CLASSES)],
    locale: Locale = "tr",
) -> Response:
    """Printable middle-school English class sheets for parent meetings, one page per class.

    Any teacher may print any class (ADR-071). Classes without students are left out.
    """
    semester = await db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    sheets = [
        sheet
        for sheet in await build_class_sheets(db, semester=semester, class_ids=class_id)
        if sheet.students
    ]
    if not sheets:
        raise HTTPException(409, {"code": "empty_report_set"})
    pdf = await run_in_threadpool(render_class_sheets_pdf, sheets, locale)
    filename = class_sheet_filename(
        [sheet.class_name for sheet in sheets], sheets[0].year_label, sheets[0].semester_number
    )
    return pdf_response(pdf, filename)


@router.post("/exports/year/{year_id}", status_code=202, dependencies=[Depends(export_rate_limit)])
async def create_year_export_job(
    year_id: int,
    background: BackgroundTasks,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> JobOut:
    if await db.get(AcademicYear, year_id) is None:
        raise HTTPException(404, {"code": "unknown_year"})
    job = await create_job(
        db, kind="year_export", requested_by=user.id, payload={"year_id": year_id}
    )
    await publish_job(db, job, export_year_job.delay)
    background.add_task(ping_worker_best_effort)
    return JobOut.from_model(job)
