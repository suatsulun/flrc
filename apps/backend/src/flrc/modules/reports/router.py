from typing import Annotated, Literal

import httpx2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from flrc.config import settings
from flrc.db.models import AcademicYear, Semester, User
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import require_admin, require_coordinator_or_admin
from flrc.modules.jobs.router import JobOut
from flrc.modules.jobs.service import create_job
from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.render import render_report_pdf
from flrc.workers.tasks.exports import export_year_job

router = APIRouter(tags=["reports"])


async def ping_worker_best_effort() -> None:
    if not settings.worker_health_url:
        return
    try:
        async with httpx2.AsyncClient(timeout=3.0) as client:
            await client.get(settings.worker_health_url)
    except httpx2.HTTPError:
        return


@router.get("/reports/pdf")
async def download_report_set(
    _: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int,
    kind: Literal["english_elementary", "english_middle", "german_karne", "french_karne"],
    locale: Literal["tr", "en", "de", "fr"] = "tr",
) -> Response:
    semester = await db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    cards = await db.run_sync(
        lambda session: build_report_set(
            session,
            semester_id=semester_id,
            kind=kind,
            locale=locale,
        )
    )
    if not cards:
        raise HTTPException(409, {"code": "empty_report_set"})
    pdf = await run_in_threadpool(render_report_pdf, cards)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{kind}-s{semester_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/exports/year/{year_id}", status_code=202)
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
    export_year_job.delay(job.id)
    background.add_task(ping_worker_best_effort)
    return JobOut.from_model(job)
