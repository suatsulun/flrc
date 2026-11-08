import base64
import gc
import json
import multiprocessing
import os
import struct
import sys
import threading
import time
import zipfile
from io import BytesIO
from multiprocessing.connection import Connection
from pathlib import Path
from types import FunctionType, ModuleType

import pytest
from jinja2.exceptions import SecurityError
from PIL import Image
from pypdf import PdfReader, PdfWriter

from flrc.config import settings
from flrc.modules.reports import packaging, render
from flrc.modules.reports.branding import contained_file, report_branding
from flrc.modules.reports.builder import ReportEntry
from flrc.modules.reports.models import ReportCard, ReportSigner


@pytest.fixture
def overlay(tmp_path, monkeypatch):
    root = tmp_path / "branding"
    reports = root / "reports"
    (reports / "templates").mkdir(parents=True)
    (root / "brand.json").write_text('{"name":"Synthetic School","accentColor":"#123456"}')
    (root / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (reports / "principal.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    config = {
        "version": 1,
        "templates": {"german_karne": "private.html", "french_karne": "private.html"},
        "principals": {
            "primary": {"name": "Synthetic Elementary Principal", "signature": "principal.svg"},
            "middle": {"name": "Synthetic Middle Principal", "signature": "principal.svg"},
        },
    }
    (reports / "config.json").write_text(json.dumps(config))
    (reports / "templates" / "private.html").write_text("""
{% extends "base.html" %}
{% block page_size %}A4 landscape{% endblock %}
{% block sheet_width %}297mm{% endblock %}
{% block sheet_height %}210mm{% endblock %}
{% block sheets %}{% for sheet in sheets %}
<section class="sheet"><p>{{ sheet.card.student_name }}</p>
{% set p = report_branding.principals['primary' if sheet.card.grade_level <= 4 else 'middle'] %}
<p>{{ p.name }}</p><img src="{{ p.signature }}" />
{% for teacher in sheet.card.teachers %}<p>{{ teacher.name }}</p>
{% if teacher.signature %}<img src="{{ teacher.signature }}" />{% endif %}{% endfor %}
{% if 'stamp' in report_branding.assets %}<img src="{{ report_branding.assets.stamp }}" />
{% endif %}</section>
<section class="sheet"><p>HTML cover placeholder</p></section>
{% endfor %}{% endblock %}
""")
    monkeypatch.setattr(settings, "school_branding_dir", str(root))
    monkeypatch.setattr(settings, "school_name", "")
    monkeypatch.setattr(settings, "school_logo_path", "")
    monkeypatch.setattr(settings, "report_render_workers", 1)
    render.school_brand.cache_clear()
    render.school_logo_data_uri.cache_clear()
    yield reports, config
    render.school_brand.cache_clear()
    render.school_logo_data_uri.cache_clear()


def card(grade=4, subject="german"):
    return ReportCard(
        kind=subject + "_karne",
        locale="tr",
        year_label="Synthetic Year",
        semester_number=1,
        grade_level=grade,
        class_name=f"{grade}/A",
        school_number=grade * 100,
        student_name=f"Synthetic Student {grade}",
        subject=subject,
        subject_label=subject,
        fields=[],
        average=None,
        teachers=[ReportSigner(user_id=1, name="Synthetic Teacher <script>", roles=[subject])],
    )


@pytest.mark.parametrize("subject", ["german", "french"])
def test_overlay_uses_grade_principal_and_escapes_names(overlay, subject):
    primary = render.render_report_html([card(4, subject)])
    middle = render.render_report_html([card(5, subject)])
    assert "Synthetic Elementary Principal" in primary
    assert "Synthetic Middle Principal" not in primary
    assert "Synthetic Middle Principal" in middle
    assert "Synthetic Elementary Principal" not in middle
    assert "Synthetic Teacher &lt;script&gt;" in primary
    assert "<script>" not in primary
    pdf = PdfReader(BytesIO(render.render_report_pdf([card(4, subject), card(5, subject)])))
    assert len(pdf.pages) == 4
    assert "Elementary Principal" in pdf.pages[0].extract_text()
    assert "Middle Principal" in pdf.pages[2].extract_text()


def test_cover_pdf_replaces_every_back_and_keeps_front_order(overlay):
    reports, config = overlay
    cover_bytes = render.render_pdf_document(
        "<style>@page {size:A4 landscape}</style><p>SYNTHETIC ORIGINAL COVER</p>"
    )
    (reports / "cover.pdf").write_bytes(cover_bytes)
    config["covers"] = {"german_karne": "cover.pdf"}
    (reports / "config.json").write_text(json.dumps(config))
    pdf = PdfReader(BytesIO(render.render_report_pdf([card(4), card(5)])))
    assert len(pdf.pages) == 4
    assert "Student 4" in pdf.pages[0].extract_text()
    assert "Student 5" in pdf.pages[2].extract_text()
    for page in (pdf.pages[1], pdf.pages[3]):
        assert "SYNTHETIC ORIGINAL COVER" in page.extract_text()
        assert "placeholder" not in page.extract_text()
        assert 840 < float(page.mediabox.width) < 844


def test_wrong_cover_size_fails_instead_of_printing_misaligned(overlay):
    reports, config = overlay
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(reports / "cover.pdf")
    config["covers"] = {"german_karne": "cover.pdf"}
    (reports / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="report_cover_page_size"):
        render.render_report_pdf([card()])


def test_private_template_cannot_access_python_internals(overlay):
    reports, _ = overlay
    (reports / "templates" / "private.html").write_text("{{ sheets[0].card.__class__.__mro__ }}")
    with pytest.raises(SecurityError):
        render.render_report_html([card()])


def test_overlay_rejects_path_traversal_absolute_and_symlink(overlay, tmp_path):
    reports, _ = overlay
    secret = tmp_path / "outside.png"
    secret.write_bytes(b"outside")
    (reports / "linked.png").symlink_to(secret)
    for relative in ("../../outside.png", str(secret), "linked.png"):
        with pytest.raises(ValueError, match="report_asset_outside_branding"):
            contained_file(reports, relative)
    (reports / "templates" / "escape.html").symlink_to(secret)
    with pytest.raises(ValueError, match="report_asset_outside_branding"):
        report_branding().environment(Path(render.HERE) / "templates")


def test_no_overlay_preserves_generic_templates(monkeypatch):
    monkeypatch.setattr(settings, "school_branding_dir", "")
    assert report_branding() is None
    html = render.render_report_html([card()])
    assert "Synthetic Elementary Principal" not in html
    assert 'class="cover-frame"' in html


def png_bytes(color: str) -> bytes:
    image = BytesIO()
    Image.new("RGB", (60, 20), color).save(image, format="PNG")
    return image.getvalue()


def reachable(roots: list[object]) -> list[object]:
    """Every object reachable from ``roots``, short of modules, functions and classes."""
    seen: set[int] = set()
    found: list[object] = []
    stack = list(roots)
    while stack:
        item = stack.pop()
        if id(item) in seen or isinstance(item, ModuleType | FunctionType | type):
            continue
        seen.add(id(item))
        found.append(item)
        stack.extend(gc.get_referents(item))
    return found


# Colours unique to each case, so the artwork is new to the process every time.
@pytest.mark.parametrize(
    ("path", "signature_color", "stamp_color"),
    [("direct", "navy", "silver"), ("parallel", "teal", "gold"), ("job", "maroon", "olive")],
)
def test_teacher_signatures_never_outlive_the_render_that_prints_them(
    overlay, tmp_path, monkeypatch, path, signature_color, stamp_color
):
    """Nothing a process keeps after a render leads to a teacher's signature (ADR-080).

    The school's fixed artwork — an SVG principal signature and a raster stamp, both new to
    this process — is still memoised, as bytes.
    """
    reports, config = overlay
    (reports / "principal.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg"><desc>{path}</desc></svg>'
    )
    stamp = png_bytes(stamp_color)
    (reports / "stamp.png").write_bytes(stamp)
    config["assets"] = {"stamp": "stamp.png"}
    (reports / "config.json").write_text(json.dumps(config))
    monkeypatch.setattr(render, "_fetched_assets", {})
    png = png_bytes(signature_color)
    signature = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    signed = card()
    signed.teachers[0].signature = signature

    if path == "job":
        render.render_cards_to_file([signed], tmp_path / "class.pdf")
        pdf = PdfReader(tmp_path / "class.pdf")
    else:
        if path == "parallel":

            def inline_wave(render_document, documents, deadline):
                return [render_document(document) for document in documents]

            monkeypatch.setattr(settings, "report_render_workers", 2)
            monkeypatch.setattr(render, "MIN_PARALLEL_UNITS", 2)
            monkeypatch.setattr(render, "_render_wave", inline_wave)
        pdf = PdfReader(BytesIO(render.render_report_pdf([signed, signed])))
    gc.collect()

    assert len(pdf.pages[0].images) == 2, "the stamp and the teacher's signature are printed"
    kept = reachable(
        [
            value
            for name, value in vars(render).items()
            if isinstance(value, dict) and not name.startswith("__")
        ]
    )
    assert stamp in kept
    assert (reports / "principal.svg").read_bytes() in kept
    assert not [item for item in kept if isinstance(item, str) and item == signature]
    assert not [item for item in kept if isinstance(item, bytes) and item == png]


def holders_of(needle: bytes) -> list[str]:
    """What, in this process, still holds ``needle``: objects, and other threads' frames."""
    text = needle.decode()

    def holds(value: object) -> bool:
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes | bytearray):
            return value is not needle and needle in value
        return isinstance(value, str) and value is not text and text in value

    found = [
        type(item).__name__
        for item in gc.get_objects()
        if any(holds(referent) for referent in gc.get_referents(item))
    ]
    for ident, frame in sys._current_frames().items():
        if ident == threading.get_ident():
            continue
        while frame is not None:
            if any(holds(value) for value in frame.f_locals.values()):
                found.append(f"{frame.f_code.co_name} frame")
            frame = frame.f_back
    return found


