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
import gc
import json
import logging
import math
import mimetypes
import os
import time
from collections.abc import Iterator
from concurrent.futures import Executor, ProcessPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import lru_cache, partial
from io import BytesIO
from multiprocessing import get_context
from multiprocessing.context import BaseContext
from pathlib import Path
from threading import Condition
from typing import Literal, cast
from urllib.parse import quote

import pikepdf
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter, Transformation
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

from flrc.config import settings
from flrc.modules.academics.class_names import is_prep
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
# Bound layout memory even when a school has hundreds of duplex report cards.
MAX_RENDER_UNITS = 16
# A report job renders a class inside one render process; smaller batches keep each process's
# peak down when every card carries artwork (ADR-077 measurements).
JOB_RENDER_UNITS = 8
# A parallel render that has not finished by then has a stuck worker: its pool is stopped
# and the render fails, so the shared process budget is never held for good. Generous:
# a whole class renders in seconds on the deployment-sized host.
RENDER_DEADLINE_SECONDS = 10 * 60
# How long a stopped worker gets to exit after SIGTERM, and again after SIGKILL.
STOPPED_WORKER_GRACE_SECONDS = 5
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
        "comments": [],
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
    # Hazırlık is the year before grade 1: the cover names it, never "0th Grade".
    if is_prep(card.grade_level):
        class_year_tr, class_year_en = "Hazırlık Sınıfı", "Preparatory Class"
    else:
        class_year_tr = f"{card.grade_level}. Sınıf"
        class_year_en = f"{ordinal_en(card.grade_level)} Grade"
    scored = [field for field in card.fields if field.value_type != "text"]
    left, right = _split_for_columns(consecutive_blocks(scored))
    return {
        "card": card,
        "left": left,
        "right": right,
        "comments": _comments(card),
        "title_tr": f"{card.year_label} {class_year_tr}",
        "title_en": (
            f"{card.year_label} {class_year_en} "
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


def _document_plan(
    cards: list[ReportCard], one_card_per_sheet: bool = False
) -> tuple[str, dict[str, object], str, list[object]]:
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
        # One card per sheet lets a set be split into exactly one student per page.
        if one_card_per_sheet:
            return (
                template,
                context,
                "pages",
                [{"top": middle_sheet(card), "bottom": None} for card in cards],
            )
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


def back_cover_file(kind: str) -> Path | None:
    """The school's original back-cover PDF for this card kind, if its overlay has one."""
    branding = report_branding()
    if branding is None:
        return None
    relative = branding.config.covers.get(cast(Literal["german_karne", "french_karne"], kind))
    return None if relative is None else contained_file(branding.root, relative)


def _page_size(page: pikepdf.Page) -> tuple[float, float]:
    box = page.mediabox
    return float(box[2]) - float(box[0]), float(box[3]) - float(box[1])


def cover_duplex_backs(document: pikepdf.Pdf, cover: pikepdf.Pdf) -> None:
    """Replace every second page of ``document`` with the cover's single page, in place.

    qpdf copies the cover's objects into ``document`` once and every back shares them, so a
    set carries the cover once however many cards it holds. ``cover`` must stay open until
    ``document`` is saved: its streams are read while writing.
    """
    if len(cover.pages) != 1 or len(document.pages) % 2:
        raise ValueError("report_duplex_page_count")
    back = cover.pages[0]
    back_width, back_height = _page_size(back)
    for index in range(1, len(document.pages), 2):
        face_width, face_height = _page_size(document.pages[index - 1])
        if abs(face_width - back_width) > 2 or abs(face_height - back_height) > 2:
            raise ValueError("report_cover_page_size")
        document.pages[index] = back


def apply_back_cover(pdf: bytes, cards: list[ReportCard]) -> bytes:
    """Replace each duplex back with the original school PDF, without rasterizing it.

    ``cards`` are the cards ``pdf`` holds, in order; a set merged from several classes takes
    the cover once here instead of once per class (ADR-077).
    """
    cover_file = back_cover_file(cards[0].kind)
    if cover_file is None:
        return pdf
    with pikepdf.open(BytesIO(pdf)) as document, pikepdf.open(cover_file) as cover:
        if len(document.pages) != 2 * len(cards):
            raise ValueError("report_duplex_page_count")
        cover_duplex_backs(document, cover)
        result = BytesIO()
        document.save(result)
    return result.getvalue()


# On-screen previews carry this mark so they are never mistaken for an issued card (ADR-078).
# Its size follows the card it covers: a tenth of the diagonal fits the word along it.
WATERMARK_SIZE_PER_DIAGONAL = 0.1


@lru_cache(maxsize=8)
def _watermark_page(text: str, width: float, height: float, two_up: bool) -> bytes:
    """A one-page PDF of ``width`` x ``height`` points with ``text`` across each card.

    A two-up middle-school sheet holds two A5 cards, one per half, so each half
    gets its own mark centred on that card.
    """
    card_height = height / 2 if two_up else height
    diagonal = math.hypot(width, card_height)
    size = round(diagonal * WATERMARK_SIZE_PER_DIAGONAL, 2)
    angle = round(-math.degrees(math.atan2(card_height, width)), 2)
    marks = [
        {
            "left": round(width / 2 - diagonal / 2, 2),
            "top": round(top + card_height / 2 - size / 2, 2),
            "width": round(diagonal, 2),
            "size": size,
            "angle": angle,
        }
        for top in ((0.0, card_height) if two_up else (0.0,))
    ]
    html = env.get_template("preview_watermark.html").render(
        width=width, height=height, text=text, marks=marks
    )
    return render_pdf_document(html)


def _stamp_watermark(pdf: bytes, text: str, *, two_up: bool) -> bytes:
    """Lay the diagonal ``text`` over every page, back covers included."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))
    for page in writer.pages:
        box = page.mediabox
        width, height = round(float(box.width), 2), round(float(box.height), 2)
        stamp = PdfReader(BytesIO(_watermark_page(text, width, height, two_up))).pages[0]
        page.merge_transformed_page(
            stamp, Transformation().translate(float(box.left), float(box.bottom))
        )
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def _finish_report(
    pdf: bytes, cards: list[ReportCard], watermark: str | None, back_cover: bool
) -> bytes:
    if back_cover:
        pdf = apply_back_cover(pdf, cards)
    if watermark is None:
        return pdf
    return _stamp_watermark(pdf, watermark, two_up=cards[0].kind == "english_middle")


class ReportAssetFetcher(URLFetcher):
    """Deny-by-default asset fetcher for the report templates.

    The cards embed every asset they need — the logo, the rating faces, the
    landmark watermarks — as ``data:`` URIs built in this module. Nothing a
    card legitimately references lives on disk or on the network, so every
    other scheme is refused. Without this, a URL that reached a template could
    make the renderer read a local file (``file:``) or reach an internal
    address (``http:``) on behalf of whoever asked for the report.

    Decoded asset bytes are memoised per process, so a set rendered as several
    documents decodes each watermark once per process instead of once per
    document. ``private_assets`` are fetched but never memoised.
    """

    def __init__(self, private_assets: frozenset[str] = frozenset()) -> None:
        super().__init__(allowed_protocols=ALLOWED_ASSET_SCHEMES, allow_redirects=False)
        self._private_assets = private_assets

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> URLFetcherResponse:
        cached = _fetched_assets.get(url)
        if cached is None:
            with closing(super().fetch(url, headers)) as response:
                cached = (response.read(), response.headers.get("Content-Type", ""))
            # Only this module's own fixed set of assets is ever cached; the
            # bound keeps a template that one day interpolates caller data
            # into a data URI from growing the map without limit.
            if url not in self._private_assets and len(_fetched_assets) < MAX_CACHED_ASSETS:
                _fetched_assets[url] = cached
        body, content_type = cached
        return URLFetcherResponse(url, body=body, headers={"Content-Type": content_type})


# The only process-wide memo: the fixed artwork's bytes — logo, faces, watermarks,
# overlay assets — so each is decoded once per process rather than once per document.
# A teacher's signature never enters it: permanent deletion erases it (ADR-080). Parsed
# images stay in WeasyPrint's per-document cache, because they keep the fetcher and that
# cache, and with them the document's signatures; reusing them measured neutral anyway
# (ADR-046).
_fetched_assets: dict[str, tuple[bytes, str]] = {}


def _signature_assets(cards: list[ReportCard]) -> frozenset[str]:
    """The teachers' signature data URIs the cards print, which no process cache may keep."""
    return frozenset(
        teacher.signature for card in cards for teacher in card.teachers if teacher.signature
    )


def render_pdf_document(html: str, private_assets: frozenset[str] = frozenset()) -> bytes:
    """Render one already-rendered HTML document to PDF bytes.

    Runs in the request thread or in a renderer subprocess, so it takes a
    string rather than report data: a worker never needs the database, the
    settings for a card, or anything else the parent already resolved.
    ``private_assets`` — the teachers' signatures — are never memoised; like
    every parsed image, they go with the document.
    """
    try:
        return HTML(
            string=html, base_url=str(HERE), url_fetcher=ReportAssetFetcher(private_assets)
        ).write_pdf()
    finally:
        # WeasyPrint page trees contain cycles; release each batch before the next.
        gc.collect()


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


def render_process_context() -> BaseContext:
    """How report renders start their processes.

    forkserver, not fork: the API process is multi-threaded, and a child forked
    from it can inherit a held lock and deadlock. The server preloads this
    module, so each render's fresh processes start with WeasyPrint imported.
    """
    context = get_context("forkserver")
    context.set_forkserver_preload([__name__])
    return context


def _render_pool(workers: int) -> Executor | None:
    """A renderer pool for one render, or ``None`` if none can exist.

    Never kept between renders: a pool's queue thread and processes hold on to
    the last document they were sent, whose HTML carries pupils' grades and
    teachers' signatures, and shutting the pool down is what releases them
    (ADR-080). A pool is not always possible — a daemonic worker process may
    not have children — so callers must be able to fall back to rendering
    serially.
    """
    try:
        return ProcessPoolExecutor(max_workers=workers, mp_context=render_process_context())
    except (OSError, ValueError, AssertionError, NotImplementedError):
        return None


def _stop_pool(pool: Executor) -> None:
    """Stop a pool whose render passed its deadline, without waiting on a stuck worker."""
    processes = (
        list((pool._processes or {}).values()) if isinstance(pool, ProcessPoolExecutor) else []
    )
    for process in processes:
        process.terminate()
    for process in processes:
        process.join(timeout=STOPPED_WORKER_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(timeout=STOPPED_WORKER_GRACE_SECONDS)
    pool.shutdown(wait=False, cancel_futures=True)


class _ProcessBudget:
    """How many renderer processes this process may have alive at once, across renders.

    Pools are per render (above), so without a shared budget two concurrent downloads
    would each start ``render_worker_limit()`` processes.
    """

    def __init__(self) -> None:
        self._changed = Condition()
        self._alive = 0

    @contextmanager
    def reserve(self, count: int) -> Iterator[None]:
        """Wait until ``count`` more processes fit the limit; hold them until the block ends."""
        limit = render_worker_limit()
        count = min(count, limit)
        with self._changed:
            self._changed.wait_for(lambda: self._alive + count <= limit)
            self._alive += count
        try:
            yield
        finally:
            with self._changed:
                self._alive -= count
                self._changed.notify_all()


_render_processes = _ProcessBudget()


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


def render_report_pdf(
    cards: list[ReportCard],
    *,
    one_card_per_sheet: bool = False,
    watermark: str | None = None,
    back_cover: bool = True,
) -> bytes:
    """Render a report set, laying its sheets out in parallel when that helps.

    Every ``.sheet`` in these templates is a self-contained, fixed-height page
    (or duplex page pair) that never flows into its neighbour, so slicing the
    sheet list and concatenating the resulting PDFs reproduces the single
    document exactly — including the guillotine imposition, which is computed
    over the whole set before any slicing happens. Splitting by sheet rather
    than by class means a single-class set is parallelised too, and that
    unequal class sizes do not leave workers idle.

    Both parallel rendering and its serial fallback use bounded batches so
    a whole-school request cannot become one enormous WeasyPrint page tree.

    ``watermark`` stamps that text diagonally over every finished page, back
    covers included, for on-screen previews (ADR-078). Official sets leave it
    unset and are rendered exactly as before.
    ``one_card_per_sheet`` prints each middle-school card alone on its sheet
    instead of the guillotine imposition; other card kinds ignore it.
    ``back_cover=False`` leaves the template's own duplex backs in place, page for page, for
    a caller that merges several sets and applies the school's cover once with
    :func:`apply_back_cover`.
    """
    template, context, units_key, units = _document_plan(cards, one_card_per_sheet)
    jinja_template = _template_environment().get_template(template)
    render = partial(render_pdf_document, private_assets=_signature_assets(cards))

    def document(sheets: list[object]) -> str:
        return jinja_template.render(**context, **{units_key: sheets})

    workers = render_worker_limit()
    parallel = workers >= 2 and len(units) >= MIN_PARALLEL_UNITS
    batch_count = (len(units) + MAX_RENDER_UNITS - 1) // MAX_RENDER_UNITS
    chunks = _chunk(units, max(batch_count, min(workers, len(units)) if parallel else 1))

    def serial() -> bytes:
        parts = [render(document(chunk)) for chunk in chunks]
        return parts[0] if len(parts) == 1 else _merge_pdf_parts(parts)

    if not parallel and len(chunks) == 1:
        return _finish_report(render(document(units)), cards, watermark, back_cover)

    if not parallel:
        return _finish_report(serial(), cards, watermark, back_cover)
    parts: list[bytes] | None = None
    timed_out = False
    # Held until the pool has shut down or been stopped, so concurrent renders together
    # never have more renderer processes alive than one render may use.
    with _render_processes.reserve(workers):
        pool = _render_pool(workers)
        if pool is not None:
            deadline = time.monotonic() + RENDER_DEADLINE_SECONDS
            try:
                rendered: list[bytes] = []
                # Submit only one wave at a time; queued HTML also holds embedded images.
                for start in range(0, len(chunks), workers):
                    documents = [document(chunk) for chunk in chunks[start : start + workers]]
                    remaining = max(0.0, deadline - time.monotonic())
                    rendered.extend(pool.map(render, documents, timeout=remaining))
                parts = rendered
            except TimeoutError:
                timed_out = True
            except Exception:
                # Deliberately broad: a pool can fail for reasons that have nothing to
                # do with this report — a killed worker, a host that forbids child
                # processes — and a report card that arrives slowly beats one that
                # does not arrive. A fault in the document itself still surfaces,
                # because the serial retry below renders the very same HTML.
                logger.warning(
                    "parallel report render failed, falling back to serial", exc_info=True
                )
            finally:
                if timed_out:
                    _stop_pool(pool)
                else:
                    # Waits for its processes and threads, which release the documents.
                    pool.shutdown(wait=True)
    if timed_out:
        logger.error("parallel report render passed its deadline; its workers were stopped")
        raise TimeoutError("report_render_timed_out")
    if parts is None:
        return _finish_report(serial(), cards, watermark, back_cover)
    return _finish_report(_merge_pdf_parts(parts), cards, watermark, back_cover)


def concatenate_pdfs(files: list[Path], output: Path) -> None:
    """Join PDFs page by page with qpdf, reading each from disk.

    The first file is the primary input, so the result keeps its title and metadata.
    """
    job = pikepdf.Job(
        ["qpdf", str(files[0]), "--pages", *(str(path) for path in files), "--", str(output)]
    )
    job.run()
    if job.exit_code != 0:
        raise RuntimeError(f"qpdf could not join the PDFs (exit {job.exit_code})")


def render_cards_to_file(
    cards: list[ReportCard], output: Path, *, one_card_per_sheet: bool = False
) -> int:
    """Render a set to ``output`` within this process, in bounded batches; returns its pages.

    The report-job path (ADR-077): one class runs entirely inside a render process, batch by
    batch, and each batch goes to disk before qpdf joins them, so neither this process nor the
    job's worker holds the set's PDF or HTML at once. The school's back cover is not applied.
    """
    template, context, units_key, units = _document_plan(cards, one_card_per_sheet)
    jinja_template = _template_environment().get_template(template)
    signatures = _signature_assets(cards)
    batches = _chunk(units, max(1, -(-len(units) // JOB_RENDER_UNITS)))
    files: list[Path] = []
    for index, batch in enumerate(batches):
        path = output.with_name(f"{output.stem}-batch-{index:03d}.pdf")
        path.write_bytes(
            render_pdf_document(jinja_template.render(**context, **{units_key: batch}), signatures)
        )
        files.append(path)
    if len(files) == 1:
        files[0].replace(output)
    else:
        concatenate_pdfs(files, output)
        for path in files:
            path.unlink()
    with pikepdf.open(output) as document:
        return len(document.pages)
