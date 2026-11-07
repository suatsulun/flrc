"""Package a built report set as one PDF, a ZIP of class PDFs, or a ZIP of student PDFs.

Each class is rendered once through the bounded renderer (ADR-028/046); a student's PDF is
cut out of the class PDF by page range, never rendered on its own. The page ranges are exact
because every card owns fixed pages: a duplex card is two pages, and a middle-school card is
one page when printed alone on its sheet. A class PDF whose page count disagrees with that
mapping fails the job instead of handing anyone a mis-split file (ADR-077).

Every file carries its own copy of what its pages use, including a school's back-cover PDF on
the German/French karne, so ZIP outputs grow with the number of files. A ZIP that would pass the
output budget is cut into numbered parts between whole files, one part in memory at a time.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile, TemporaryDirectory
from typing import Literal, cast
from zipfile import ZIP_DEFLATED, ZipFile

import pikepdf

from flrc.modules.reports.builder import ReportEntry
from flrc.modules.reports.filenames import report_filename, student_scope
from flrc.modules.reports.render import back_cover_file, cover_duplex_backs, render_report_pdf

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


def render_class(
    class_set: ClassSet, *, one_card_per_sheet: bool = False, back_cover: bool = True
) -> bytes:
    """Render one class and check its pages against the card mapping."""
    cards = [entry.card for entry in class_set.entries]
    pdf = render_report_pdf(cards, one_card_per_sheet=one_card_per_sheet, back_cover=back_cover)
    with pikepdf.open(BytesIO(pdf)) as document:
        pages = len(document.pages)
    if pages != expected_pages(cards[0].kind, len(cards), one_card_per_sheet=one_card_per_sheet):
        raise ReportPackagingError("report_page_mapping")
    return pdf


def split_pdf(
    pdf: bytes, pages_each: int, parts: int, cover: pikepdf.Pdf | None = None
) -> Iterator[bytes]:
    """Cut a PDF into ``parts`` consecutive files of ``pages_each`` pages, one at a time.

    Each file receives only its own pages and what they reference, so no other pupil's page
    travels in it. With ``cover``, each file's duplex backs become the school's cover.
    """
    with pikepdf.open(BytesIO(pdf)) as source:
        if len(source.pages) != pages_each * parts:
            raise ReportPackagingError("report_page_mapping")
        for start in range(0, len(source.pages), pages_each):
            with pikepdf.new() as part:
                part.pages.extend(source.pages[start : start + pages_each])
                if "/Info" in source.trailer:
                    part.docinfo = cast(pikepdf.Dictionary, part.copy_foreign(source.docinfo))
                if cover is not None:
                    cover_duplex_backs(part, cover)
                output = BytesIO()
                part.save(output)
            yield output.getvalue()


def _with_cover(pdf: bytes, cover: pikepdf.Pdf | None) -> bytes:
    """One class's PDF with the school's cover on its duplex backs."""
    if cover is None:
        return pdf
    with pikepdf.open(BytesIO(pdf)) as document:
        cover_duplex_backs(document, cover)
        output = BytesIO()
        document.save(output)
    return output.getvalue()


def _concatenate(files: list[Path], output: Path) -> None:
    """Join class PDFs page by page with qpdf, reading each from disk (ADR-077).

    The first file is the primary input so the set keeps its title and metadata.
    """
    job = pikepdf.Job(
        ["qpdf", str(files[0]), "--pages", *(str(path) for path in files), "--", str(output)]
    )
    job.run()
    if job.exit_code != 0:
        raise RuntimeError(f"qpdf could not join the class PDFs (exit {job.exit_code})")


def _unique(name: str, taken: set[str]) -> str:
    """Two pupils with one name and no number must not overwrite each other in a ZIP."""
    stem, dot, extension = name.rpartition(".")
    candidate, copy = name, 1
    while candidate in taken:
        copy += 1
        candidate = f"{stem} ({copy}){dot}{extension}"
    taken.add(candidate)
    return candidate


# What an entry adds beyond its bytes: local and central headers with the name twice, and the
# few bytes deflate adds to data that does not compress (PDF streams are compressed already).
ENTRY_OVERHEAD = 256
ARCHIVE_OVERHEAD = 1024
# A pupil ZIP starts a new part at a class boundary when the class no longer fits and at most
# this share of the part would stay unused.
CLASS_BREAK_WASTE = 0.25


def _entry_cost(size: int, name: str) -> int:
    return size + size // 500 + ENTRY_OVERHEAD + 2 * len(name.encode())


@dataclass(frozen=True)
class PackagedSet:
    """A packaged set: its last (or only) file, the MIME type, and how many parts it has."""

    data: bytes
    mime: str
    parts: int


class _ZipParts:
    """ZIP entries written into numbered parts that each stay within the budget.

    One part is open at a time, spooled to disk; a full part is handed to ``on_part`` and
    released before the next begins. Parts break only between whole files.
    """

    def __init__(self, max_bytes: int, on_part: Callable[[int, bytes], None]) -> None:
        self.capacity = max_bytes - ARCHIVE_OVERHEAD
        self.on_part = on_part
        self.number = 0
        self.taken: set[str] = set()
        self._open()

    def _open(self) -> None:
        self.spool = SpooledTemporaryFile(max_size=SPOOL_BYTES)
        self.bundle = ZipFile(self.spool, "w", compression=ZIP_DEFLATED)
        self.number += 1
        self.used = 0
        self.entries = 0

    def _close(self) -> bytes:
        self.bundle.close()
        self.spool.seek(0)
        data = self.spool.read()
        self.spool.close()
        return data

    @property
    def room(self) -> int:
        return self.capacity - self.used

    def next_part(self) -> None:
        if self.entries:
            self.on_part(self.number, self._close())
            self._open()

    def fits_fresh_part(self, size: int, name: str) -> bool:
        return _entry_cost(size, name) <= self.capacity

    def add(self, name: str, data: bytes) -> None:
        cost = _entry_cost(len(data), name)
        if cost > self.capacity:
            # One file alone is larger than any part may be.
            raise ReportPackagingError("report_output_too_large")
        if cost > self.room:
            self.next_part()
        self.bundle.writestr(_unique(name, self.taken), data)
        self.used += cost
        self.entries += 1

    def finish(self) -> PackagedSet:
        return PackagedSet(data=self._close(), mime=ZIP_MIME, parts=self.number)

    def abandon(self) -> None:
        self.bundle.close()
        self.spool.close()


def package_report_set(
    classes: list[ClassSet],
    report_format: ReportFormat,
    on_class_done: Callable[[int], None] = lambda _done: None,
    max_bytes: int = MAX_OUTPUT_BYTES,
    on_part: Callable[[int, bytes], None] = lambda _number, _data: None,
) -> PackagedSet:
    """Render every class once and package the result.

    ``on_class_done`` receives the number of finished classes after each one. A ZIP larger
    than ``max_bytes`` is cut into numbered parts: every full part goes to ``on_part`` as it
    closes, and the last part is returned with the part count. Only a single file larger than
    ``max_bytes`` (or a combined PDF, which cannot be split) fails with
    ``report_output_too_large``.
    """
    if not classes:
        raise ReportPackagingError("empty_report_set")
    # The school's cover is opened once per set and shared by every file that needs it.
    with ExitStack() as stack:
        cover_path = back_cover_file(classes[0].entries[0].card.kind)
        cover = stack.enter_context(pikepdf.open(cover_path)) if cover_path else None
        if report_format == "combined":
            return _package_combined(classes, on_class_done, max_bytes, cover)
        return _package_zip(classes, report_format, on_class_done, max_bytes, on_part, cover)


def _package_combined(
    classes: list[ClassSet],
    on_class_done: Callable[[int], None],
    max_bytes: int,
    cover: pikepdf.Pdf | None,
) -> PackagedSet:
    """Classes rendered without the cover go to disk; qpdf joins them; the cover goes on once."""
    with TemporaryDirectory(prefix="flrc-report-") as directory:
        folder = Path(directory)
        files: list[Path] = []
        for done, class_set in enumerate(classes, start=1):
            path = folder / f"class-{done:04d}.pdf"
            path.write_bytes(render_class(class_set, back_cover=False))
            files.append(path)
            on_class_done(done)
        merged = folder / "merged.pdf"
        _concatenate(files, merged)
        if cover is not None:
            covered = folder / "covered.pdf"
            with pikepdf.open(merged) as document:
                cover_duplex_backs(document, cover)
                document.save(covered)
            merged = covered
        if merged.stat().st_size > max_bytes:
            raise ReportPackagingError("report_output_too_large")
        return PackagedSet(data=merged.read_bytes(), mime=PDF_MIME, parts=1)


def _package_zip(
    classes: list[ClassSet],
    report_format: ReportFormat,
    on_class_done: Callable[[int], None],
    max_bytes: int,
    on_part: Callable[[int, bytes], None],
    cover: pikepdf.Pdf | None,
) -> PackagedSet:
    first = classes[0].entries[0].card
    kind, year_label, semester = first.kind, first.year_label, first.semester_number
    zip_parts = _ZipParts(max_bytes, on_part)
    try:
        for done, class_set in enumerate(classes, start=1):
            if report_format == "per_class":
                name = report_filename(class_set.class_name, kind, year_label, semester, "pdf")
                zip_parts.add(name, _with_cover(render_class(class_set, back_cover=False), cover))
            else:
                pdf = render_class(class_set, one_card_per_sheet=True, back_cover=False)
                pages_each = expected_pages(kind, 1, one_card_per_sheet=True)
                students = split_pdf(pdf, pages_each, len(class_set.entries), cover)
                for index, (entry, student_pdf) in enumerate(
                    zip(class_set.entries, students, strict=True)
                ):
                    card = entry.card
                    scope = student_scope(card.class_name, card.school_number, card.student_name)
                    name = report_filename(scope, kind, year_label, semester, "pdf")
                    if index == 0:
                        # Keep a class together when it would not fit the part's remaining
                        # room, would fit a fresh part, and starting one wastes little.
                        estimate = len(student_pdf) * len(class_set.entries)
                        if (
                            _entry_cost(estimate, name) > zip_parts.room
                            and zip_parts.fits_fresh_part(estimate, name)
                            and zip_parts.room <= zip_parts.capacity * CLASS_BREAK_WASTE
                        ):
                            zip_parts.next_part()
                    zip_parts.add(name, student_pdf)
            on_class_done(done)
    except BaseException:
        zip_parts.abandon()
        raise
    return zip_parts.finish()
