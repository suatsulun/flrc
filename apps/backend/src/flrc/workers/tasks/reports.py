import logging
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.db.sync import sync_engine
from flrc.modules.jobs.service import (
    discard_parts,
    mark_failed,
    mark_parts_succeeded,
    mark_running,
    mark_succeeded,
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
    # Only ids and names for the whole set; each class's cards are built when it is rendered.
    wanted_classes = set(payload.class_ids)
    wanted_students = set(payload.student_ids)
    classes = [
        (item.id, [s.id for s in item.students if s.id in wanted_students] or None)
        if wanted_students
        else (item.id, None)
        for item in eligible_roster(db, year_id=semester.year_id, kind=payload.kind)
        if (not wanted_classes or item.id in wanted_classes)
        and (not wanted_students or any(s.id in wanted_students for s in item.students))
    ]
    if not classes:
        raise ReportPackagingError("empty_report_set")
    # A redelivered job starts over; parts of an interrupted attempt are not this set's.
    discard_parts(db, job.id)
    mark_running(db, job, total=len(classes))

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
            if entries:
                yield ClassSet(class_id=class_id, entries=entries)

    filename = job.output_filename or "report"

    def advance(done: int) -> None:
        job.progress = done
        db.commit()

    def save_part(number: int, data: bytes) -> None:
        store_part(db, job, number=number, filename=part_filename(filename, number), data=data)

    result = package_report_set(
        class_sets(), payload.format, advance, packaging.MAX_OUTPUT_BYTES, save_part
    )
    if result.parts == 1:
        mark_succeeded(db, job, data=result.data, filename=filename, mime=result.mime)
        return
    save_part(result.parts, result.data)
    mark_parts_succeeded(db, job)


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
