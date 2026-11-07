import logging
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.db.sync import sync_engine
from flrc.modules.jobs.service import mark_failed, mark_running, mark_succeeded
from flrc.modules.reports.branding import ReportKind
from flrc.modules.reports.builder import build_report_entries
from flrc.modules.reports.packaging import (
    ReportFormat,
    ReportPackagingError,
    group_by_class,
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
    entries = build_report_entries(
        db,
        semester_id=payload.semester_id,
        kind=payload.kind,
        locale=payload.locale,
        class_ids=payload.class_ids or None,
        student_ids=payload.student_ids or None,
    )
    classes = group_by_class(entries)
    if not classes:
        raise ReportPackagingError("empty_report_set")
    mark_running(db, job, total=len(classes))

    def advance(done: int) -> None:
        job.progress = done
        db.commit()

    data, mime = package_report_set(classes, payload.format, advance)
    mark_succeeded(db, job, data=data, filename=job.output_filename or "report", mime=mime)


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
            fresh = db.get(m.JobRun, job_id)
            if fresh is not None:
                mark_failed(db, fresh, error.code)
        except Exception:
            db.rollback()
            fresh = db.get(m.JobRun, job_id)
            if fresh is not None:
                mark_failed(db, fresh, "report_set_failed")
            raise
