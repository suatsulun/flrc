import base64
from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.modules.administration.report_identity import MAX_SIGNATURE_BYTES, validate_signature
from flrc.modules.reports.builder import build_report_set
from tests.conftest import TEST_URL_SYNC, TestSession


def png_bytes(size=(120, 40), color=(20, 30, 40, 255), metadata=False):
    image = Image.new("RGBA", size, color)
    data = BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text("Comment", "Private scanner metadata")
    image.save(data, format="PNG", pnginfo=info)
    return data.getvalue()


def test_signature_pixels_preserved_metadata_removed():
    original = png_bytes(metadata=True)
    result = validate_signature(original + b"discard appended payload")
    with Image.open(BytesIO(result)) as image, Image.open(BytesIO(original)) as source:
        assert image.tobytes() == source.tobytes()
        assert image.info == {}
    assert b"Private scanner metadata" not in result
    assert b"appended payload" not in result


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"<svg><script/></svg>", "signature_invalid_png"),
        (b"not a png", "signature_invalid_png"),
        (png_bytes()[:-20], "signature_invalid_png"),
        (b"x" * (MAX_SIGNATURE_BYTES + 1), "signature_too_large"),
        (png_bytes((4097, 1)), "signature_dimensions"),
        (png_bytes((2100, 2100)), "signature_dimensions"),
        (png_bytes(color=(0, 0, 0, 0)), "signature_empty"),
    ],
)
def test_invalid_signature_rejected(data, error):
    with pytest.raises(ValueError, match=error):
        validate_signature(data)


def test_animated_signature_rejected():
    out = BytesIO()
    Image.new("RGBA", (20, 20), "black").save(
        out, format="PNG", save_all=True, append_images=[Image.new("RGBA", (20, 20), "red")]
    )
    with pytest.raises(ValueError, match="signature_invalid_png"):
        validate_signature(out.getvalue())


async def test_admin_upload_download_replace_remove_and_identity_audit(api, world):
    path = f"/api/admin/users/{world.main.id}"
    original = png_bytes(metadata=True)
    async with api(world.admin) as client:
        renamed = await client.patch(path, json={"report_name": "  Synthetic PRINT NAME  "})
        assert renamed.status_code == 200
        assert renamed.json()["report_name"] == "Synthetic PRINT NAME"
        uploaded = await client.put(
            path + "/signature", files={"file": ("sign.png", original, "image/png")}
        )
        assert uploaded.status_code == 200
        assert "signature_png" not in uploaded.json()
        signature_url = uploaded.json()["signature_url"]
        assert signature_url.startswith(path + "/signature?v=")
        downloaded = await client.get(signature_url)
        assert downloaded.headers["content-type"] == "image/png"
        assert "no-store" in downloaded.headers["cache-control"]
        assert downloaded.content == validate_signature(original)
        invalid = await client.put(
            path + "/signature", files={"file": ("spoof.png", b"<svg/>", "image/png")}
        )
        assert invalid.status_code == 422
        assert (await client.get(signature_url)).content == downloaded.content
        replaced = await client.put(
            path + "/signature", files={"file": ("sign.png", png_bytes(color="blue"), "image/png")}
        )
        assert replaced.status_code == 200
        assert replaced.json()["signature_url"] != signature_url
        removed = await client.delete(path + "/signature")
        assert removed.status_code == 200
        assert removed.json()["signature_url"] is None
        assert (await client.get(path + "/signature")).status_code == 404
        reset = await client.patch(path, json={"report_name": "   "})
        assert reset.json()["report_name"] is None
    async with TestSession() as db:
        events = list(
            await db.scalars(select(m.ReportIdentityAudit).order_by(m.ReportIdentityAudit.id))
        )
        assert len(events) == 5
        assert all(
            event.actor_id == world.admin.id and event.user_id == world.main.id for event in events
        )
        assert events[0].after["report_name"] == "Synthetic PRINT NAME"
        assert events[1].before["signature_digest"] is None
        assert events[1].after["signature_digest"]
        assert events[-2].after["signature_digest"] is None
        assert "signature_png" not in str([event.after for event in events])


async def test_signature_endpoints_require_admin_and_origin(api, world):
    path = f"/api/admin/users/{world.main.id}/signature"
    async with TestSession() as db:
        coordinator = m.User(
            email="coordinator@example.test", full_name="Synthetic Coordinator", is_coordinator=True
        )
        db.add(coordinator)
        await db.commit()
    for actor in (world.main, coordinator):
        async with api(actor) as client:
            assert (await client.get(path)).status_code == 403
            assert (
                await client.put(path, files={"file": ("sign.png", png_bytes())})
            ).status_code == 403
            assert (await client.delete(path)).status_code == 403
    async with api(None) as client:
        assert (await client.get(path)).status_code == 401
    async with api(world.admin) as client:
        blocked = await client.put(
            path,
            files={"file": ("sign.png", png_bytes())},
            headers={"origin": "https://untrusted.example"},
        )
        assert blocked.status_code == 403
        assert (await client.get("/api/admin/users/999999/signature")).status_code == 404


