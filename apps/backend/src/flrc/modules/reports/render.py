"""HTML and PDF rendering for report-card sets.

This is the third layer of the report pipeline: the builder produces
:class:`ReportCard` data, this module arranges it for the page, and WeasyPrint
turns the result into a PDF.

Each report set has its own template because the school's four cards are
genuinely different documents:

- ``middle_english.html`` — an A5 card printed two-up on A4 and cut apart,
  imposed so the guillotined class stack reads in roster order.
- ``primary_english.html`` — an A4 duplex card: decorated cover, then the
  smiley-face checklist.
- ``karne.html`` — the German/French A4 duplex card: bilingual checklist
  (plus the semester grade row for grades 5–8), then a language cover.

They share ``base.html`` so page setup and print CSS live in one place.

Private school overlays can add the logo, assigned teachers' report names and
signatures, grade-selected principals, and original PDF back covers. Generic
templates keep their existing appearance when no overlay is configured.
"""

import base64
import json
import logging
import mimetypes
import os
from concurrent.futures import Executor, ProcessPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from multiprocessing import get_context
from pathlib import Path
from threading import Lock
from typing import Literal, cast
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

from flrc.config import settings
from flrc.modules.reports.branding import ReportKind, contained_file, report_branding
from flrc.modules.reports.models import ReportCard, ReportField

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
BRAND_FILE = ASSETS / "brand.json"
BRAND_LOGO = ASSETS / "logo.svg"

# Used only if `pnpm brand` has never run, so a bare checkout still renders.
FALLBACK_NAME = "FL-ReportCard"
FALLBACK_ACCENT = "#1c62b6"

# A whole-school set is rendered on the request thread, so the pool is capped
# rather than sized to the host: four WeasyPrint workers already saturate the
# small instances this deploys to, and each one costs real memory.
MAX_RENDER_WORKERS = 4
# Below this many sheets the pool costs more than the layout it saves.
# Below twelve sheets, process dispatch and PDF merging cost more than the
# saved layout time on the deployment-sized benchmark host (11 sheets:
# 2.00s serial versus 3.04s parallel). Keep ordinary small classes direct.
MIN_PARALLEL_UNITS = 12
# Everything the cards reference is a data URI built in this module. Anything
# else — a local file, an internal HTTP address — is refused outright.
ALLOWED_ASSET_SCHEMES = frozenset({"data"})
MAX_CACHED_ASSETS = 16

