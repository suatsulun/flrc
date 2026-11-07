"""Package a built report set as one PDF, a ZIP of class PDFs, or a ZIP of student PDFs.

Each class is rendered once (ADR-028/046); a student's PDF is cut out of the class PDF by page
range, never rendered on its own. The page ranges are exact because every card owns fixed
pages: a duplex card is two pages, and a middle-school card is one page when printed alone on
its sheet. A class PDF whose page count disagrees with that mapping fails the job instead of
handing anyone a mis-split file (ADR-077).

A class is rendered, joined, split and covered entirely inside a render process, which writes
its files to a temporary folder and returns only their paths; the job's own process never holds
a class's PDF or HTML. Every file carries its own copy of what its pages use, including a
school's back-cover PDF on the German/French karne. A ZIP that would pass the output budget is
cut into numbered parts between whole files, one part in memory at a time.
"""

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import chain
from multiprocessing import get_context
from pathlib import Path
from tempfile import SpooledTemporaryFile, TemporaryDirectory
from typing import Literal, cast
from zipfile import ZIP_DEFLATED, ZipFile

import pikepdf

from flrc.modules.reports.builder import ReportEntry
from flrc.modules.reports.filenames import report_filename, student_scope
from flrc.modules.reports.models import ReportCard
from flrc.modules.reports.render import (
    back_cover_file,
    concatenate_pdfs,
    cover_duplex_backs,
    render_cards_to_file,
    render_worker_limit,
)

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


def split_pdf(
    source: Path, pages_each: int, parts: int, cover: pikepdf.Pdf | None = None
) -> list[Path]:
    """Cut ``source`` into ``parts`` files of ``pages_each`` pages, written beside it.

    Each file receives only its own pages and what they reference, so no other pupil's page
    travels in it. With ``cover``, each file's duplex backs become the school's cover.
    """
    files: list[Path] = []
    with pikepdf.open(source) as document:
        if len(document.pages) != pages_each * parts:
            raise ReportPackagingError("report_page_mapping")
        for index, start in enumerate(range(0, len(document.pages), pages_each)):
            with pikepdf.new() as part:
                part.pages.extend(document.pages[start : start + pages_each])
                if "/Info" in document.trailer:
                    part.docinfo = cast(pikepdf.Dictionary, part.copy_foreign(document.docinfo))
                if cover is not None:
                    cover_duplex_backs(part, cover)
                path = source.with_name(f"{source.stem}-pupil-{index:03d}.pdf")
                part.save(path)
            files.append(path)
    return files


def _with_cover(source: Path, cover: pikepdf.Pdf) -> Path:
    path = source.with_name(f"{source.stem}-covered.pdf")
    with pikepdf.open(source) as document:
        cover_duplex_backs(document, cover)
        document.save(path)
    return path


def render_class_files(
    cards: list[ReportCard],
    folder: str,
    index: int,
    report_format: ReportFormat,
    cover_path: str | None,
) -> list[str]:
    """Render one class inside this process and write the files the format needs.

    Runs in a render process: it receives only this class's cards and returns only paths.
    A combined set gets the class without the cover (the cover goes on once, after joining);
    a class ZIP gets the covered class; a pupil ZIP gets one covered file per pupil.
    """
    per_pupil = report_format == "per_student"
    source = Path(folder) / f"class-{index:04d}.pdf"
    pages = render_cards_to_file(cards, source, one_card_per_sheet=per_pupil)
    if pages != expected_pages(cards[0].kind, len(cards), one_card_per_sheet=per_pupil):
        raise ReportPackagingError("report_page_mapping")
    with ExitStack() as stack:
        cover = None
        if cover_path is not None and report_format != "combined":
            cover = stack.enter_context(pikepdf.open(cover_path))
        if per_pupil:
            pages_each = expected_pages(cards[0].kind, 1, one_card_per_sheet=True)
            files = split_pdf(source, pages_each, len(cards), cover)
            source.unlink()
            return [str(path) for path in files]
        if cover is not None:
            covered = _with_cover(source, cover)
            source.unlink()
            return [str(covered)]
    return [str(source)]


def _rendered(
    classes: Iterator[ClassSet],
    report_format: ReportFormat,
    folder: Path,
    cover_path: Path | None,
    pool: ProcessPoolExecutor | None,
    in_flight: int,
) -> Iterator[tuple[ClassSet, list[Path]]]:
    """Each class with its rendered files, in print order, keeping ``in_flight`` classes busy.

    Only the classes being rendered are held here; the rest are built as they are needed.
    """
    cover = None if cover_path is None else str(cover_path)
    pending: deque[tuple[ClassSet, Future[list[str]]]] = deque()
    for index, class_set in enumerate(classes):
        arguments = (
            [entry.card for entry in class_set.entries],
            str(folder),
            index,
            report_format,
            cover,
        )
        if pool is None:
            yield class_set, [Path(path) for path in render_class_files(*arguments)]
            continue
        pending.append((class_set, pool.submit(render_class_files, *arguments)))
        if len(pending) >= in_flight:
            done, future = pending.popleft()
            yield done, [Path(path) for path in future.result()]
    while pending:
        done, future = pending.popleft()
        yield done, [Path(path) for path in future.result()]


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

    def add(self, name: str, path: Path) -> None:
        """Copy a finished file from disk into the open part, then delete it."""
        cost = _entry_cost(path.stat().st_size, name)
        if cost > self.capacity:
            # One file alone is larger than any part may be.
            raise ReportPackagingError("report_output_too_large")
        if cost > self.room:
            self.next_part()
        self.bundle.write(path, _unique(name, self.taken))
        path.unlink()
        self.used += cost
        self.entries += 1

    def finish(self) -> PackagedSet:
        return PackagedSet(data=self._close(), mime=ZIP_MIME, parts=self.number)

    def abandon(self) -> None:
        self.bundle.close()
        self.spool.close()


