import logging
from collections.abc import Iterator
from typing import Literal

from celery.signals import worker_ready
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.db.sync import sync_engine
from flrc.modules.jobs.service import (
    discard_parts,
    mark_failed,
    mark_parts_succeeded,
    mark_running,
    mark_succeeded,
    record_progress,
    store_part,
)
from flrc.modules.reports import packaging
from flrc.modules.reports.branding import ReportKind
from flrc.modules.reports.builder import build_report_entries, eligible_roster
from flrc.modules.reports.filenames import part_filename
from flrc.modules.reports.packaging import (
    ClassSet,
    ReportFormat,
    ReportPackagingError,
    package_report_set,
    reclaim_workspaces,
    workspace_prefix,
)
from flrc.workers.celery import celery_app

logger = logging.getLogger(__name__)


class ReportJobPayload(BaseModel):
    """What a `report_set` job stores; empty id lists mean every eligible class."""

    semester_id: int
    kind: ReportKind
    locale: Literal["tr", "en", "de", "fr"]
    format: ReportFormat
    class_ids: list[int]
    student_ids: list[int]


def run_report_job(db: Session, job: m.JobRun) -> None:
    payload = ReportJobPayload.model_validate(job.payload)
    semester = db.get(m.Semester, payload.semester_id)
    if semester is None:
        raise ValueError("unknown_semester")
    # One read freezes the set: every class and the pupils it prints. Each class is then built
    # from its frozen pupils only when a render process can take it.
    wanted_classes = set(payload.class_ids)
    wanted_students = set(payload.student_ids)
    classes: list[tuple[int, list[int]]] = []
    for item in eligible_roster(db, year_id=semester.year_id, kind=payload.kind):
        if wanted_classes and item.id not in wanted_classes:
            continue
        pupils = [s.id for s in item.students if not wanted_students or s.id in wanted_students]
        if pupils:
            classes.append((item.id, pupils))
    if not classes:
        raise ReportPackagingError("empty_report_set")
    # A redelivered job starts over; parts of an interrupted attempt are not this set's.
    discard_parts(db, job.id)
    mark_running(db, job, total=len(classes))
    printed: list[int] = []

    def class_sets() -> Iterator[ClassSet]:
        for class_id, student_ids in classes:
            entries = build_report_entries(
                db,
                semester_id=payload.semester_id,
                kind=payload.kind,
                locale=payload.locale,
                class_ids=[class_id],
                student_ids=student_ids,
            )
            printed.extend(entry.student_id for entry in entries)
            if entries:
                yield ClassSet(class_id=class_id, entries=entries)

    filename = job.output_filename or "report"

    def advance(done: int) -> None:
        record_progress(db, job, done)

    def save_part(number: int, data: bytes) -> None:
        store_part(db, job, number=number, filename=part_filename(filename, number), data=data)

    result = package_report_set(
        class_sets(),
        payload.format,
        advance,
        packaging.MAX_OUTPUT_BYTES,
        save_part,
        workspace=workspace_prefix(job.id),
    )
    # A pupil moved, removed or dropped from the language while the job ran would be printed
    # twice or not at all; nothing is published unless every frozen pupil appears once.
    if sorted(printed) != sorted(pupil for _, ids in classes for pupil in ids):
        raise ReportPackagingError("report_roster_changed")
    if result.parts == 1:
        mark_succeeded(db, job, data=result.data, filename=filename, mime=result.mime)
        return
    save_part(result.parts, result.data)
    mark_parts_succeeded(db, job, parts=result.parts)


def live_report_jobs(db: Session) -> list[int]:
    return list(
        db.scalars(
            select(m.JobRun.id).where(
                m.JobRun.kind == "report_set",
                m.JobRun.parent_id.is_(None),
                m.JobRun.status.in_(("queued", "running")),
            )
        )
    )


def reclaim_finished_workspaces(db: Session) -> None:
    removed = reclaim_workspaces(live_report_jobs(db))
    logger.info("reclaimed %s report workspaces", removed)


@worker_ready.connect
def reclaim_report_workspaces(**_kwargs: object) -> None:
    """A restarted worker first removes what killed jobs left in its temporary folder."""
    with Session(sync_engine()) as db:
        reclaim_finished_workspaces(db)


@celery_app.task(name="reports.set")
def report_set_job(job_id: int) -> None:
    with Session(sync_engine()) as db:
        job = db.get(m.JobRun, job_id)
        if job is None or job.status == "succeeded":
            return
        try:
            run_report_job(db, job)
        except ReportPackagingError as error:
            # An expected outcome (nothing to print, a page mapping refused): record the reason.
            logger.warning("report job %s failed: %s", job_id, error.code)
            db.rollback()
            discard_parts(db, job_id)
            fresh = db.get(m.JobRun, job_id)
            if fresh is not None:
                mark_failed(db, fresh, error.code)
        except Exception:
            db.rollback()
            discard_parts(db, job_id)
            fresh = db.get(m.JobRun, job_id)
            if fresh is not None:
                mark_failed(db, fresh, "report_set_failed")
            raise
        finally:
            # The job is finished now, so a workspace an interrupted earlier attempt left
            # behind is no longer protected as live and goes with this attempt's.
            reclaim_finished_workspaces(db)