def record_waves(monkeypatch) -> list[str]:
    """How each render wave ended: ``"rendered"`` or the exception's class name."""
    outcomes: list[str] = []
    original = render._render_wave

    def recorded(render_document, documents, deadline):
        try:
            rendered = original(render_document, documents, deadline)
        except Exception as exc:
            outcomes.append(type(exc).__name__)
            raise
        outcomes.append("rendered")
        return rendered

    monkeypatch.setattr(render, "_render_wave", recorded)
    return outcomes


def test_real_render_processes_keep_no_signature_after_the_render(overlay, monkeypatch):
    """After a render through real render processes, none is left and nothing holds a signature.

    An executor's queue threads kept the last document they were sent; render processes
    end with their documents (ADR-080).
    """
    needle = base64.b64encode(png_bytes("purple"))
    signed = card()
    signed.teachers[0].signature = "data:image/png;base64," + needle.decode()
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(settings, "report_render_workers", 2)
    monkeypatch.setattr(render, "MIN_PARALLEL_UNITS", 2)
    waves = record_waves(monkeypatch)
    pdf = PdfReader(BytesIO(render.render_report_pdf([signed, signed])))
    assert waves == ["rendered"]
    assert len(pdf.pages[0].images) == 1, "the teacher's signature is printed"

    del signed
    gc.collect()
    assert {child.pid for child in multiprocessing.active_children()} - before == set()
    assert holders_of(needle) == []


