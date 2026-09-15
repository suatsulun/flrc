"""Hazırlık classes: grade 0 with a name instead of a letter section (ADR-065)."""

import io

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.modules.academics.class_names import PREP_GRADE, class_label, normalize_section
from flrc.modules.imports.parser import parse_class
from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.render import primary_sheet
from tests.conftest import TEST_URL_SYNC, TestSession


def test_class_label_names_prep_classes_and_numbers_the_rest() -> None:
    assert class_label(PREP_GRADE, "Bulut") == "Bulut"
    assert class_label(5, "A") == "5/A"


def test_section_spelling_follows_the_grade() -> None:
    assert normalize_section(5, " a ") == "A"
    assert normalize_section(5, "i") == "İ"
    assert normalize_section(PREP_GRADE, "yıldız") == "Yıldız"
    assert normalize_section(PREP_GRADE, "GÜNEŞ") == "Güneş"
    assert normalize_section(PREP_GRADE, "IŞIK") == "Işık"
    assert normalize_section(PREP_GRADE, "gök  kuşağı ") == "Gök Kuşağı"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5/A", (5, "A")),
        ("5-a", (5, "A")),
        ("Bulut", (PREP_GRADE, "Bulut")),
        ("bulut", (PREP_GRADE, "Bulut")),
        ("Hazırlık Yıldız", (PREP_GRADE, "Yıldız")),
        ("HAZIRLIK/GÜNEŞ", (PREP_GRADE, "Güneş")),
        ("Hazirlik-Bulut", (PREP_GRADE, "Bulut")),
        ("Hazırlık/Gök Kuşağı", (PREP_GRADE, "Gök Kuşağı")),
        ("Hazırlık", None),
        ("A", None),
        ("5/AB", None),
        ("9/A", None),
        ("Bulut 2", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_class_reads_numbered_and_prep_classes(value, expected) -> None:
    assert parse_class(value) == expected


def test_worksheet_titles_need_the_prep_prefix() -> None:
    assert parse_class("Students", bare_prep_name=False) is None
    assert parse_class("Hazırlık Bulut", bare_prep_name=False) == (PREP_GRADE, "Bulut")
    assert parse_class("5-A", bare_prep_name=False) == (5, "A")


async def test_admin_creates_named_prep_classes_listed_before_grade_one(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/classes",
            json={"year_id": world.year, "grade_level": PREP_GRADE, "section": "bulut"},
        )
        assert created.status_code == 201, created.text
        assert (created.json()["section"], created.json()["name"]) == ("Bulut", "Bulut")
        duplicate = await client.post(
            "/api/admin/classes",
            json={"year_id": world.year, "grade_level": PREP_GRADE, "section": "BULUT"},
        )
        assert duplicate.status_code == 409
        too_high = await client.post(
            "/api/admin/classes",
            json={"year_id": world.year, "grade_level": 9, "section": "A"},
        )
        blank = await client.post(
            "/api/admin/classes",
            json={"year_id": world.year, "grade_level": PREP_GRADE, "section": "   "},
        )
        assert (too_high.status_code, blank.status_code) == (422, 422)
        renamed = await client.patch(
            f"/api/admin/classes/{created.json()['id']}", json={"section": "yıldız"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Yıldız"
        listed = await client.get(f"/api/admin/years/{world.year}/classes")
        assert [item["name"] for item in listed.json()] == ["Yıldız", "5/A"]


def prep_roster_file() -> dict[str, tuple[str, bytes]]:
    workbook = Workbook()
    titled = workbook.active
    # A class-per-sheet file names the class in the title, hyphenated (ADR-023).
    titled.title = "Hazırlık-Bulut"
    titled.append(["Okul No", "Ad Soyad"])
    titled.append([80001, "Synthetic Prep One"])
    titled.append([80002, "Synthetic Prep Two"])
    combined = workbook.create_sheet("Liste")
    combined.append(["Okul No", "Ad Soyad", "Sınıf/Şube"])
    combined.append([80003, "Synthetic Prep Three", "yıldız"])
    combined.append([80004, "Synthetic Prep Four", "Hazırlık Güneş"])
    combined.append([80005, "Synthetic Pupil Five", "5/A"])
    split = workbook.create_sheet("Ayrık")
    split.append(["Okul No", "Ad Soyad", "Sınıf", "Şube"])
    split.append([80006, "Synthetic Prep Six", "Hazırlık", "Bulut"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return {"file": ("synthetic-prep.xlsx", buffer.getvalue())}


async def test_import_reads_prep_classes_from_titles_cells_and_split_columns(api, world):
    files = prep_roster_file()
    expected = [(PREP_GRADE, "Bulut"), (PREP_GRADE, "Güneş"), (PREP_GRADE, "Yıldız"), (5, "A")]
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert [issue for issue in body["issues"] if issue["level"] == "error"] == []
        assert [(item["grade_level"], item["section"]) for item in body["classes"]] == expected
        bulut = next(row for row in body["rows"] if row["row"]["school_number"] == 80001)
        assert (bulut["original_grade_level"], bulut["original_section"]) == (PREP_GRADE, "Bulut")
        assert bulut["original_class"] == "Bulut"
        filtered = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "grade_level": PREP_GRADE, "section": "bulut"},
            files=files,
        )
        assert filtered.json()["filtered_rows"] == 3
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": body["sha256"],
                "expected_review_sha256": body["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text
    async with TestSession() as db:
        rows = (
            await db.execute(
                select(m.SchoolClass.grade_level, m.SchoolClass.section)
                .where(m.SchoolClass.year_id == world.year)
                .order_by(m.SchoolClass.grade_level, m.SchoolClass.section)
            )
        ).all()
    assert [tuple(row) for row in rows] == expected


async def test_prep_classes_get_the_primary_english_card(world):
    async with TestSession() as db:
        prep = m.SchoolClass(year_id=world.year, grade_level=PREP_GRADE, section="Bulut")
        db.add(prep)
        await db.flush()
        column = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=PREP_GRADE,
            subject="english",
            value_type="scale3",
            owner_role="main",
            labels={"tr": "Dinler", "en": "Listens"},
            position=1,
        )
        pupil = m.Student(full_name="Synthetic Prep Pupil", search_name="synthetic prep pupil")
        db.add_all([column, pupil])
        await db.flush()
        db.add(
            m.Enrollment(
                student_id=pupil.id, class_id=prep.id, year_id=world.year, school_number=51101
            )
        )
        await db.commit()
    engine = create_engine(TEST_URL_SYNC)
    try:
        with Session(engine) as db:
            cards = build_report_set(
                db, semester_id=world.semester, kind="english_elementary", locale="tr"
            )
    finally:
        engine.dispose()
    assert [(card.class_name, card.grade_level) for card in cards] == [("Bulut", PREP_GRADE)]
    assert [field.label for field in cards[0].fields] == ["Dinler"]
    sheet = primary_sheet(cards[0])
    assert sheet["title_tr"] == "Synthetic year Hazırlık Sınıfı"
    assert sheet["title_en"] == (
        "Synthetic year Preparatory Class 1st Term English Progress Report"
    )
