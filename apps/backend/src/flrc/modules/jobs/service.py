from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from flrc.db.models import JobRun, User

OUTPUT_TTL = timedelta(hours=24)

log = structlog.get_logger()


async def create_job(
    db: AsyncSession,
    *,
    kind: str,
    requested_by: int,
    payload: dict[str, object],
    filename: str | None = None,
    total: int = 0,
) -> JobRun:
    """Queue a job. A known output name and step count let the downloads list show it waiting."""
    job = JobRun(
        kind=kind,
        status="queued",
        requested_by=requested_by,
        payload=payload,
        output_filename=filename,
        total=total,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def pending_jobs(db: AsyncSession, *, kind: str, requested_by: int) -> int:
    """How many jobs of this kind the account has waiting or running.

    The account row stays locked until the caller's transaction ends (``create_job`` commits),
    so simultaneous requests of one account each count the job the other has just added.
    """
    await db.execute(select(User.id).where(User.id == requested_by).with_for_update(key_share=True))
    count = await db.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(
            JobRun.kind == kind,
            JobRun.requested_by == requested_by,
            JobRun.status.in_(("queued", "running")),
        )
    )
    return count or 0


async def publish_job(db: AsyncSession, job: JobRun, send: Callable[[int], object]) -> None:
    """Hand a stored job to the worker queue.

    The row is already committed, so a refused publication would leave it waiting for a
    message that never comes; it fails instead, and the request answers 503.
    """
    try:
        send(job.id)
    except Exception as error:
        log.warning("job_publication_failed", job_id=job.id, kind=job.kind, exc_info=True)
        _fail(job, "job_queue_unavailable")
        await db.commit()
        raise HTTPException(503, {"code": "job_queue_unavailable"}) from error


def mark_running(db: Session, job: JobRun, total: int) -> None:
    job.status = "running"
    job.total = total
    job.progress = 0
    job.started_at = datetime.now(UTC).replace(tzinfo=None)
    job.error_code = None
    job.error_detail = None
    db.commit()


def mark_succeeded(db: Session, job: JobRun, *, data: bytes, filename: str, mime: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    job.status = "succeeded"
    job.progress = job.total
    job.output_blob = data
    job.output_filename = filename
    job.output_mime = mime
    job.output_size = len(data)
    job.output_expires_at = now + OUTPUT_TTL
    job.finished_at = now
    db.commit()


def _fail(job: JobRun, code: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_detail = "The job failed. See server logs with this job id."
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)


def mark_failed(db: Session, job: JobRun, code: str) -> None:
    _fail(job, code)
    db.commit()
