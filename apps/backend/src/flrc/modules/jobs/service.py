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


FAILED_DETAIL = "The job failed. See server logs with this job id."


def mark_failed(db: Session, job: JobRun, code: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_detail = FAILED_DETAIL
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()


# A staged part outlives no job: every step the job finishes extends it, and once the job stops
# advancing for this long ``purge_job_outputs`` fails the request and reclaims its parts.
STAGED_PART_TTL = timedelta(hours=6)


def record_progress(db: Session, job: JobRun, done: int) -> None:
    """Record a finished step and extend the staging expiry of the parts stored so far.

    Progress is the job's heartbeat: a set that keeps advancing never loses its staged parts,
    however long it runs.
    """
    job.progress = done
    db.execute(
        update(JobRun)
        .where(JobRun.parent_id == job.id, JobRun.status != "succeeded")
        .values(output_expires_at=datetime.now(UTC).replace(tzinfo=None) + STAGED_PART_TTL)
    )
    db.commit()


class IncompletePartsError(Exception):
    """A split set lost a part, or its request stopped running, before it could be published."""


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


def mark_parts_succeeded(db: Session, job: JobRun, *, parts: int) -> None:
    """Finish a split request: every part and the request share one 24-hour expiry.

    The request row is locked first, as ``purge_job_outputs`` locks it before reclaiming parts,
    and the set is published only while the request is still running and holds exactly the
    parts 1 to ``parts``; otherwise ``IncompletePartsError`` is raised and nothing changes.
    """
    db.refresh(job, with_for_update=True)
    stored = db.scalars(
        select(JobRun.part).where(JobRun.parent_id == job.id).order_by(JobRun.part)
    ).all()
    if job.status != "running" or list(stored) != list(range(1, parts + 1)):
        raise IncompletePartsError(job.id)
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
    aborted set is cleaned up even when its own exception handler never ran. A request still
    queued or running whose staged parts expired has stopped advancing: it is marked failed
    first, in the same transaction, so it can never publish a set without those parts.
    Expired outputs keep their history row and lose only their bytes (ADR-024). Returns how
    many outputs were reclaimed.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    stalled = select(JobRun.parent_id).where(
        JobRun.parent_id.is_not(None),
        JobRun.status != "succeeded",
        JobRun.output_expires_at < now,
    )
    db.execute(
        update(JobRun)
        .where(JobRun.id.in_(stalled), JobRun.status.in_(("queued", "running")))
        .values(
            status="failed",
            error_code="report_set_failed",
            error_detail=FAILED_DETAIL,
            finished_at=now,
        )
    )
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
