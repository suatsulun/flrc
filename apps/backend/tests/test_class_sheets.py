from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import select

from flrc.config import settings
from flrc.db import models as m
from flrc.modules.reports.class_sheet import (
    DIGIT_MM_PER_PT,
    VALUE_PADDING_MM,
    ClassSheetOut,
    column_widths,
)
from flrc.modules.reports.render import school_brand
from tests.conftest import TestSession

LONG_NAME = "Synthetic Abdurrahmangazi Karamehmetoğulları Pupil"


async def _fill_class(world, count: int) -> None:
    """Grow the world's 5/A to ``count`` pupils, every fifth with a very long name."""
    async with TestSession() as db:
        for index in range(2, count):
            student = m.Student(
                full_name=f"{LONG_NAME} {index}" if index % 5 == 0 else f"Synthetic Pupil {index}",
                search_name=f"synthetic pupil {index}",
            )
            db.add(student)
            await db.flush()
            db.add(
                m.Enrollment(
                    student_id=student.id,
                    class_id=world.cls,
                    year_id=world.year,
                    school_number=51100 + index,
                )
            )
        await db.commit()


async def test_sheet_lists_english_fields_and_teachers_for_any_teacher(api, world) -> None:
    async with TestSession() as db:
        rating = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="english",
            value_type="scale3",
            owner_role="main",
            labels={"tr": "Katılım", "en": "Participation"},
            group_labels={"tr": "Tutum", "en": "Attitude"},
            position=3,
        )
        retired_note = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="english",
            value_type="text",
            owner_role="main",
            labels={"tr": "Görüş", "en": "Comments"},
            position=4,
        )
        retired_score = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="english",
            value_type="score",
            owner_role="main",
            labels={"tr": "Eski", "en": "Old exam"},
            position=5,
            is_active=False,
        )
        german = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="german",
            value_type="score",
            owner_role="german",
            labels={"tr": "Sınav", "de": "Prüfung"},
            position=1,
        )
        db.add_all([rating, retired_note, retired_score, german])
        await db.flush()
        db.add_all(
            [
                m.GradeValue(
                    student_id=world.student_one,
                    column_definition_id=column,
                    version=1,
                    updated_by=world.main.id,
                    **value,
                )
                for column, value in (
                    (world.main_column, {"score": 88}),
                    (rating.id, {"scale": 3}),
                    (retired_note.id, {"text_value": "Retired synthetic note"}),
                    (retired_score.id, {"score": 12}),
                    (german.id, {"score": 40}),
                )
            ]
        )
        await db.commit()
        rating_id = rating.id

    # An unassigned teacher reads the class like the grid (ADR-071).
    outsider = m.User(id=999_001, email="outsider@example.test", full_name="Outsider")
    async with api(outsider) as client:
        response = await client.get(f"/api/classes/{world.cls}/sheet", params={"semester": 1})
    assert response.status_code == 200
    sheet = response.json()
    assert sheet["class_name"] == "5/A"
    assert sheet["semester_id"] == world.semester
    assert sheet["teachers"] == ["Main Teacher", "Skills Teacher"]
    # English only: no German field, no retired field and no note (ADR-063).
    assert [(c["id"], c["label"], c["group"], c["value_type"]) for c in sheet["columns"]] == [
        (world.main_column, "Main score", None, "score"),
        (world.skills_column, "Skills score", None, "score"),
        (rating_id, "Participation", "Attitude", "scale3"),
    ]
    assert [(s["school_number"], s["full_name"], s["values"]) for s in sheet["students"]] == [
        (51001, "Synthetic Student One", [88, None, 3]),
        (51002, "Synthetic Student Two", [None, None, None]),
    ]


async def test_class_reports_are_for_middle_school_classes_only(api, world) -> None:
    async with TestSession() as db:
        primary = m.SchoolClass(year_id=world.year, grade_level=4, section="A")
        db.add(primary)
        await db.commit()
        primary_id = primary.id
    async with api(world.main) as client:
        preview = await client.get(f"/api/classes/{primary_id}/sheet")
        printed = await client.get(
            "/api/reports/class-sheets",
            params={"semester_id": world.semester, "class_id": [world.cls, primary_id]},
        )
    for response in (preview, printed):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "class_report_middle_english_only"


async def test_catalog_lists_every_assignment_even_without_owned_fields(api, world) -> None:
    """The class report belongs to both English teachers, even when one owns no field."""
    async with TestSession() as db:
        skills_column = await db.get(m.ColumnDefinition, world.skills_column)
        assert skills_column is not None
        skills_column.is_active = False
        await db.commit()
    async with api(world.skills) as client:
        catalog = (await client.get("/api/class-catalog")).json()
    (entry,) = catalog
    assert entry["assigned_roles"] == ["skills"]
    # Field ownership still drives the grid's own shortcuts and warnings.
    assert entry["subjects"][0]["my_roles"] == []
    assert entry["subjects"][0]["can_write"] is False


