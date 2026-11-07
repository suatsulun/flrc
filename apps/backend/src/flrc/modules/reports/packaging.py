"""Package a built report set as one PDF, a ZIP of class PDFs, or a ZIP of student PDFs.

Each class is rendered once through the bounded renderer (ADR-028/046); a student's PDF is
cut out of the class PDF by page range, never rendered on its own. The page ranges are exact
because every card owns fixed pages: a duplex card is two pages, and a middle-school card is
one page when printed alone on its sheet. A class PDF whose page count disagrees with that
mapping fails the job instead of handing anyone a mis-split file (ADR-077).

Every file carries its own copy of what its pages use, including a school's back-cover PDF on
the German/French karne, so ZIP outputs grow with the number of files. The output budget keeps
a set within what the worker and the 24-hour blob store can hold.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from io import BytesIO
from tempfile import SpooledTemporaryFile
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

from pypdf import PdfReader, PdfWriter

from flrc.modules.reports.builder import ReportEntry
from flrc.modules.reports.filenames import report_filename, student_scope
from flrc.modules.reports.render import render_report_pdf

ReportFormat = Literal["combined", "per_class", "per_student"]
PDF_MIME = "application/pdf"
ZIP_MIME = "application/zip"
# The largest file a job may store. The 1 GiB worker holds it twice while saving it (the bytes
# and the database driver's copy) beside two render processes; the 2 GiB API holds it while it
# is downloaded (measurements in ADR-077).
MAX_OUTPUT_BYTES = 192 * 1024 * 1024
# A ZIP under construction moves to a temporary file beyond this size.
SPOOL_BYTES = 8 * 1024 * 1024


class ReportPackagingError(ValueError):
    """A report job failure with a stable, user-facing code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ClassSet:
    class_id: int
    entries: list[ReportEntry]

    @property
    def class_name(self) -> str:
        return self.entries[0].card.class_name


def group_by_class(entries: list[ReportEntry]) -> list[ClassSet]:
    """The set's classes in print order; the builder emits each class contiguously."""
    groups: dict[int, list[ReportEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.class_id, []).append(entry)
    return [ClassSet(class_id=class_id, entries=rows) for class_id, rows in groups.items()]


def expected_pages(kind: str, cards: int, *, one_card_per_sheet: bool) -> int:
    """How many pages a class of ``cards`` cards prints."""
    if kind == "english_middle":
        # Two A5 cards share an A4 sheet unless each is printed alone.
        return cards if one_card_per_sheet else (cards + 1) // 2
    # Primary English and the German/French karne are duplex: face and back.
    return 2 * cards


def render_class(class_set: ClassSet, *, one_card_per_sheet: bool = False) -> bytes:
    """Render one class and check its pages against the card mapping."""
    cards = [entry.card for entry in class_set.entries]
    pdf = render_report_pdf(cards, one_card_per_sheet=one_card_per_sheet)
    pages = len(PdfReader(BytesIO(pdf)).pages)
    if pages != expected_pages(cards[0].kind, len(cards), one_card_per_sheet=one_card_per_sheet):
        raise ReportPackagingError("report_page_mapping")
    return pdf


def _metadata(reader: PdfReader) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in (reader.metadata or {}).items()
        if isinstance(key, str) and value is not None
    }


def split_pdf(pdf: bytes, pages_each: int, parts: int) -> Iterator[bytes]:
    """Cut a PDF into ``parts`` consecutive files of ``pages_each`` pages, one at a time."""
    reader = PdfReader(BytesIO(pdf))
    if len(reader.pages) != pages_each * parts:
        raise ReportPackagingError("report_page_mapping")
    metadata = _metadata(reader)
    for start in range(0, len(reader.pages), pages_each):
        # A fresh writer receives only these pages and what they reference, so no other
        # student's page travels in the file.
        writer = PdfWriter()
        for page in reader.pages[start : start + pages_each]:
            writer.add_page(page)
        if metadata:
            writer.add_metadata(metadata)
        writer.compress_identical_objects()
        output = BytesIO()
        writer.write(output)
        yield output.getvalue()


class _OutputBudget:
    """Stops a set as soon as its output, projected from the students done, cannot fit."""

    def __init__(self, max_bytes: int, students: int) -> None:
        self.max_bytes = max_bytes
        self.students = students
        self.spent = 0
        self.done = 0

    def spend(self, size: int, students: int) -> None:
        self.spent += size
        self.done += students
        if self.spent * self.students > self.max_bytes * self.done:
            raise ReportPackagingError("report_output_too_large")


def _unique(name: str, taken: set[str]) -> str:
    """Two pupils with one name and no number must not overwrite each other in a ZIP."""
    stem, dot, extension = name.rpartition(".")
    candidate, copy = name, 1
    while candidate in taken:
        copy += 1
        candidate = f"{stem} ({copy}){dot}{extension}"
    taken.add(candidate)
    return candidate


def package_report_set(
    classes: list[ClassSet],
    report_format: ReportFormat,
    on_class_done: Callable[[int], None] = lambda _done: None,
    max_bytes: int = MAX_OUTPUT_BYTES,
) -> tuple[bytes, str]:
    """Render every class once and package the result; returns the bytes and their MIME type.

    ``on_class_done`` receives the number of finished classes after each one. A set whose
    output is on course to pass ``max_bytes`` stops early with ``report_output_too_large``.
    """
    if not classes:
        raise ReportPackagingError("empty_report_set")
    first = classes[0].entries[0].card
    kind, year_label, semester = first.kind, first.year_label, first.semester_number
    budget = _OutputBudget(max_bytes, sum(len(item.entries) for item in classes))

    if report_format == "combined":
        writer = PdfWriter()
        for done, class_set in enumerate(classes, start=1):
            pdf = render_class(class_set)
            reader = PdfReader(BytesIO(pdf))
            if done == 1 and reader.metadata:
                writer.add_metadata(_metadata(reader))
            for page in reader.pages:
                writer.add_page(page)
            # Each class repeats the fonts and any back cover; fold them as the set grows so
            # memory follows the finished document, not the sum of its class PDFs.
            writer.compress_identical_objects()
            on_class_done(done)
        output = BytesIO()
        writer.write(output)
        # Class PDFs overstate a combined set (its cover and fonts are shared), so only the
        # finished document is measured.
        if output.tell() > max_bytes:
            raise ReportPackagingError("report_output_too_large")
        return output.getvalue(), PDF_MIME

    taken: set[str] = set()
    # Finished entries wait on disk, not in memory, until the archive is complete.
    with SpooledTemporaryFile(max_size=SPOOL_BYTES) as archive:
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
            for done, class_set in enumerate(classes, start=1):
                if report_format == "per_class":
                    pdf = render_class(class_set)
                    budget.spend(len(pdf), len(class_set.entries))
                    name = report_filename(class_set.class_name, kind, year_label, semester, "pdf")
                    bundle.writestr(_unique(name, taken), pdf)
                else:
                    pdf = render_class(class_set, one_card_per_sheet=True)
                    pages_each = expected_pages(kind, 1, one_card_per_sheet=True)
                    students = split_pdf(pdf, pages_each, len(class_set.entries))
                    for entry, student_pdf in zip(class_set.entries, students, strict=True):
                        budget.spend(len(student_pdf), 1)
                        card = entry.card
                        scope = student_scope(
                            card.class_name, card.school_number, card.student_name
                        )
                        name = report_filename(scope, kind, year_label, semester, "pdf")
                        bundle.writestr(_unique(name, taken), student_pdf)
                on_class_done(done)
        archive.seek(0)
        return archive.read(), ZIP_MIME
