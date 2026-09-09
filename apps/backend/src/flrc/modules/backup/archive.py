"""Academic-year archive bundles (ADR-056).

When a year is archived the school keeps, outside the application, everything
it would need in five years: the four report sets per semester as PDFs, the
whole-year workbook, an encrypted full dump from that moment, and a manifest
with checksums and counts. Human-readable files survive even if the app is
gone; the dump allows a complete historical restore.
"""

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.render import render_report_pdf
from flrc.workers.tasks.exports import build_year_workbook

REPORT_KINDS = ("english_elementary", "english_middle", "german_karne", "french_karne")
MANIFEST = "manifest.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def app_version() -> str:
    try:
        return version("flrc-backend")
    except PackageNotFoundError:
        return "unknown"


def year_counts(db: Session, year_id: int) -> dict[str, int]:
    enrollments = db.scalar(
        select(func.count()).select_from(m.Enrollment).where(m.Enrollment.year_id == year_id)
    )
    grade_values = db.scalar(
        select(func.count())
        .select_from(m.GradeValue)
        .join(m.ColumnDefinition, m.ColumnDefinition.id == m.GradeValue.column_definition_id)
        .join(m.Semester, m.Semester.id == m.ColumnDefinition.semester_id)
        .where(m.Semester.year_id == year_id)
    )
    classes = db.scalar(
        select(func.count()).select_from(m.SchoolClass).where(m.SchoolClass.year_id == year_id)
    )
    return {
        "enrollments": int(enrollments or 0),
        "grade_values": int(grade_values or 0),
        "classes": int(classes or 0),
    }


def schema_revision(db: Session) -> str | None:
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # a dump restored without the table, or no migrations yet
        db.rollback()
        return None
    return str(revision) if revision else None


def build_year_documents(db: Session, year: m.AcademicYear, out_dir: Path) -> list[Path]:
    """Render every non-empty report set for every semester, plus the workbook."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    semesters = list(
        db.scalars(
            select(m.Semester).where(m.Semester.year_id == year.id).order_by(m.Semester.number)
        )
    )
    for semester in semesters:
        for kind in REPORT_KINDS:
            cards = build_report_set(db, semester_id=semester.id, kind=kind, locale="tr")
            if not cards:
                continue
            target = out_dir / f"{year.label}-s{semester.number}-{kind}.pdf"
            target.write_bytes(render_report_pdf(cards))
            written.append(target)
    workbook = out_dir / f"{year.label}-export.xlsx"
    workbook.write_bytes(build_year_workbook(db, year.id))
    written.append(workbook)
    return written


def write_manifest(
    out_dir: Path,
    *,
    label: str,
    files: list[Path],
    counts: dict[str, int],
    revision: str | None,
) -> Path:
    manifest = {
        "label": label,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "app_version": app_version(),
        "schema_revision": revision,
        "counts": counts,
        "files": [
            {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_of(path)}
            for path in files
        ],
    }
    target = out_dir / MANIFEST
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
