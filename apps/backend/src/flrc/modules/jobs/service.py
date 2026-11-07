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


# A staged part outlives no job: if the job dies before replacing this with the set's shared
# expiry, ``purge_job_outputs`` reclaims it on its own.
STAGED_PART_TTL = timedelta(hours=6)


def store_part(db: Session, job: JobRun, *, number: int, filename: str, data: bytes) -> None:
    """Save one finished part of a split output and release its bytes from the session.

    A part is a ``job_runs`` row under its request, so it keeps the blob store, the download
    route and the request's authorization. It stays hidden as ``running`` until the whole set
    is finished, so a failed set never leaves half a download behind; until then it carries
    a short staging expiry of its own.
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
        output_expires_at=datetime.now(UTC).replace(tzinfo=None) + STAGED_PART_TTL,
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


def purge_job_outputs(db: Session) -> int:
    """Reclaim stored outputs past their expiry and parts of requests that did not succeed.

    Parts of a failed request, or staged parts past their bound, are deleted outright, so an
    aborted set is cleaned up even when its own exception handler never ran. Expired outputs
    keep their history row and lose only their bytes (ADR-024). Returns how many outputs were
    reclaimed.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    failed_requests = select(JobRun.id).where(JobRun.status == "failed")
    aborted = db.execute(
        delete(JobRun).where(
            JobRun.parent_id.is_not(None),
            (JobRun.parent_id.in_(failed_requests))
            | ((JobRun.status != "succeeded") & (JobRun.output_expires_at < now)),
        )
    )
    expired = db.execute(
        update(JobRun)
        .where(JobRun.output_expires_at < now, JobRun.output_blob.is_not(None))
        .values(output_blob=None)
    )
    db.commit()
    return int(getattr(aborted, "rowcount", 0) or 0) + int(getattr(expired, "rowcount", 0) or 0)
