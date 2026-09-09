from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from flrc.db.models import JobRun

OUTPUT_TTL = timedelta(hours=24)


async def create_job(
    db: AsyncSession, *, kind: str, requested_by: int, payload: dict[str, object]
) -> JobRun:
    job = JobRun(kind=kind, status="queued", requested_by=requested_by, payload=payload)
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