REAL_RENDER = render.render_pdf_document


def dies_while_sending(html: str, private_assets: frozenset[str] = frozenset()) -> bytes:
    """In a render process: start sending a large result to the parent, then die.

    Writes a length header announcing far more than follows to every write-only pipe the
    process holds, as an interrupted send leaves it, and exits without any cleanup. In
    this test process — the serial fallback — it renders normally.
    """
    if multiprocessing.parent_process() is None:
        return REAL_RENDER(html, private_assets)
    for item in gc.get_objects():
        if isinstance(item, Connection) and item.writable and not item.readable:
            if not item.closed:
                os.write(item.fileno(), struct.pack("!i", 64 * 1024 * 1024) + b"%PDF-1.7 partial")
    os._exit(1)


def test_a_render_process_dying_mid_result_fails_promptly_and_keeps_nothing(overlay, monkeypatch):
    """A render process killed while sending its PDF never leaves the render waiting.

    The parent sees end of file on that process's own pipe at once, falls back to the
    serial render, and keeps neither the process nor the documents it was sent.
    """
    needle = base64.b64encode(png_bytes("orange"))
    signed = card()
    signed.teachers[0].signature = "data:image/png;base64," + needle.decode()
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(settings, "report_render_workers", 2)
    monkeypatch.setattr(render, "MIN_PARALLEL_UNITS", 2)
    monkeypatch.setattr(render, "RENDER_DEADLINE_SECONDS", 3)
    monkeypatch.setattr(render, "render_pdf_document", dies_while_sending)
    waves = record_waves(monkeypatch)

    started = time.monotonic()
    pdf = PdfReader(BytesIO(render.render_report_pdf([signed, signed])))
    assert time.monotonic() - started < 2.5, "the render did not wait for its deadline"
    assert waves == ["_RenderProcessFailed"], "the wave failed, then the render went serial"
    assert len(pdf.pages[0].images) == 1, "the serial render printed the card"

    del signed
    gc.collect()
    assert {child.pid for child in multiprocessing.active_children()} - before == set()
    assert holders_of(needle) == []


def cover_overlay(reports, config) -> None:
    cover_bytes = render.render_pdf_document(
        "<style>@page {size:A4 landscape}</style><p>SYNTHETIC ORIGINAL COVER</p>"
    )
    (reports / "cover.pdf").write_bytes(cover_bytes)
    config["covers"] = {"german_karne": "cover.pdf"}
    (reports / "config.json").write_text(json.dumps(config))


