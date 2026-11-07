from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfReader

from flrc.core import rate_limit
from flrc.db import models as m
from flrc.modules.reports import preview as preview_module
from tests.conftest import TestSession

WATERMARK = "ÖNİZLEME"
A4_HEIGHT_PT = 841.89


def pdf_text(content: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


@pytest.fixture
async def languages(world):
    """Adds a German teacher to 5/A, where only student one takes German, and a 6/A."""
    async with TestSession() as db:
        german = m.User(email="german@example.test", full_name="German Teacher")
        outsider = m.User(email="outsider@example.test", full_name="Unassigned Teacher")
        coordinator = m.User(
            email="coordinator@example.test", full_name="Coordinator", is_coordinator=True
        )
        other_class = m.SchoolClass(year_id=world.year, grade_level=6, section="A")
        other_student = m.Student(full_name="Other Pupil", search_name="other pupil")
        unnumbered = m.Student(full_name="Aaron Unnumbered", search_name="aaron unnumbered")
        db.add_all([german, outsider, coordinator, other_class, other_student, unnumbered])
        await db.flush()
        db.add_all(
            [
                m.TeachingAssignment(class_id=world.cls, role="german", user_id=german.id),
                m.StudentLanguage(
                    student_id=world.student_one, year_id=world.year, language="german"
                ),
                m.Enrollment(
                    student_id=other_student.id,
                    class_id=other_class.id,
                    year_id=world.year,
                    school_number=61001,
                ),
                # No number yet: listed after the numbered pupils, as in the official set.
                m.Enrollment(
                    student_id=unnumbered.id,
                    class_id=world.cls,
                    year_id=world.year,
                    school_number=None,
                ),
            ]
        )
        await db.commit()
        return SimpleNamespace(
            german=german,
            outsider=outsider,
            coordinator=coordinator,
            other_class=other_class.id,
            other_student=other_student.id,
            unnumbered=unnumbered.id,
        )


async def preview(api, user, world, student_id: int, kind: str):
    async with api(user) as client:
        return await client.get(
            "/api/reports/preview",
            params={"semester_id": world.semester, "student_id": student_id, "kind": kind},
        )


async def test_assigned_english_teachers_preview_their_class_card_with_the_mark(
    api, world, languages
) -> None:
    for teacher in (world.main, world.skills):
        response = await preview(api, teacher, world, world.student_one, "english_middle")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "no-store" in response.headers["cache-control"]
        reader = PdfReader(BytesIO(response.content))
        # Only this pupil's A5 card: the two-up sheet is cropped to its top half.
        assert len(reader.pages) == 1
        assert float(reader.pages[0].mediabox.height) == pytest.approx(A4_HEIGHT_PT / 2, abs=1)
        text = pdf_text(response.content)
        assert WATERMARK in text
        assert "Synthetic Student One" in text
        assert "Synthetic Student Two" not in text


async def test_teachers_cannot_preview_other_classes_or_other_cards(api, world, languages) -> None:
    denied = [
        (world.main, languages.other_student, "english_middle"),
        (world.main, world.student_one, "german_karne"),
        (languages.german, world.student_one, "english_middle"),
        # The German teacher's class, but this pupil does not take German.
        (languages.german, world.student_two, "german_karne"),
        (languages.outsider, world.student_one, "english_middle"),
        (languages.coordinator, world.student_one, "english_middle"),
    ]
    for user, student_id, kind in denied:
        response = await preview(api, user, world, student_id, kind)
        assert response.status_code == 403, (user.full_name, student_id, kind)
        assert response.json()["detail"]["code"] == "forbidden"


async def test_language_teacher_previews_their_language_card(api, world, languages) -> None:
    response = await preview(api, languages.german, world, world.student_one, "german_karne")
    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content))
    # The duplex karne keeps both of its pages, each one marked.
    assert len(reader.pages) == 2
    for page in reader.pages:
        assert WATERMARK in page.extract_text()


async def test_admin_previews_any_card_that_exists(api, world, languages) -> None:
    allowed = await preview(api, world.admin, world, languages.other_student, "english_middle")
    assert allowed.status_code == 200
    assert WATERMARK in pdf_text(allowed.content)

    no_language = await preview(api, world.admin, world, world.student_two, "german_karne")
    wrong_grade = await preview(api, world.admin, world, world.student_one, "english_elementary")
    for response in (no_language, wrong_grade):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "report_preview_not_eligible"

    unknown = await preview(api, world.admin, world, 999_999, "english_middle")
    assert unknown.status_code == 404
    # A teacher learns nothing about pupils outside their classes.
    hidden = await preview(api, world.main, world, 999_999, "english_middle")
    assert hidden.status_code == 403