async def test_a_full_class_prints_on_one_page_and_each_class_on_its_own(api, world) -> None:
    await _fill_class(world, 34)
    async with TestSession() as db:
        empty = m.SchoolClass(year_id=world.year, grade_level=6, section="B")
        second = m.SchoolClass(year_id=world.year, grade_level=7, section="C")
        db.add_all([empty, second])
        await db.flush()
        pupil = m.Student(full_name="Synthetic Seventh Grader", search_name="seventh")
        db.add(pupil)
        await db.flush()
        db.add(
            m.Enrollment(
                student_id=pupil.id, class_id=second.id, year_id=world.year, school_number=7
            )
        )
        await db.commit()
        empty_id, second_id = empty.id, second.id

    params = {"semester_id": world.semester, "locale": "en"}
    async with api(world.main) as client:
        single = await client.get(
            "/api/reports/class-sheets", params=params | {"class_id": world.cls}
        )
        assert single.status_code == 200
        assert single.headers["content-type"].startswith("application/pdf")
        pages = PdfReader(BytesIO(single.content)).pages
        # 34 pupils, long names included, still fit a single sheet of paper.
        assert len(pages) == 1
        text = pages[0].extract_text()
        assert "5/A · English" in text
        assert "34 students" in text

        several = await client.get(
            "/api/reports/class-sheets",
            params=params | {"class_id": [world.cls, empty_id, second_id]},
        )
        pages = PdfReader(BytesIO(several.content)).pages
        # The empty class is left out; every other class has exactly one page.
        assert len(pages) == 2
        assert "7/C · English" in pages[1].extract_text()

        only_empty = await client.get(
            "/api/reports/class-sheets", params=params | {"class_id": empty_id}
        )
        assert only_empty.status_code == 409
        assert only_empty.json()["detail"]["code"] == "empty_report_set"


async def test_long_labels_names_and_many_fields_still_fit_one_page(
    api, world, monkeypatch, request
) -> None:
    """Every heading and the masthead have fixed heights, and fields share the width, so
    admin-entered labels, long school and teacher names and many fields cannot push rows off
    the page."""
    monkeypatch.setattr(settings, "school_name", "Synthetic School With A Long Official Name " * 5)
    school_brand.cache_clear()
    request.addfinalizer(school_brand.cache_clear)
    await _fill_class(world, 34)
    long_group = "A group heading an administrator typed at great length " * 6
    long_label = "An assessment heading that keeps going well past three printed lines " * 3
    async with TestSession() as db:
        for teacher in (world.main.id, world.skills.id):
            user = await db.get(m.User, teacher)
            assert user is not None
            user.full_name = "Synthetic Teacher With A Very Long Name " * 4
        columns = [
            m.ColumnDefinition(
                semester_id=world.semester,
                grade_level=5,
                subject="english",
                value_type="scale3" if position % 2 else "score",
                owner_role="main",
                labels={"tr": long_label, "en": f"{long_label}{position}"},
                group_labels={"tr": long_group, "en": f"{long_group}{position // 4}"},
                position=10 + position,
            )
            for position in range(40)
        ]
        db.add_all(columns)
        await db.flush()
        pupils = await db.scalars(
            select(m.Enrollment.student_id).where(m.Enrollment.class_id == world.cls)
        )
        db.add_all(
            m.GradeValue(
                student_id=pupil,
                column_definition_id=column.id,
                version=1,
                updated_by=world.main.id,
                **({"scale": 3} if column.value_type == "scale3" else {"score": 100}),
            )
            for pupil in pupils
            for column in columns
        )
        await db.commit()
    async with api(world.main) as client:
        preview = await client.get(f"/api/classes/{world.cls}/sheet")
        response = await client.get(
            "/api/reports/class-sheets",
            params={"semester_id": world.semester, "class_id": world.cls, "locale": "tr"},
        )
    assert response.status_code == 200
    # 34 pupils, 42 fields with long headings in long groups, the rating legend and two
    # long teacher names: still one page.
    assert len(PdfReader(BytesIO(response.content)).pages) == 1
    # The name column gives way so a three-digit score stays whole in each narrow field.
    name_mm, field_mm, value_pt = column_widths(ClassSheetOut(**preview.json()), 7.5)
    assert name_mm < 64
    assert value_pt >= 6
    assert 3 * value_pt * DIGIT_MM_PER_PT + VALUE_PADDING_MM <= field_mm


async def test_pdf_rejects_unknown_and_other_year_classes(api, world) -> None:
    async with TestSession() as db:
        past_year = m.AcademicYear(label="2020-2021", status="archived")
        db.add(past_year)
        await db.flush()
        past_class = m.SchoolClass(year_id=past_year.id, grade_level=5, section="A")
        db.add(past_class)
        await db.commit()
        past_class_id = past_class.id
    params = {"semester_id": world.semester}
    async with api(world.skills) as client:
        unknown = await client.get(
            "/api/reports/class-sheets", params=params | {"class_id": 999999}
        )
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "unknown_class"
        other_year = await client.get(
            "/api/reports/class-sheets", params=params | {"class_id": past_class_id}
        )
        assert other_year.status_code == 409
        assert other_year.json()["detail"]["code"] == "class_not_in_semester"