def package_report_set(
    classes: Iterable[ClassSet],
    report_format: ReportFormat,
    on_class_done: Callable[[int], None] = lambda _done: None,
    max_bytes: int = MAX_OUTPUT_BYTES,
    on_part: Callable[[int, bytes], None] = lambda _number, _data: None,
) -> PackagedSet:
    """Render every class once and package the result.

    ``classes`` may be built lazily: a class is taken only when a render process is free for
    it. ``on_class_done`` receives the number of finished classes after each one. A ZIP larger
    than ``max_bytes`` is cut into numbered parts: every full part goes to ``on_part`` as it
    closes, and the last part is returned with the part count. Only a single file larger than
    ``max_bytes`` (or a combined PDF, which cannot be split) fails with
    ``report_output_too_large``.
    """
    iterator = iter(classes)
    first = next(iterator, None)
    if first is None:
        raise ReportPackagingError("empty_report_set")
    cover_path = back_cover_file(first.entries[0].card.kind)
    workers = render_worker_limit()
    with ExitStack() as stack:
        folder = Path(stack.enter_context(TemporaryDirectory(prefix="flrc-report-")))
        # A pool per job: its processes, and the memory they used, end with the job.
        pool = (
            stack.enter_context(
                ProcessPoolExecutor(max_workers=workers, mp_context=get_context("forkserver"))
            )
            if workers > 1
            else None
        )
        rendered = _rendered(
            chain([first], iterator), report_format, folder, cover_path, pool, workers
        )
        if report_format == "combined":
            return _package_combined(rendered, on_class_done, max_bytes, folder, cover_path)
        return _package_zip(rendered, report_format, on_class_done, max_bytes, on_part)


def _package_combined(
    rendered: Iterator[tuple[ClassSet, list[Path]]],
    on_class_done: Callable[[int], None],
    max_bytes: int,
    folder: Path,
    cover_path: Path | None,
) -> PackagedSet:
    """qpdf joins the uncovered class files from disk; the cover then goes on once."""
    files: list[Path] = []
    for done, (_class_set, paths) in enumerate(rendered, start=1):
        files.extend(paths)
        on_class_done(done)
    merged = folder / "merged.pdf"
    concatenate_pdfs(files, merged)
    if cover_path is not None:
        covered = folder / "covered.pdf"
        with pikepdf.open(merged) as document, pikepdf.open(cover_path) as cover:
            cover_duplex_backs(document, cover)
            document.save(covered)
        merged = covered
    if merged.stat().st_size > max_bytes:
        raise ReportPackagingError("report_output_too_large")
    return PackagedSet(data=merged.read_bytes(), mime=PDF_MIME, parts=1)


def _package_zip(
    rendered: Iterator[tuple[ClassSet, list[Path]]],
    report_format: ReportFormat,
    on_class_done: Callable[[int], None],
    max_bytes: int,
    on_part: Callable[[int, bytes], None],
) -> PackagedSet:
    zip_parts = _ZipParts(max_bytes, on_part)
    try:
        for done, (class_set, paths) in enumerate(rendered, start=1):
            first = class_set.entries[0].card
            kind, year_label, semester = first.kind, first.year_label, first.semester_number
            if report_format == "per_class":
                name = report_filename(class_set.class_name, kind, year_label, semester, "pdf")
                zip_parts.add(name, paths[0])
            else:
                for index, (entry, path) in enumerate(zip(class_set.entries, paths, strict=True)):
                    card = entry.card
                    scope = student_scope(card.class_name, card.school_number, card.student_name)
                    name = report_filename(scope, kind, year_label, semester, "pdf")
                    if index == 0:
                        # Keep a class together when it would not fit the part's remaining
                        # room, would fit a fresh part, and starting one wastes little.
                        estimate = path.stat().st_size * len(class_set.entries)
                        if (
                            _entry_cost(estimate, name) > zip_parts.room
                            and zip_parts.fits_fresh_part(estimate, name)
                            and zip_parts.room <= zip_parts.capacity * CLASS_BREAK_WASTE
                        ):
                            zip_parts.next_part()
                    zip_parts.add(name, path)
            on_class_done(done)
    except BaseException:
        zip_parts.abandon()
        raise
    return zip_parts.finish()
