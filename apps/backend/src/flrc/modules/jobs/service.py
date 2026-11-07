from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from flrc.db.models import JobRun

OUTPUT_TTL = timedelta(hours=24)


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


def mark_failed(db: Session, job: JobRun, code: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_detail = "The job failed. See server logs with this job id."
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()


def store_part(db: Session, job: JobRun, *, number: int, filename: str, data: bytes) -> None:
    """Save one finished part of a split output and release its bytes from the session.

    A part is a ``job_runs`` row under its request, so it keeps the blob store, the download
    route and the request's authorization. It stays hidden as ``running`` until the whole set
    is finished, so a failed set never leaves half a download behind.
    """
    part = JobRun(
        kind=job.kind,
        status="running",
        requested_by=job.requested_by,
        payload={},
        parent_id=job.id,
        part=number,
        output_filename=filename,
        output_mime="application/zip",
        output_size=len(data),
        output_blob=data,
    )
    db.add(part)
    db.commit()
    db.expunge(part)


def mark_parts_succeeded(db: Session, job: JobRun) -> None:
    """Finish a split request: every part and the request share one 24-hour expiry."""
    now = datetime.now(UTC).replace(tzinfo=None)
    expires = now + OUTPUT_TTL
    db.execute(
        update(JobRun)
        .where(JobRun.parent_id == job.id)
        .values(status="succeeded", output_expires_at=expires, finished_at=now)
    )
    job.status = "succeeded"
    job.progress = job.total
    job.output_mime = "application/zip"
    job.output_size = db.scalar(
        select(func.sum(JobRun.output_size)).where(JobRun.parent_id == job.id)
    )
    job.output_expires_at = expires
    job.finished_at = now
    db.commit()


def discard_parts(db: Session, job_id: int) -> None:
    db.execute(delete(JobRun).where(JobRun.parent_id == job_id))
    db.commit()
