from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from flrc.db.models import JobRun, User
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import current_user

router = APIRouter(tags=["jobs"])


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: int
    total: int
    output_filename: str | None
    output_size: int | None
    output_expires_at: datetime | None
    error_code: str | None

    @classmethod
    def from_model(cls, job: JobRun) -> "JobOut":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            progress=job.progress,
            total=job.total,
            output_filename=job.output_filename,
            output_size=job.output_size,
            output_expires_at=job.output_expires_at,
            error_code=job.error_code,
        )


def may_read_job(user: User, job: JobRun) -> bool:
    if user.is_admin or job.requested_by == user.id:
        return True
    return user.is_coordinator and job.kind != "year_export"


def safe_download_name(value: str | None) -> str:
    return (value or "download.bin").replace("\r", "").replace("\n", "").replace('"', "_")


@router.get("/jobs")
async def list_jobs(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=25, ge=1, le=100),
) -> list[JobOut]:
    statement = select(JobRun).order_by(JobRun.id.desc()).limit(limit)
    if not user.is_admin:
        statement = (
            statement.where(JobRun.kind != "year_export")
            if user.is_coordinator
            else statement.where(JobRun.requested_by == user.id)
        )
    jobs = list(await db.scalars(statement))
    return [JobOut.from_model(job) for job in jobs]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> JobOut:
    job = await db.get(JobRun, job_id)
    if job is None:
        raise HTTPException(404, {"code": "unknown_job"})
    if not may_read_job(user, job):
        raise HTTPException(403, {"code": "forbidden"})
    if job.status == "queued":
        from flrc.modules.reports.router import ping_worker_best_effort

        background.add_task(ping_worker_best_effort)
    return JobOut.from_model(job)


@router.get("/jobs/{job_id}/download")
async def download_job(
    job_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await db.scalar(
        select(JobRun).options(undefer(JobRun.output_blob)).where(JobRun.id == job_id)
    )
    if job is None:
        raise HTTPException(404, {"code": "unknown_job"})
    if not may_read_job(user, job):
        raise HTTPException(403, {"code": "forbidden"})
    if job.status != "succeeded":
        raise HTTPException(409, {"code": "job_not_ready", "status": job.status})
    now = datetime.now(UTC).replace(tzinfo=None)
    if job.output_blob is None or job.output_expires_at is None or job.output_expires_at <= now:
        raise HTTPException(410, {"code": "output_expired"})
    disposition = f'attachment; filename="{safe_download_name(job.output_filename)}"'
    return Response(
        content=job.output_blob,
        media_type=job.output_mime or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )
