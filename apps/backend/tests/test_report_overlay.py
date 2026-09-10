import json
from io import BytesIO
from pathlib import Path

import pytest
from jinja2.exceptions import SecurityError
from pypdf import PdfReader, PdfWriter

from flrc.config import settings
from flrc.modules.reports import render
from flrc.modules.reports.branding import contained_file, report_branding
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
{% for teacher in sheet.card.teachers %}<p>{{ teacher.name }}</p>{% endfor %}</section>
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