async def test_report_builder_selects_class_subject_teachers_and_deduplicates_roles(world):
    signature = png_bytes()
    async with TestSession() as db:
        teacher = await db.get(m.User, world.main.id)
        teacher.report_name = "Synthetic Report Teacher"
        teacher.signature_png = signature
        assignment = await db.scalar(
            select(m.TeachingAssignment).where(
                m.TeachingAssignment.class_id == world.cls, m.TeachingAssignment.role == "skills"
            )
        )
        assignment.user_id = teacher.id
        other = m.User(
            email="german@example.test",
            full_name="Synthetic German Teacher",
            teaching_field="german",
        )
        db.add(other)
        await db.flush()
        db.add(m.TeachingAssignment(class_id=world.cls, role="german", user_id=other.id))
        await db.commit()
    with Session(create_engine(TEST_URL_SYNC)) as db:
        cards = build_report_set(db, semester_id=world.semester, kind="english_middle", locale="en")
    assert len(cards) == 2
    for card in cards:
        assert card.language_subject is None
        assert len(card.teachers) == 1
        teacher = card.teachers[0]
        assert teacher.name == "Synthetic Report Teacher"
        assert teacher.roles == ["main", "skills"]
        assert base64.b64decode(teacher.signature.split(",")[1]) == signature


async def test_middle_card_uses_each_students_year_class_and_language_teacher(world):
    signatures = {"german": png_bytes(color="navy"), "french": png_bytes(color="teal")}
    async with TestSession() as db:
        german = m.User(
            email="german@example.test",
            full_name="Synthetic German Account",
            report_name="Synthetic German Print Name",
            teaching_field="german",
            signature_png=signatures["german"],
        )
        french = m.User(
            email="french@example.test",
            full_name="Synthetic French Fallback Name",
            teaching_field="french",
            signature_png=signatures["french"],
        )
        other = m.User(
            email="other@example.test",
            full_name="Synthetic Other Class Teacher",
            teaching_field="german",
        )
        historical = m.User(
            email="historical@example.test",
            full_name="Synthetic Historical Teacher",
            teaching_field="french",
            is_active=False,
        )
        old_year = m.AcademicYear(label="Synthetic archived year", status="archived")
        other_class = m.SchoolClass(year_id=world.year, grade_level=5, section="B")
        db.add_all([german, french, other, historical, old_year, other_class])
        await db.flush()
        old_semester = m.Semester(year_id=old_year.id, number=1, status="locked")
        old_class = m.SchoolClass(year_id=old_year.id, grade_level=5, section="A")
        db.add_all([old_semester, old_class])
        await db.flush()
        db.add_all(
            [
                m.TeachingAssignment(class_id=world.cls, role="german", user_id=german.id),
                m.TeachingAssignment(class_id=world.cls, role="french", user_id=french.id),
                m.TeachingAssignment(class_id=other_class.id, role="german", user_id=other.id),
                m.TeachingAssignment(class_id=old_class.id, role="french", user_id=historical.id),
                m.StudentLanguage(
                    student_id=world.student_one, year_id=world.year, language="german"
                ),
                m.StudentLanguage(
                    student_id=world.student_two, year_id=world.year, language="french"
                ),
                m.StudentLanguage(
                    student_id=world.student_one, year_id=old_year.id, language="french"
                ),
                m.Enrollment(
                    student_id=world.student_one,
                    year_id=old_year.id,
                    class_id=old_class.id,
                    school_number=51001,
                ),
            ]
        )
        await db.commit()
    with Session(create_engine(TEST_URL_SYNC)) as db:
        cards = build_report_set(db, semester_id=world.semester, kind="english_middle", locale="en")
        historical_cards = build_report_set(
            db, semester_id=old_semester.id, kind="english_middle", locale="en"
        )
        language_cards = {
            subject: build_report_set(
                db, semester_id=world.semester, kind=subject + "_karne", locale="tr"
            )
            for subject in ("german", "french")
        }

    assert len(cards) == 2
    for card, subject, teacher in zip(cards, ("german", "french"), (german, french), strict=True):
        assert card.language_subject == subject
        assert card.language_fields == [], "enrollment selects the teacher even without scores"
        assert [(item.user_id, item.roles) for item in card.teachers] == [
            (world.main.id, ["main"]),
            (world.skills.id, ["skills"]),
            (teacher.id, [subject]),
        ]
        signer = card.teachers[-1]
        assert signer.name == (teacher.report_name or teacher.full_name)
        assert base64.b64decode(signer.signature.split(",")[1]) == signatures[subject]
        assert len(language_cards[subject]) == 1
        assert language_cards[subject][0].teachers == [signer]
        assert language_cards[subject][0].language_subject is None

    assert len(historical_cards) == 1
    historical_card = historical_cards[0]
    assert historical_card.language_subject == "french"
    assert [(item.user_id, item.name, item.roles) for item in historical_card.teachers] == [
        (historical.id, historical.full_name, ["french"])
    ]


@pytest.mark.parametrize("language", ["german", "french"])
async def test_middle_card_missing_language_assignment_never_uses_the_other_teacher(
    world, language
):
    other_language = "french" if language == "german" else "german"
    async with TestSession() as db:
        other = m.User(
            email="other@example.test",
            full_name="Synthetic Other Language Teacher",
            teaching_field=other_language,
        )
        db.add(other)
        await db.flush()
        db.add_all(
            [
                m.StudentLanguage(
                    student_id=world.student_one, year_id=world.year, language=language
                ),
                m.TeachingAssignment(class_id=world.cls, role=other_language, user_id=other.id),
            ]
        )
        await db.commit()
    with Session(create_engine(TEST_URL_SYNC)) as db:
        cards = build_report_set(db, semester_id=world.semester, kind="english_middle", locale="en")
    assert [card.language_subject for card in cards] == [language, None]
    assert all(
        [(teacher.user_id, teacher.roles) for teacher in card.teachers]
        == [(world.main.id, ["main"]), (world.skills.id, ["skills"])]
        for card in cards
    )
