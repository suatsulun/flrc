from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from flrc.db.models import JobRun, User
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import current_user
from flrc.modules.reports.filenames import content_disposition

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
    created_at: datetime
    # Set on the numbered parts of a request too large for one file (ADR-077).
    parent_id: int | None
    part: int | None

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
            created_at=job.created_at,
            parent_id=job.parent_id,
            part=job.part,
        )


def may_read_job(user: User, job: JobRun) -> bool:
    if user.is_admin or job.requested_by == user.id:
        return True
    return user.is_coordinator and job.kind != "year_export"


@router.get("/jobs")
async def list_jobs(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=25, ge=1, le=100),
) -> list[JobOut]:
    """The newest ``limit`` requests plus every job still running or still downloadable.

    Outputs are kept for 24 hours (ADR-024), so a downloads list must reach each of them,
    including every part of a split request, however many jobs ran since.
    """
    visible = select(JobRun.id)
    if not user.is_admin:
        # The same rule as ``may_read_job``: one's own jobs, and for coordinators every job
        # except year exports.
        own = JobRun.requested_by == user.id
        visible = visible.where(
            or_(own, JobRun.kind != "year_export") if user.is_coordinator else own
        )
    newest = visible.where(JobRun.parent_id.is_(None)).order_by(JobRun.id.desc()).limit(limit)
    now = datetime.now(UTC).replace(tzinfo=None)
    retained = visible.where(
        or_(JobRun.output_expires_at > now, JobRun.status.in_(("queued", "running")))
    )
    statement = (
        select(JobRun)
        .where(or_(JobRun.id.in_(newest.scalar_subquery()), JobRun.id.in_(retained)))
        .order_by(JobRun.id.desc())
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
    if job.output_blob is None and await db.scalar(
        select(exists().where(JobRun.parent_id == job.id))
    ):
        raise HTTPException(409, {"code": "job_output_in_parts"})
    if job.output_blob is None or job.output_expires_at is None or job.output_expires_at <= now:
        raise HTTPException(410, {"code": "output_expired"})
    return Response(
        content=job.output_blob,
        media_type=job.output_mime or "application/octet-stream",
        headers={"Content-Disposition": content_disposition(job.output_filename)},
    )