env = Environment(
    loader=FileSystemLoader(HERE / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

TEMPLATES = {
    "english_middle": "middle_english.html",
    "english_elementary": "primary_english.html",
    "german_karne": "karne.html",
    "french_karne": "karne.html",
}

# Document titles only (browser tab / PDF metadata); the card faces themselves
# are fixed bilingual documents and ignore the caller's UI locale.
SET_TITLES = {
    "tr": {
        "english_elementary": "İngilizce İlkokul Karneleri",
        "english_middle": "İngilizce Ortaokul Karneleri",
        "german_karne": "Almanca Karneleri",
        "french_karne": "Fransızca Karneleri",
    },
    "en": {
        "english_elementary": "Elementary English Report Cards",
        "english_middle": "Middle School English Report Cards",
        "german_karne": "German Report Cards",
        "french_karne": "French Report Cards",
    },
    "de": {
        "english_elementary": "Englischzeugnisse Grundschule",
        "english_middle": "Englischzeugnisse Mittelstufe",
        "german_karne": "Deutschzeugnisse",
        "french_karne": "Französischzeugnisse",
    },
    "fr": {
        "english_elementary": "Bulletins d’anglais primaire",
        "english_middle": "Bulletins d’anglais collège",
        "german_karne": "Bulletins d’allemand",
        "french_karne": "Bulletins de français",
    },
}

NO_FIELDS_NOTE = "Bu sınıf seviyesi için rapor alanı yapılandırılmamış."

# Checklist column order follows the school's cards: the karne lists the
# weakest rating first, the primary card puts the happiest face first.
KARNE_SCALE_ORDER = (1, 2, 3)
PRIMARY_SCALE_ORDER = (3, 2, 1)


def _svg_uri(body: str, viewbox: str) -> str:
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{viewbox}'>{body}</svg>"
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def _face(mouth: str) -> str:
    """A rating face as a data-URI SVG.

    Drawn rather than typed: DejaVu has no neutral-face glyph, and the
    school's card uses the yellow smiley style.
    """
    return _svg_uri(
        "<circle cx='12' cy='12' r='10.4' fill='#ffd34d' stroke='#8a6414' stroke-width='1.4'/>"
        "<circle cx='8.3' cy='9.7' r='1.4' fill='#5d430c'/>"
        "<circle cx='15.7' cy='9.7' r='1.4' fill='#5d430c'/>"
        f"{mouth}",
        "0 0 24 24",
    )


_STROKE = "fill='none' stroke='#5d430c' stroke-width='1.7' stroke-linecap='round'"
# Happiest first, matching PRIMARY_SCALE_ORDER.
FACES = (
    _face(f"<path d='M7.3 13.8c1.3 2.1 2.9 3.1 4.7 3.1s3.4-1 4.7-3.1' {_STROKE}/>"),
    _face(f"<path d='M8 15.6h8' {_STROKE}/>"),
    _face(f"<path d='M7.3 17.2c1.3-2.1 2.9-3.1 4.7-3.1s3.4 1 4.7 3.1' {_STROKE}/>"),
)

# Landmark silhouettes, printed as pale watermarks behind the karne checklist
# exactly like the school's cards (Eiffel Tower / Brandenburg Gate).
EIFFEL_WATERMARK = _svg_uri(
    "<g fill='#243044' fill-opacity='0.09'>"
    "<rect x='56' y='0' width='8' height='22'/>"
    "<path d='M60 14 L71 88 H49 Z'/>"
    "<rect x='42' y='86' width='36' height='8'/>"
    "<path d='M52 94 C52 130 44 160 30 196 L39 196 C48 172 55 152 60 141 "
    "C65 152 72 172 81 196 L90 196 C76 160 68 130 68 94 Z'/>"
    "<rect x='30' y='146' width='60' height='7'/>"
    "<path d='M14 252 C34 220 46 205 50 194 H70 C74 205 86 220 106 252 H88 "
    "C74 230 66 221 60 211 C54 221 46 230 32 252 Z'/>"
    "<rect x='8' y='250' width='104' height='6'/>"
    "</g>",
    "0 0 120 256",
)
BRANDENBURG_WATERMARK = _svg_uri(
    "<g fill='#243044' fill-opacity='0.09'>"
    "<rect x='128' y='2' width='44' height='8'/>"
    "<rect x='138' y='10' width='24' height='10'/>"
    "<rect x='96' y='20' width='108' height='16'/>"
    "<rect x='12' y='38' width='276' height='24'/>"
    "<rect x='6' y='62' width='288' height='6'/>"
    + "".join(
        f"<rect x='{x - 3}' y='70' width='24' height='6'/>"
        f"<rect x='{x}' y='76' width='18' height='90'/>"
        for x in (22, 71, 120, 169, 218, 267)
    )
    + "<rect x='0' y='168' width='300' height='8'/>"
    "</g>",
    "0 0 300 176",
)


def _balloon(x: float, y: float, color: str) -> str:
    return (
        f"<path d='M{x} {y + 11} q 3 7 -1.5 14 q -3 6 1.5 13' "
        "fill='none' stroke='#9aa0a6' stroke-width='0.7'/>"
        f"<ellipse cx='{x}' cy='{y}' rx='8.6' ry='10.6' fill='{color}'/>"
        f"<path d='M{x - 2.6} {y + 10} L{x} {y + 13.4} L{x + 2.6} {y + 10} Z' fill='{color}'/>"
        f"<ellipse cx='{x - 3}' cy='{y - 3.6}' rx='2.4' ry='3.4' fill='white' opacity='0.35'/>"
    )


# The primary cover's scattered balloons, echoing the school's printed cover.
BALLOONS_BACKGROUND = _svg_uri(
    "".join(
        _balloon(x, y, color)
        for x, y, color in (
            (22, 30, "#e63946"),
            (44, 70, "#f28ab2"),
            (16, 122, "#4dabf7"),
            (34, 172, "#94c973"),
            (66, 26, "#ffd43b"),
            (233, 32, "#38b2a3"),
            (276, 26, "#f28ab2"),
            (256, 74, "#e63946"),
            (282, 124, "#ffd43b"),
            (262, 172, "#b197fc"),
            (60, 178, "#ff922b"),
            (150, 190, "#4dabf7"),
        )
    ),
    "0 0 297 210",
)


def ordinal_en(number: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(number, "th")
    return f"{number}{suffix}"


def ordinal_fr(number: int, feminine: bool = False) -> str:
    if number == 1:
        return "1ère" if feminine else "1er"
    return f"{number}ème"


# Cover words are stored pre-uppercased: CSS text-transform under lang="tr"
# applies Turkish casing and would print FRANÇAİS with a dotted İ.
KARNE_STATIC = {
    "german": {
        "word": "DEUTSCH",
        "name_label": "Vor- und Nachname",
        "class_label": "Klasse",
        "title_tr": "İKİNCİ YABANCI DİL KARNESİ",
        "title_l2": "ZEUGNIS FÜR DIE ZWEITE FREMDSPRACHE",
        "ratings": (
            ("Geliştirilmeli", "Aufbaubedürftig"),
            ("İyi", "Gut"),
            ("Çok İyi", "Sehr gut"),
        ),
    },
    "french": {
        "word": "FRANÇAIS",
        "name_label": "Nom-Prénom",
        "class_label": "Classe",
        "title_tr": "İKİNCİ YABANCI DİL KARNESİ",
        "title_l2": "BULLETIN LANGUE VIVANTE 2",
        "ratings": (
            ("Geliştirilmeli", "À développer"),
            ("İyi", "Bien"),
            ("Çok İyi", "Très bien"),
        ),
    },
}


def karne_chrome(card: ReportCard) -> dict[str, object]:
    """The karne's fixed bilingual wording, formatted for this card's scope."""
    grade, semester = card.grade_level, card.semester_number
    if card.subject == "german":
        scope_l2 = f"{grade}. Klassen {semester}. Halbjahr"
        grade_l2 = f"ZEUGNISNOTE {semester}. HALBJAHR"
    else:
        scope_l2 = f"{ordinal_fr(grade, feminine=True)} Classe {ordinal_fr(semester)} Semestre"
        grade_l2 = f"MOYENNE DU {ordinal_fr(semester)} SEMESTRE"
    return {
        **KARNE_STATIC[card.subject],
        "scope_tr": f"{grade}. Sınıflar {semester}. Dönem",
        "scope_l2": scope_l2,
        "grade_tr": f"{semester}. DÖNEM DERS NOTU",
        "grade_l2": grade_l2,
    }


@dataclass(frozen=True)
class ChecklistBlock:
    """A consecutive run of same-group fields, in the configured order.

    Grouping happens here rather than in the template because Jinja's
    ``groupby`` sorts its input, which would reorder the rows the school
    deliberately arranged.
    """

    group: str | None
    group_alt: str | None
    rows: tuple[ReportField, ...]


def consecutive_blocks(fields: list[ReportField]) -> tuple[ChecklistBlock, ...]:
    blocks: list[ChecklistBlock] = []
    rows: list[ReportField] = []
    current: str | None = None
    current_alt: str | None = None
    for field in fields:
        if rows and field.group != current:
            blocks.append(ChecklistBlock(current, current_alt, tuple(rows)))
            rows = []
        current, current_alt = field.group, field.group_alt
        rows.append(field)
    if rows:
        blocks.append(ChecklistBlock(current, current_alt, tuple(rows)))
    return tuple(blocks)


def _split_for_columns(
    blocks: tuple[ChecklistBlock, ...],
) -> tuple[list[ChecklistBlock], list[ChecklistBlock]]:
    """Deal blocks into the checklist page's two columns, balanced by height.

    Done in Python rather than CSS multi-column so a section box never splits
    across columns and the result is deterministic in WeasyPrint.
    """
    total = sum(len(block.rows) + 2 for block in blocks)
    left: list[ChecklistBlock] = []
    right: list[ChecklistBlock] = []
    used = 0
    for block in blocks:
        if used < total / 2:
            left.append(block)
            used += len(block.rows) + 2
        else:
            right.append(block)
    return left, right


def _comments(card: ReportCard) -> list[ReportField]:
    return [field for field in card.fields if field.value_type == "text"]


def _grade_display(average: float | None) -> str:
    # Blank rather than a dash: the school's card leaves the grade box empty
    # when no grade exists. Half-up rounding — a 79.5 must not print as 79.
    return "" if average is None else str(int(average + 0.5))


def middle_sheet(card: ReportCard) -> dict[str, object]:
    scored = [field for field in card.fields if field.value_type != "text"]
    blocks = consecutive_blocks(scored)
    lang_blocks = consecutive_blocks(card.language_fields)
    # Header depth: 1 for a flat row of labels, 2 when any group spans its
    # columns, 3 when the language section has its own sub-groups
    # (DEUTSCH → Klassenarbeiten/Hausaufgaben → the individual columns).
    if any(block.group for block in lang_blocks):
        depth = 3
    elif card.language_fields or any(block.group for block in blocks):
        depth = 2
    else:
        depth = 1
    return {
        "card": card,
        "blocks": blocks,
        "lang_blocks": lang_blocks,
        "depth": depth,
        "comments": _comments(card),
        "title": f"{card.year_label} ACADEMIC PROGRESS REPORT",
    }


def cut_stack_pages(cards: list[ReportCard]) -> list[dict[str, object]]:
    """Two A5 cards per A4 sheet, imposed for guillotine cutting.

    Within a class of n students, sheet i carries student i on top and
    student i + ceil(n/2) below. Print the class, cut the stack across the
    middle, put the top pile on the bottom pile: the cards are in roster
    order. Each class starts on its own sheet so classes can be cut as
    separate stacks.
    """
    by_class: dict[str, list[ReportCard]] = {}
    for card in cards:
        by_class.setdefault(card.class_name, []).append(card)

    pages: list[dict[str, object]] = []
    for class_cards in by_class.values():
        half = (len(class_cards) + 1) // 2
        for index in range(half):
            bottom = class_cards[index + half] if index + half < len(class_cards) else None
            pages.append(
                {
                    "top": middle_sheet(class_cards[index]),
                    "bottom": middle_sheet(bottom) if bottom else None,
                }
            )
    return pages


def primary_sheet(card: ReportCard) -> dict[str, object]:
    scored = [field for field in card.fields if field.value_type != "text"]
    left, right = _split_for_columns(consecutive_blocks(scored))
    return {
        "card": card,
        "left": left,
        "right": right,
        "comments": _comments(card),
        "title_en": (
            f"{card.year_label} {ordinal_en(card.grade_level)} Grade "
            f"{ordinal_en(card.semester_number)} Term English Progress Report"
        ),
    }


def karne_sheet(card: ReportCard) -> dict[str, object]:
    # Score-type columns never appear as checklist rows: they live on the
    # middle-school English card and inside the semester average.
    checkable = [field for field in card.fields if field.value_type == "scale3"]
    blocks = consecutive_blocks(checkable)
    return {
        "card": card,
        "chrome": karne_chrome(card),
        "blocks": blocks,
        "comments": _comments(card),
        "has_rail": any(block.group for block in blocks),
        # Primary students (grades 1–4) get no numeric grade on their karne.
        "show_grade": card.grade_level >= 5,
        "grade_display": _grade_display(card.average),
    }


@dataclass(frozen=True)
class SchoolBrand:
    """What the report card says about the school issuing it."""

    name: str
    accent: str
    logo: str | None


@lru_cache(maxsize=1)
def school_logo_data_uri() -> str | None:
    """The school's logo as a data URI, or ``None`` if there is no readable file.

    Private templates place this logo; environment overrides and generic
    assets continue to use the same resolution order.
    """
    path = next((candidate for candidate in _logo_candidates() if candidate.is_file()), None)
    if path is None:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _branding_dir() -> Path | None:
    if not settings.school_branding_dir:
        return None
    path = Path(settings.school_branding_dir)
    return path if path.is_dir() else None


def _logo_candidates() -> list[Path]:
    candidates: list[Path] = []
    if settings.school_logo_path:
        candidates.append(Path(settings.school_logo_path))
    if (overlay := _branding_dir()) is not None:
        candidates.append(overlay / "logo.svg")
    candidates.append(BRAND_LOGO)
    return candidates


def _brand_sources() -> list[Path]:
    sources: list[Path] = []
    if (overlay := _branding_dir()) is not None:
        sources.append(overlay / "brand.json")
    sources.append(BRAND_FILE)
    return sources


@lru_cache(maxsize=1)
def school_brand() -> SchoolBrand:
    """Resolve the school's name, accent, and logo for report cards.

    Precedence is the ``SCHOOL_NAME``/``SCHOOL_LOGO_PATH`` overrides, then a
    mounted ``SCHOOL_BRANDING_DIR`` overlay, then the assets synced in by
    ``pnpm brand``, then a built-in fallback so a checkout that has never run
    the tool still produces a sane report card.
    """
    name, accent = FALLBACK_NAME, FALLBACK_ACCENT
    for source in _brand_sources():
        if not source.is_file():
            continue
        try:
            brand = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = str(brand.get("name") or name)
        accent = str(brand.get("accentColor") or accent)
        break
    return SchoolBrand(
        name=settings.school_name or name,
        accent=accent,
        logo=school_logo_data_uri(),
    )


def _document_plan(cards: list[ReportCard]) -> tuple[str, dict[str, object], str, list[object]]:
    """Everything a document needs, with the repeated sheets kept separate.

    The context a report set shares (title, branding, scale order, watermark)
    is identical for every sheet in it, so it is built once and the sheets are
    returned alongside it. That lets one set be rendered whole or in slices
    from the very same context, which is what keeps a parallel render
    byte-identical to a serial one.
    """
    if not cards:
        raise ValueError("empty_report_set")
    first = cards[0]
    template = TEMPLATES.get(first.kind)
    if template is None:
        raise ValueError("unknown_report_kind")
    locale = first.locale if first.locale in SET_TITLES else "tr"

    context: dict[str, object] = {
        "set_title": SET_TITLES[locale][first.kind],
        "school": school_brand(),
        "no_fields_note": NO_FIELDS_NOTE,
    }
    if (branding := report_branding()) is not None:
        template = branding.config.templates.get(cast(ReportKind, first.kind), template)
        context["report_branding"] = branding.context()
    if first.kind == "english_middle":
        return template, context, "pages", list(cut_stack_pages(cards))
    if first.kind == "english_elementary":
        context["faces"] = FACES
        context["scale_order"] = PRIMARY_SCALE_ORDER
        context["balloons"] = BALLOONS_BACKGROUND
        return template, context, "sheets", [primary_sheet(card) for card in cards]
    context["scale_order"] = KARNE_SCALE_ORDER
    context["watermark"] = BRANDENBURG_WATERMARK if first.subject == "german" else EIFFEL_WATERMARK
    return template, context, "sheets", [karne_sheet(card) for card in cards]


def render_report_html(cards: list[ReportCard]) -> str:
    template, context, units_key, units = _document_plan(cards)
    return _template_environment().get_template(template).render(**context, **{units_key: units})


def _template_environment() -> Environment:
    branding = report_branding()
    return branding.environment(HERE / "templates") if branding else env


def _apply_back_cover(pdf: bytes, cards: list[ReportCard]) -> bytes:
    """Replace each duplex back with the original school PDF, without rasterizing it."""
    branding = report_branding()
    if branding is None:
        return pdf
    relative = branding.config.covers.get(
        cast(Literal["german_karne", "french_karne"], cards[0].kind)
    )
    if relative is None:
        return pdf
    cover = PdfReader(contained_file(branding.root, relative))
    document = PdfReader(BytesIO(pdf))
    if len(cover.pages) != 1 or len(document.pages) != 2 * len(cards):
        raise ValueError("report_duplex_page_count")
    writer = PdfWriter()
    for index in range(0, len(document.pages), 2):
        face = document.pages[index]
        back = cover.pages[0]
        if (
            abs(float(face.mediabox.width) - float(back.mediabox.width)) > 2
            or abs(float(face.mediabox.height) - float(back.mediabox.height)) > 2
        ):
            raise ValueError("report_cover_page_size")
        writer.add_page(face)
        writer.add_page(back)
    if document.metadata:
        writer.add_metadata({key: str(value) for key, value in document.metadata.items()})
    writer.compress_identical_objects()
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


class ReportAssetFetcher(URLFetcher):
    """Deny-by-default asset fetcher for the report templates.

    The cards embed every asset they need — the logo, the rating faces, the
    landmark watermarks — as ``data:`` URIs built in this module. Nothing a
    card legitimately references lives on disk or on the network, so every
    other scheme is refused. Without this, a URL that reached a template could
    make the renderer read a local file (``file:``) or reach an internal
    address (``http:``) on behalf of whoever asked for the report.

    Decoded asset bytes are memoised, so a set rendered as several documents
    decodes each watermark once per process instead of once per document.
    """

    def __init__(self) -> None:
        super().__init__(allowed_protocols=ALLOWED_ASSET_SCHEMES, allow_redirects=False)
        self._assets: dict[str, tuple[bytes, str]] = {}

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> URLFetcherResponse:
        cached = self._assets.get(url)
        if cached is None:
            with closing(super().fetch(url, headers)) as response:
                cached = (response.read(), response.headers.get("Content-Type", ""))
            # Only this module's own fixed set of assets is ever cached; the
            # bound keeps a template that one day interpolates caller data
            # into a data URI from growing the map without limit.
            if len(self._assets) < MAX_CACHED_ASSETS:
                self._assets[url] = cached
        body, content_type = cached
        return URLFetcherResponse(url, body=body, headers={"Content-Type": content_type})


@lru_cache(maxsize=1)
def _asset_fetcher() -> ReportAssetFetcher:
    return ReportAssetFetcher()


# WeasyPrint's documented in-memory image cache. Held per process so the
# watermarks and faces are parsed once rather than once per document.
_image_cache: dict[str, object] = {}


def render_pdf_document(html: str) -> bytes:
    """Render one already-rendered HTML document to PDF bytes.

    Runs in the request thread or in a renderer subprocess, so it takes a
    string rather than report data: a worker never needs the database, the
    settings for a card, or anything else the parent already resolved.
    """
    return HTML(string=html, base_url=str(HERE), url_fetcher=_asset_fetcher()).write_pdf(
        cache=_image_cache
    )


def _merge_pdf_parts(parts: list[bytes]) -> bytes:
    """Join the part PDFs in order while preserving the document metadata."""
    writer = PdfWriter()
    metadata: dict[str, str] = {}
    for index, part in enumerate(parts):
        reader = PdfReader(BytesIO(part))
        if index == 0 and reader.metadata:
            metadata = {
                key: str(value)
                for key, value in reader.metadata.items()
                if isinstance(key, str) and value is not None
            }
        for page in reader.pages:
            writer.add_page(page)
    if metadata:
        writer.add_metadata(metadata)
    # The parts embed the same font subsets and the same watermark, so the
    # merged file is meaningfully smaller once the duplicates are folded away.
    writer.compress_identical_objects()
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _cgroup_cpu_limit() -> float | None:
    """The container's CPU quota, or ``None`` when it is not limited.

    ``os.process_cpu_count`` reports the host's CPUs even inside a container
    capped at a fraction of one, and this deploys to small managed instances.
    Sizing the pool to the host there would oversubscribe the quota and make
    the render slower than doing it serially.
    """
    try:
        quota_text, period_text = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        return None if quota_text == "max" else int(quota_text) / int(period_text)
    except (OSError, ValueError):
        pass
    try:
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
    except (OSError, ValueError):
        return None
    return quota / period if quota > 0 and period > 0 else None


def render_worker_limit() -> int:
    """How many renderer processes this host may use, at most."""
    if settings.report_render_workers:
        return max(1, settings.report_render_workers)
    available = float(os.process_cpu_count() or 1)
    quota = _cgroup_cpu_limit()
    if quota is not None:
        available = min(available, quota)
    return max(1, min(MAX_RENDER_WORKERS, int(available)))


_pool_lock = Lock()
_pool: tuple[int, Executor] | None = None


def _render_pool(workers: int) -> Executor | None:
    """A warm renderer pool for this process, or ``None`` if none can exist.

    Keyed on the pid so a server that forks its workers after a render never
    hands a child an executor whose processes belong to the parent. A pool is
    not always possible — a daemonic worker process may not have children —
    so callers must be able to fall back to rendering serially.
    """
    global _pool
    with _pool_lock:
        if _pool is not None:
            owner, pool = _pool
            if owner == os.getpid():
                return pool
            _pool = None
        try:
            # forkserver, not fork: the API process is multi-threaded, and a
            # child forked from it can inherit a held lock and deadlock. Not
            # spawn either, which re-imports WeasyPrint for every worker.
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("forkserver"))
        except (OSError, ValueError, AssertionError, NotImplementedError):
            return None
        _pool = (os.getpid(), pool)
        return pool


def _discard_pool() -> None:
    """Drop a pool that broke so the next request builds a fresh one."""
    global _pool
    with _pool_lock:
        if _pool is None:
            return
        _, pool = _pool
        _pool = None
    pool.shutdown(wait=False)


def _chunk(units: list[object], count: int) -> list[list[object]]:
    """Split the sheets into ``count`` contiguous, evenly sized slices."""
    size, extra = divmod(len(units), count)
    chunks: list[list[object]] = []
    start = 0
    for index in range(count):
        stop = start + size + (1 if index < extra else 0)
        if stop > start:
            chunks.append(units[start:stop])
        start = stop
    return chunks


def render_report_pdf(cards: list[ReportCard]) -> bytes:
    """Render a report set, laying its sheets out in parallel when that helps.

    Every ``.sheet`` in these templates is a self-contained, fixed-height page
    (or duplex page pair) that never flows into its neighbour, so slicing the
    sheet list and concatenating the resulting PDFs reproduces the single
    document exactly — including the guillotine imposition, which is computed
    over the whole set before any slicing happens. Splitting by sheet rather
    than by class means a single-class set is parallelised too, and that
    unequal class sizes do not leave workers idle.

    Falls back to one serial document whenever a pool is unavailable or dies,
    because a slow report card is recoverable and a failed one is not.
    """
    template, context, units_key, units = _document_plan(cards)
    jinja_template = _template_environment().get_template(template)

    def document(sheets: list[object]) -> str:
        return jinja_template.render(**context, **{units_key: sheets})

    workers = render_worker_limit()
    if workers < 2 or len(units) < MIN_PARALLEL_UNITS:
        return _apply_back_cover(render_pdf_document(document(units)), cards)

    pool = _render_pool(workers)
    if pool is None:
        return _apply_back_cover(render_pdf_document(document(units)), cards)
    chunks = _chunk(units, min(workers, len(units)))
    try:
        parts = list(pool.map(render_pdf_document, [document(chunk) for chunk in chunks]))
    except Exception:
        # Deliberately broad: a pool can fail for reasons that have nothing to
        # do with this report — a killed worker, a host that forbids child
        # processes — and a report card that arrives slowly beats one that
        # does not arrive. A fault in the document itself still surfaces,
        # because the serial retry below renders the very same HTML.
        logger.warning("parallel report render failed, falling back to serial", exc_info=True)
        _discard_pool()
        return _apply_back_cover(render_pdf_document(document(units)), cards)
    return _apply_back_cover(_merge_pdf_parts(parts), cards)
