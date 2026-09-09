"""Reproducible report-card PDF benchmark.

Run from ``apps/backend``::

    uv run python benchmarks/report_pdf.py                    # synthetic cards
    uv run python benchmarks/report_pdf.py --db 1             # a real semester
    uv run python benchmarks/report_pdf.py --profile out.prof

``--db`` builds the report set from postgres with the real builder, so the
data-build stage measures actual queries rather than a dictionary loop. The
synthetic mode needs no database and its names and values are deterministic
placeholders containing no school data.

Every scenario re-renders the set the old way (one WeasyPrint document) and
the new way, and asserts the two agree page for page before printing a
timing: a benchmark that is allowed to report a fast wrong answer is worse
than no benchmark.
"""

import argparse
import cProfile
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from statistics import median
from time import perf_counter

from pypdf import PdfReader

from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.models import ReportCard, ReportField
from flrc.modules.reports.render import (
    render_pdf_document,
    render_report_html,
    render_report_pdf,
    render_worker_limit,
)

KINDS = ("english_middle", "english_elementary", "german_karne", "french_karne")


def synthetic_cards(
    class_count: int,
    students_per_class: int = 22,
    kind: str = "english_middle",
) -> list[ReportCard]:
    subject = "german" if kind == "german_karne" else "english"
    grade_level = 3 if kind == "english_elementary" else 5
    value_type = "scale3" if kind == "german_karne" else "score"
    cards: list[ReportCard] = []
    for class_index in range(class_count):
        class_name = f"{grade_level}/{chr(ord('A') + class_index % 26)}{class_index // 26 or ''}"
        for student_index in range(students_per_class):
            fields = [
                ReportField(
                    label=f"Ölçüt {field_index}",
                    label_alt=f"Criterion {field_index}",
                    group=f"Bölüm {field_index // 6}",
                    group_alt=f"Group {field_index // 6}",
                    value_type=value_type,
                    value=(
                        1 + (student_index + field_index) % 3
                        if value_type == "scale3"
                        else 70 + (student_index + field_index) % 30
                    ),
                )
                for field_index in range(18)
            ]
            fields.append(
                ReportField(
                    label="Öğretmen görüşü",
                    label_alt="Teacher comment",
                    group=None,
                    group_alt=None,
                    value_type="text",
                    value=f"Synthetic comment {class_index}-{student_index}",
                )
            )
            cards.append(
                ReportCard(
                    kind=kind,
                    locale="tr",
                    year_label="2026-2027",
                    semester_number=1,
                    grade_level=grade_level,
                    class_name=class_name,
                    school_number=51000 + class_index * 100 + student_index,
                    student_name=f"Synthetic Student {class_index:02}-{student_index:02}",
                    subject=subject,
                    subject_label=subject.title(),
                    fields=fields,
                    average=84.5,
                    language_label=None,
                    language_fields=[],
                )
            )
    return cards


def timed[T](function: Callable[[], T], iterations: int) -> tuple[float, T]:
    """Median wall-clock of ``iterations`` runs, plus the last result.

    Median rather than minimum: a report set is rendered once per request on
    a shared instance, so the typical run matters more than the luckiest one.
    """
    samples: list[float] = []
    result: T | None = None
    for _ in range(iterations):
        started = perf_counter()
        result = function()
        samples.append(perf_counter() - started)
    assert result is not None
    return median(samples), result


def page_fingerprint(pdf: bytes) -> list[tuple[str, float, float, int]]:
    """What the regression tests compare: text, page box and rotation."""
    return [
        (
            page.extract_text(),
            float(page.mediabox.width),
            float(page.mediabox.height),
            page.rotation or 0,
        )
        for page in PdfReader(BytesIO(pdf)).pages
    ]


@dataclass
class Row:
    label: str
    cards: int
    pages: int
    build: float
    jinja: float
    serial: float
    parallel: float
    serial_bytes: int
    parallel_bytes: int

    def format(self) -> str:
        speedup = self.serial / self.parallel if self.parallel else 0.0
        return (
            f"| {self.label:<34} | {self.cards:>5} | {self.pages:>5} | "
            f"{self.build:>8.3f} | {self.jinja:>6.3f} | {self.serial:>9.2f} | "
            f"{self.parallel:>9.2f} | {speedup:>6.2f}x | "
            f"{self.serial_bytes / 1024:>7.0f} | {self.parallel_bytes / 1024:>7.0f} |"
        )


HEADER = (
    f"| {'scenario':<34} | {'cards':>5} | {'pages':>5} | {'build s':>8} | "
    f"{'jinja':>6} | {'before s':>9} | {'after s':>9} | {'gain':>7} | "
    f"{'KB pre':>7} | {'KB post':>7} |"
)
RULE = "|" + "|".join("-" * width for width in (36, 7, 7, 10, 8, 11, 11, 9, 9, 9)) + "|"


def measure(
    label: str,
    build: Callable[[], list[ReportCard]],
    iterations: int,
) -> Row:
    build_seconds, cards = timed(build, iterations)
    jinja_seconds, html = timed(lambda: render_report_html(cards), iterations)
    serial_seconds, serial_pdf = timed(lambda: render_pdf_document(html), iterations)
    parallel_seconds, parallel_pdf = timed(lambda: render_report_pdf(cards), iterations)

    before, after = page_fingerprint(serial_pdf), page_fingerprint(parallel_pdf)
    if before != after:
        page = next(
            (index for index, (a, b) in enumerate(zip(before, after, strict=False)) if a != b),
            min(len(before), len(after)),
        )
        raise SystemExit(f"{label}: parallel render differs from serial at page {page}")

    return Row(
        label=label,
        cards=len(cards),
        pages=len(before),
        build=build_seconds,
        jinja=jinja_seconds,
        serial=serial_seconds,
        parallel=parallel_seconds,
        serial_bytes=len(serial_pdf),
        parallel_bytes=len(parallel_pdf),
    )


@contextmanager
def report_session() -> Iterator[object]:
    from sqlalchemy.orm import Session

    from flrc.db.sync import sync_engine

    engine = sync_engine()
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--db",
        type=int,
        metavar="SEMESTER_ID",
        help="benchmark real report sets from the database at DATABASE_URL_DIRECT",
    )
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()

    print(f"renderer workers: {render_worker_limit()} (host CPUs: {os.process_cpu_count()})\n")
    print(HEADER)
    print(RULE)

    if args.db is None:
        for classes in (1, 4, 26):
            print(
                measure(
                    f"synthetic middle, {classes} class(es)",
                    lambda classes=classes: synthetic_cards(classes),
                    args.iterations,
                ).format()
            )
        print(
            measure(
                "synthetic karne, 4 classes",
                lambda: synthetic_cards(4, kind="german_karne"),
                args.iterations,
            ).format()
        )
    else:
        with report_session() as session:
            for kind in KINDS:
                cards = build_report_set(session, semester_id=args.db, kind=kind, locale="tr")
                if not cards:
                    print(f"| {kind:<34} | (no cards for this semester)")
                    continue
                print(
                    measure(
                        f"school set, {kind}",
                        lambda kind=kind: build_report_set(
                            session, semester_id=args.db, kind=kind, locale="tr"
                        ),
                        args.iterations,
                    ).format()
                )

    if args.profile:
        cards = synthetic_cards(1)
        html = render_report_html(cards)
        render_pdf_document(html)  # warm the font and asset caches
        profiler = cProfile.Profile()
        profiler.enable()
        render_pdf_document(html)
        profiler.disable()
        profiler.dump_stats(args.profile)
        print(f"\nwrote profile to {args.profile}")


if __name__ == "__main__":
    main()