async def test_preview_is_the_requested_pupil_even_when_names_and_numbers_match(
    api, world, monkeypatch
) -> None:
    # A rolled-over setup year has no numbers yet, and two pupils may share a name.
    async with TestSession() as db:
        twins = [m.Student(full_name="Twin Pupil", search_name="twin pupil") for _ in range(2)]
        db.add_all(twins)
        await db.flush()
        for twin, score in zip(twins, (37, 93), strict=True):
            db.add(
                m.Enrollment(
                    student_id=twin.id, class_id=world.cls, year_id=world.year, school_number=None
                )
            )
            db.add(
                m.GradeValue(
                    student_id=twin.id,
                    column_definition_id=world.main_column,
                    score=score,
                    version=1,
                    updated_by=world.main.id,
                )
            )
        await db.commit()
        ids = [twin.id for twin in twins]

    async def check() -> None:
        for student_id, own, other in ((ids[0], "37", "93"), (ids[1], "93", "37")):
            response = await preview(api, world.main, world, student_id, "english_middle")
            assert response.status_code == 200
            text = pdf_text(response.content)
            assert "Twin Pupil" in text
            assert own in text
            assert other not in text

    await check()
    # The eligibility read may list the class in another order than the builder
    # (a roster change between the two reads); the card still follows the id.
    roster = preview_module._roster

    async def reordered(*args, **kwargs):
        return {class_id: rows[::-1] for class_id, rows in (await roster(*args, **kwargs)).items()}

    monkeypatch.setattr(preview_module, "_roster", reordered)
    await check()


async def test_official_report_set_carries_no_preview_mark(api, world) -> None:
    async with api(world.admin) as client:
        response = await client.get(
            "/api/reports/pdf",
            params={"semester_id": world.semester, "kind": "english_middle", "class_id": world.cls},
        )
    assert response.status_code == 200
    text = pdf_text(response.content)
    assert "Synthetic Student One" in text
    assert WATERMARK not in text


async def test_preview_uses_the_single_report_rate_limit(api, world, monkeypatch) -> None:
    evaluate = AsyncMock(return_value=(rate_limit.REPORT_SINGLE_LIMIT + 1, 17))
    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    response = await preview(api, world.main, world, world.student_one, "english_middle")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    assert evaluate.await_args is not None
    assert "report_single" in evaluate.await_args.args[2]


async def test_scope_lists_own_classes_and_eligible_pupils_in_order(api, world, languages) -> None:
    async with TestSession() as db:
        # An assignment in another year never reaches this year's scope.
        old_year = m.AcademicYear(label="Older synthetic year", status="archived")
        db.add(old_year)
        await db.flush()
        old_class = m.SchoolClass(year_id=old_year.id, grade_level=5, section="B")
        db.add(old_class)
        await db.flush()
        db.add(m.TeachingAssignment(class_id=old_class.id, role="main", user_id=world.main.id))
        await db.commit()

    async with api(world.main) as client:
        mine = await client.get("/api/reports/preview/scope")
        explicit = await client.get(
            "/api/reports/preview/scope", params={"semester_id": world.semester}
        )
    assert mine.status_code == 200
    assert explicit.json() == mine.json()
    scope = mine.json()
    assert scope["semester_id"] == world.semester
    assert scope["semester_number"] == 1
    assert [term["id"] for term in scope["semesters"]] == [world.semester]
    assert [(entry["class_id"], entry["kind"]) for entry in scope["classes"]] == [
        (world.cls, "english_middle")
    ]
    assert [
        (student["student_id"], student["school_number"])
        for student in scope["classes"][0]["students"]
    ] == [
        (world.student_one, 51001),
        (world.student_two, 51002),
        (languages.unnumbered, None),
    ]

    async with api(languages.german) as client:
        german = (await client.get("/api/reports/preview/scope")).json()
    assert [(entry["class_name"], entry["kind"]) for entry in german["classes"]] == [
        ("5/A", "german_karne")
    ]
    assert [student["student_id"] for student in german["classes"][0]["students"]] == [
        world.student_one
    ]

    for user in (languages.coordinator, languages.outsider, world.admin):
        async with api(user) as client:
            response = await client.get("/api/reports/preview/scope")
        assert response.status_code == 200
        assert response.json()["classes"] == []

    async with api(world.main) as client:
        unknown = await client.get("/api/reports/preview/scope", params={"semester_id": 999_999})
    assert unknown.status_code == 404