def karne_classes() -> list[packaging.ClassSet]:
    return [
        packaging.ClassSet(
            class_id=grade,
            entries=[
                ReportEntry(
                    class_id=grade,
                    student_id=grade * 10 + pupil,
                    card=card(grade).model_copy(
                        update={"student_name": f"Synthetic Pupil {grade}-{pupil}"}
                    ),
                )
                for pupil in (1, 2)
            ],
        )
        for grade in (4, 5, 6)
    ]


def test_combined_set_takes_the_back_cover_once_and_class_files_keep_theirs(overlay, monkeypatch):
    reports, config = overlay
    cover_overlay(reports, config)
    opened: list[str] = []
    original = render.contained_file

    def counting(root, relative):
        opened.append(relative)
        return original(root, relative)

    monkeypatch.setattr(render, "contained_file", counting)
    combined = PdfReader(BytesIO(packaging.package_report_set(karne_classes(), "combined").data))
    # The cover is read once, for the merged document, not once per class.
    assert opened == ["cover.pdf"]
    assert len(combined.pages) == 12
    for index, page in enumerate(combined.pages):
        text = page.extract_text()
        if index % 2:
            assert "SYNTHETIC ORIGINAL COVER" in text and "placeholder" not in text
        else:
            grade, pupil = 4 + index // 4, 1 + (index // 2) % 2
            assert f"Synthetic Pupil {grade}-{pupil}" in text

    opened.clear()
    per_class = packaging.package_report_set(karne_classes(), "per_class").data
    # The set opens the cover once; every class file still carries its own copy of it.
    assert opened == ["cover.pdf"]
    with zipfile.ZipFile(BytesIO(per_class)) as bundle:
        assert len(bundle.namelist()) == 3
        for name in bundle.namelist():
            pages = PdfReader(BytesIO(bundle.read(name))).pages
            assert len(pages) == 4
            for index, page in enumerate(pages):
                text = page.extract_text()
                assert ("SYNTHETIC ORIGINAL COVER" in text) == bool(index % 2)

    per_pupil = packaging.package_report_set(karne_classes(), "per_student").data
    with zipfile.ZipFile(BytesIO(per_pupil)) as bundle:
        names = bundle.namelist()
        assert len(names) == 6
        for name, (grade, pupil) in zip(
            names, [(g, p) for g in (4, 5, 6) for p in (1, 2)], strict=True
        ):
            face, back = PdfReader(BytesIO(bundle.read(name))).pages
            assert f"Synthetic Pupil {grade}-{pupil}" in face.extract_text()
            assert "SYNTHETIC ORIGINAL COVER" not in face.extract_text()
            assert "SYNTHETIC ORIGINAL COVER" in back.extract_text()


def test_every_path_keeps_the_card_and_cover_page_geometry(overlay):
    """Faces keep the card's A4 box and backs keep the school cover's own box, as before.

    The cover here is 841.92 x 595.2 pt, a few hundredths off the card's 841.89 x 595.28 pt and
    within the size tolerance: direct downloads and every job format must agree page for page.
    """
    reports, config = overlay
    cover = PdfWriter()
    cover.add_blank_page(841.92, 595.2)
    cover.write(reports / "cover.pdf")
    config["covers"] = {"german_karne": "cover.pdf"}
    (reports / "config.json").write_text(json.dumps(config))
    face_box = (0.0, 0.0, 841.889764, 595.275591)
    back_box = (0.0, 0.0, 841.92, 595.2)

    def boxes(data: bytes) -> list[tuple[float, ...]]:
        return [
            tuple(round(float(value), 6) for value in page.mediabox)
            for page in PdfReader(BytesIO(data)).pages
        ]

    def zipped(data: bytes) -> list[bytes]:
        with zipfile.ZipFile(BytesIO(data)) as bundle:
            return [bundle.read(name) for name in bundle.namelist()]

    classes = karne_classes()
    direct = render.render_report_pdf([entry.card for entry in classes[0].entries])
    combined = packaging.package_report_set(classes, "combined").data
    per_class = zipped(packaging.package_report_set(karne_classes(), "per_class").data)
    per_pupil = zipped(packaging.package_report_set(karne_classes(), "per_student").data)
    for document in [direct, combined, *per_class, *per_pupil]:
        pages = boxes(document)
        assert pages[0::2] == [face_box] * (len(pages) // 2)
        assert pages[1::2] == [back_box] * (len(pages) // 2)
