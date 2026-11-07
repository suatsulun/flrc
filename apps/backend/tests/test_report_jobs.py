"""Report downloads, background report jobs, the student picker and download names (ADR-077)."""

from io import BytesIO
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4
from zipfile import ZipFile

import pytest
from pypdf import PdfReader
from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from flrc.config import settings
from flrc.core import rate_limit
from flrc.db import models as m
from flrc.modules.reports import packaging
from flrc.modules.reports import router as reports_router
from flrc.modules.reports.builder import build_report_entries
from flrc.modules.reports.filenames import (
    class_sheet_filename,
    content_disposition,
    report_filename,
    student_scope,
)
from flrc.workers.tasks import reports as report_tasks
from tests.conftest import TEST_URL_SYNC, TestSession

TERM = "Synthetic year 1. Dönem"


@pytest.fixture(autouse=True)
async def rate_limits(monkeypatch):
    """Run the production limiter against Redis under keys no other test or run shares.

    Yields a reset that starts every budget afresh, for tests that send many requests.
    """
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    prefix = f"test:reports:{uuid4().hex}:"

    async def evaluate(script, numkeys, key, window):
        return await redis.eval(script, numkeys, prefix + key, window)

    async def reset() -> None:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}*")]
        if keys:
            await redis.delete(*keys)

    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    try:
        yield reset
    finally:
        await reset()
        await redis.aclose()


@pytest.fixture
def queued(monkeypatch) -> list[int]:
    """Capture enqueued report jobs and let the test run them against the test database."""
    ids: list[int] = []
    monkeypatch.setattr(reports_router.report_set_job, "delay", ids.append)
    monkeypatch.setattr(report_tasks, "sync_engine", lambda: create_engine(TEST_URL_SYNC))
    return ids


async def add_class(
    world,
    grade: int,
    section: str,
    students: list[tuple[str, int | None]],
    language: str | None = None,
    year_id: int | None = None,
) -> SimpleNamespace:
    async with TestSession() as db:
        school_class = m.SchoolClass(
            year_id=year_id or world.year, grade_level=grade, section=section
        )
        db.add(school_class)
        await db.flush()
        ids: list[int] = []
        for name, number in students:
            student = m.Student(full_name=name, search_name=name.lower())
            db.add(student)
            await db.flush()
            db.add(
                m.Enrollment(
                    student_id=student.id,
                    class_id=school_class.id,
                    year_id=year_id or world.year,
                    school_number=number,
                )
            )
            if language:
                db.add(
                    m.StudentLanguage(
                        student_id=student.id, year_id=year_id or world.year, language=language
                    )
                )
            ids.append(student.id)
        await db.commit()
        return SimpleNamespace(id=school_class.id, students=ids)


async def add_coordinator() -> m.User:
    async with TestSession() as db:
        user = m.User(email="coordinator@example.test", full_name="C", is_coordinator=True)
        db.add(user)
        await db.commit()
        return user


async def add_german(world, *student_ids: int, grade: int = 5) -> None:
    async with TestSession() as db:
        db.add(
            m.ColumnDefinition(
                semester_id=world.semester,
                grade_level=grade,
                subject="german",
                value_type="scale3",
                owner_role="german",
                labels={"tr": "Derse katılır", "de": "Nimmt teil"},
                position=1,
            )
        )
        for student_id in student_ids:
            db.add(m.StudentLanguage(student_id=student_id, year_id=world.year, language="german"))
        await db.commit()


def pdf_text(data: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(BytesIO(data)).pages]


def disposition_name(header: str) -> str:
    return header.split("filename*=UTF-8''", 1)[1]


# Download names


def test_report_names_keep_turkish_letters_and_replace_class_slashes() -> None:
    scope = student_scope("8/A", 123, "Ali Yılmaz")
    assert report_filename(scope, "english_middle", "2026-2027", 1, "pdf") == (
        "8-A 123 Ali Yılmaz İngilizce Karne 2026-2027 1. Dönem.pdf"
    )
    assert report_filename("8/A", "german_karne", "2026-2027", 2, "zip") == (
        "8-A Almanca Karne 2026-2027 2. Dönem.zip"
    )
    assert report_filename("Tüm Okul", "french_karne", "2026-2027", 1, "zip") == (
        "Tüm Okul Fransızca Karne 2026-2027 1. Dönem.zip"
    )
    # A pupil without a number is named by class and name; Windows-invalid characters go.
    assert student_scope("Bulut", None, "Ayşe") == "Bulut Ayşe"
    assert report_filename('5/B Ali: "x"?*', "english_elementary", "2026-2027", 1, "pdf") == (
        "5-B Ali x İngilizce Karne 2026-2027 1. Dönem.pdf"
    )
    assert class_sheet_filename(["8/A"], "2026-2027", 1) == (
        "8-A Sınıf Raporu 2026-2027 1. Dönem.pdf"
    )
    assert class_sheet_filename(["8/A", "8/B"], "2026-2027", 1) == (
        "Sınıf Raporları 2026-2027 1. Dönem.pdf"
    )


def test_content_disposition_has_an_ascii_fallback_and_an_encoded_utf8_name() -> None:
    header = content_disposition("8-A Öğrenci Şıkİ Karne.pdf", inline=True)
    assert header == (
        'inline; filename="8-A Ogrenci SikI Karne.pdf"; '
        "filename*=UTF-8''8-A%20%C3%96%C4%9Frenci%20%C5%9E%C4%B1k%C4%B0%20Karne.pdf"
    )
    header.encode("latin-1")
    hostile = content_disposition('a\r\n"b\\c.zip')
    assert hostile.startswith('attachment; filename="abc.zip"')
    assert "\r" not in hostile and "\n" not in hostile
    assert content_disposition(None).startswith('attachment; filename="download"')


# Picker


async def test_picker_lists_eligible_classes_and_students_in_roster_order(api, world) -> None:
    prep = await add_class(world, 0, "Bulut", [("Prep Pupil", 3)])
    fourth = await add_class(world, 4, "B", [("Zeynep Four", 402), ("Ahmet Four", 401)])
    other = await add_class(world, 5, "B", [("Middle Other", 5201)])
    await add_class(world, 6, "C", [])
    await add_german(world, world.student_two)
    async with TestSession() as db:
        db.add(
            m.StudentLanguage(student_id=fourth.students[0], year_id=world.year, language="german")
        )
        db.add(
            m.StudentLanguage(student_id=other.students[0], year_id=world.year, language="french")
        )
        await db.commit()

    async with api(world.admin) as client:

        async def roster(kind: str) -> list[dict]:
            response = await client.get(
                "/api/reports/roster", params={"semester_id": world.semester, "kind": kind}
            )
            assert response.status_code == 200
            return response.json()

        elementary = await roster("english_elementary")
        middle = await roster("english_middle")
        german = await roster("german_karne")
        french = await roster("french_karne")

    # Hazırlık (grade 0) and grade 4 are primary; grade 5 and up are middle school.
    assert [item["name"] for item in elementary] == ["Bulut", "4/B"]
    assert elementary[0]["id"] == prep.id
    assert [student["full_name"] for student in elementary[1]["students"]] == [
        "Ahmet Four",
        "Zeynep Four",
    ]
    # Empty classes produce no card and are left out.
    assert [item["name"] for item in middle] == ["5/A", "5/B"]
    assert middle[0]["students"] == [
        {"id": world.student_one, "full_name": "Synthetic Student One", "school_number": 51001},
        {"id": world.student_two, "full_name": "Synthetic Student Two", "school_number": 51002},
    ]
    # Second-language cards list only the pupils taking that language.
    assert [(item["name"], [s["id"] for s in item["students"]]) for item in german] == [
        ("4/B", [fourth.students[0]]),
        ("5/A", [world.student_two]),
    ]
    assert [(item["name"], [s["id"] for s in item["students"]]) for item in french] == [
        ("5/B", [other.students[0]])
    ]


async def test_picker_and_downloads_are_for_coordinators_and_admins(api, world) -> None:
    params = {"semester_id": world.semester, "kind": "english_middle"}
    async with api(world.main) as client:
        assert (await client.get("/api/reports/roster", params=params)).status_code == 403
        assert (
            await client.get("/api/reports/pdf", params=params | {"class_id": world.cls})
        ).status_code == 403
        job = await client.post("/api/reports/jobs", json=params | {"format": "combined"})
        assert job.status_code == 403
    async with api(world.admin) as client:
        missing = await client.get("/api/reports/roster", params=params | {"semester_id": 999999})
        assert missing.status_code == 404


# Direct downloads


async def test_direct_download_of_one_class_or_one_student(api, world) -> None:
    await add_class(world, 5, "B", [("Middle Other", 5201)])
    params = {"semester_id": world.semester, "kind": "english_middle"}
    async with api(world.admin) as client:
        whole = await client.get("/api/reports/pdf", params=params)
        assert whole.status_code == 422
        assert whole.json()["detail"]["code"] == "report_scope_required"

        one_class = await client.get("/api/reports/pdf", params=params | {"class_id": world.cls})
        assert one_class.status_code == 200
        assert one_class.headers["content-type"].startswith("application/pdf")
        assert one_class.headers["cache-control"] == "no-store, private, max-age=0"
        assert one_class.headers["content-disposition"].startswith("inline; ")
        assert disposition_name(one_class.headers["content-disposition"]) == quote(
            f"5-A İngilizce Karne {TERM}.pdf", safe=""
        )
        (sheet,) = pdf_text(one_class.content)
        assert "Synthetic Student One" in sheet and "Synthetic Student Two" in sheet

        student = await client.get(
            "/api/reports/pdf", params=params | {"student_id": world.student_two}
        )
        assert student.status_code == 200
        assert disposition_name(student.headers["content-disposition"]) == quote(
            f"5-A 51002 Synthetic Student Two İngilizce Karne {TERM}.pdf", safe=""
        )
        (page,) = pdf_text(student.content)
        assert "Synthetic Student Two" in page and "Synthetic Student One" not in page

        several = await client.get(
            "/api/reports/pdf",
            params=params | {"student_id": [world.student_one, world.student_two]},
        )
        assert several.status_code == 200
        assert disposition_name(several.headers["content-disposition"]) == quote(
            f"5-A Seçili Öğrenciler İngilizce Karne {TERM}.pdf", safe=""
        )


async def test_direct_download_refuses_sets_that_need_a_job(api, world) -> None:
    other = await add_class(world, 5, "B", [("Middle Other", 5201)])
    elementary = await add_class(world, 3, "C", [("Primary Pupil", 3001)])
    params = {"semester_id": world.semester, "kind": "english_middle"}
    async with api(world.admin) as client:
        spanning = await client.get(
            "/api/reports/pdf",
            params=params | {"student_id": [world.student_one, other.students[0]]},
        )
        assert spanning.status_code == 422
        assert spanning.json()["detail"]["code"] == "report_students_span_classes"

        both = await client.get(
            "/api/reports/pdf",
            params=params | {"class_id": world.cls, "student_id": world.student_one},
        )
        assert both.json()["detail"]["code"] == "report_scope_conflict"

        wrong_card = await client.get(
            "/api/reports/pdf",
            params=params | {"student_id": [world.student_one, elementary.students[0]]},
        )
        assert wrong_card.status_code == 409
        assert wrong_card.json()["detail"]["code"] == "student_not_in_report_set"

        not_german = await client.get(
            "/api/reports/pdf",
            params=params | {"kind": "german_karne", "student_id": world.student_one},
        )
        assert not_german.status_code == 409
        assert not_german.json()["detail"]["code"] == "empty_report_set"


# Job creation


async def test_job_creation_validates_scope_and_names_the_output(
    api, world, queued, rate_limits
) -> None:
    coordinator = await add_coordinator()
    other = await add_class(world, 5, "B", [("Middle Other", 5201)])
    elementary = await add_class(world, 3, "C", [("Primary Pupil", 3001)])
    async with TestSession() as db:
        past = m.AcademicYear(label="Past", status="archived")
        db.add(past)
        await db.flush()
        past_id = past.id
        await db.commit()
    past_class = await add_class(world, 5, "A", [("Past Pupil", 1)], year_id=past_id)

    body = {"semester_id": world.semester, "kind": "english_middle", "format": "per_class"}
    async with api(coordinator) as client:

        async def post(**changes: object):
            return await client.post("/api/reports/jobs", json=body | changes)

        whole = await post()
        assert whole.status_code == 202
        job = whole.json()
        assert job["kind"] == "report_set"
        assert job["status"] == "queued"
        assert job["total"] == 2
        assert job["output_filename"] == f"Tüm Okul İngilizce Karne {TERM}.zip"
        assert queued == [job["id"]]

        classes = await post(format="combined", class_ids=[world.cls, other.id])
        assert classes.json()["output_filename"] == f"Seçili Sınıflar İngilizce Karne {TERM}.pdf"
        one_class = await post(class_ids=[other.id], format="per_student")
        assert one_class.json()["output_filename"] == f"5-B İngilizce Karne {TERM}.zip"
        students = await post(student_ids=[world.student_one, other.students[0]])
        assert students.json()["total"] == 2
        assert students.json()["output_filename"] == (
            f"Seçili Öğrenciler İngilizce Karne {TERM}.zip"
        )

    errors = [
        ({"semester_id": 999999}, 404, "unknown_semester"),
        ({"class_ids": [999999]}, 404, "unknown_class"),
        ({"class_ids": [past_class.id]}, 409, "class_not_in_semester"),
        ({"class_ids": [elementary.id]}, 409, "class_not_in_report_set"),
        ({"student_ids": [elementary.students[0]]}, 409, "student_not_in_report_set"),
        ({"kind": "german_karne"}, 409, "empty_report_set"),
        ({"class_ids": [world.cls], "student_ids": [world.student_one]}, 422, None),
        ({"format": "everything"}, 422, None),
    ]
    async with api(world.admin) as client:
        for changes, status, code in errors:
            response = await client.post("/api/reports/jobs", json=body | changes)
            assert response.status_code == status, (changes, response.text)
            if code:
                assert response.json()["detail"]["code"] == code
            # The limiter counts every request; the table is longer than one window allows.
            await rate_limits()
    assert len(queued) == 4


async def test_report_routes_have_their_own_budgets(api, world, queued) -> None:
    body = {"semester_id": 999999, "kind": "english_middle", "format": "combined"}
    async with api(world.admin) as client:
        for _ in range(5):
            assert (await client.post("/api/reports/jobs", json=body)).status_code == 404
        limited = await client.post("/api/reports/jobs", json=body)
        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "rate_limited"
        assert 1 <= int(limited.headers["retry-after"]) <= 60

        # A spent set budget leaves single downloads and class sheets available.
        params = {"semester_id": world.semester, "kind": "english_middle", "class_id": world.cls}
        assert (await client.get("/api/reports/pdf", params=params)).status_code == 200
        sheets = await client.get(
            "/api/reports/class-sheets",
            params={"semester_id": world.semester, "class_id": world.cls},
        )
        assert sheets.status_code == 200


async def test_demo_refuses_report_jobs(api, world, queued, monkeypatch) -> None:
    monkeypatch.setattr(settings, "env", "demo")
    async with api(world.admin) as client:
        # The browser's same-origin mark passes the demo's origin check, as the admin app's does.
        response = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "english_middle", "format": "combined"},
            headers={"Sec-Fetch-Site": "same-origin"},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "demo_report_class_required"
    assert queued == []


# Running jobs and packaging


async def run_job(api, user, queued: list[int], body: dict) -> tuple[dict, bytes, str]:
    async with api(user) as client:
        created = await client.post("/api/reports/jobs", json=body)
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        report_tasks.report_set_job(job_id)
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        download = await client.get(f"/api/jobs/{job_id}/download")
    assert job["status"] == "succeeded", job
    assert download.status_code == 200
    return job, download.content, download.headers["content-disposition"]


async def three_pupil_class(world) -> SimpleNamespace:
    return await add_class(
        world, 6, "A", [("Pupil Alpha", 6001), ("Pupil Beta", 6002), ("Pupil Gamma", 6003)]
    )


async def test_combined_job_is_one_pdf_with_every_class(api, world, queued) -> None:
    await three_pupil_class(world)
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "combined"}
    job, data, header = await run_job(api, world.admin, queued, body)
    assert job["progress"] == job["total"] == 2
    assert header.startswith('attachment; filename="Tum Okul Ingilizce Karne')
    assert disposition_name(header) == quote(f"Tüm Okul İngilizce Karne {TERM}.pdf", safe="")
    # Two-up A5 imposition per class: 5/A (2 pupils) one sheet, 6/A (3 pupils) two sheets.
    pages = pdf_text(data)
    assert len(pages) == 3
    assert "Synthetic Student One" in pages[0] and "Pupil Gamma" in pages[1]


async def test_per_class_zip_has_one_pdf_per_class(api, world, queued) -> None:
    await three_pupil_class(world)
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "per_class"}
    _, data, _ = await run_job(api, world.admin, queued, body)
    with ZipFile(BytesIO(data)) as bundle:
        names = bundle.namelist()
        assert names == [
            f"5-A İngilizce Karne {TERM}.pdf",
            f"6-A İngilizce Karne {TERM}.pdf",
        ]
        first = pdf_text(bundle.read(names[0]))
        second = pdf_text(bundle.read(names[1]))
    assert len(first) == 1 and len(second) == 2
    assert "Pupil" not in "".join(first)
    assert "Synthetic Student" not in "".join(second)


async def test_per_student_zip_holds_exactly_each_pupils_card(api, world, queued) -> None:
    await three_pupil_class(world)
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "per_student"}
    _, data, _ = await run_job(api, world.admin, queued, body)
    expected = {
        f"5-A 51001 Synthetic Student One İngilizce Karne {TERM}.pdf": "Synthetic Student One",
        f"5-A 51002 Synthetic Student Two İngilizce Karne {TERM}.pdf": "Synthetic Student Two",
        f"6-A 6001 Pupil Alpha İngilizce Karne {TERM}.pdf": "Pupil Alpha",
        f"6-A 6002 Pupil Beta İngilizce Karne {TERM}.pdf": "Pupil Beta",
        f"6-A 6003 Pupil Gamma İngilizce Karne {TERM}.pdf": "Pupil Gamma",
    }
    names = list(expected.values())
    with ZipFile(BytesIO(data)) as bundle:
        assert bundle.namelist() == list(expected)
        for entry, owner in expected.items():
            # A middle-school card printed alone: one page, this pupil only.
            (page,) = pdf_text(bundle.read(entry))
            assert owner in page
            assert not [name for name in names if name != owner and name in page]


async def test_per_student_zip_splits_duplex_cards_two_pages_each(api, world, queued) -> None:
    await add_german(world, world.student_one, world.student_two)
    body = {
        "semester_id": world.semester,
        "kind": "german_karne",
        "format": "per_student",
        "student_ids": [world.student_one, world.student_two],
    }
    _, data, _ = await run_job(api, world.admin, queued, body)
    with ZipFile(BytesIO(data)) as bundle:
        names = bundle.namelist()
        assert names == [
            f"5-A 51001 Synthetic Student One Almanca Karne {TERM}.pdf",
            f"5-A 51002 Synthetic Student Two Almanca Karne {TERM}.pdf",
        ]
        for entry, owner, other in zip(
            names,
            ["Synthetic Student One", "Synthetic Student Two"],
            ["Synthetic Student Two", "Synthetic Student One"],
            strict=True,
        ):
            pages = pdf_text(bundle.read(entry))
            assert len(pages) == 2
            assert owner in "".join(pages) and other not in "".join(pages)


async def test_selected_students_job_prints_only_them(api, world, queued) -> None:
    pupils = await three_pupil_class(world)
    body = {
        "semester_id": world.semester,
        "kind": "english_middle",
        "format": "combined",
        "student_ids": [world.student_two, pupils.students[2]],
    }
    job, data, _ = await run_job(api, world.admin, queued, body)
    assert job["output_filename"] == f"Seçili Öğrenciler İngilizce Karne {TERM}.pdf"
    text = "".join(pdf_text(data))
    assert "Synthetic Student Two" in text and "Pupil Gamma" in text
    assert "Synthetic Student One" not in text and "Pupil Alpha" not in text


async def test_a_page_mapping_mismatch_fails_the_job_instead_of_misfiling(
    api, world, queued, monkeypatch
) -> None:
    original = packaging.render_report_pdf

    def one_page_short(cards, *, one_card_per_sheet=False):
        pdf = original(cards, one_card_per_sheet=one_card_per_sheet)
        # Every karne is two pages; keep only the first, as a layout overflow bug might.
        return next(packaging.split_pdf(pdf, 1, 2 * len(cards)))

    monkeypatch.setattr(packaging, "render_report_pdf", one_page_short)
    await add_german(world, world.student_one)
    async with api(world.admin) as client:
        created = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "german_karne", "format": "per_student"},
        )
        job_id = created.json()["id"]
        report_tasks.report_set_job(job_id)
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        download = await client.get(f"/api/jobs/{job_id}/download")
    assert job["status"] == "failed"
    assert job["error_code"] == "report_page_mapping"
    assert download.status_code == 409


async def test_a_set_that_cannot_fit_the_output_budget_stops_early(world, monkeypatch) -> None:
    await three_pupil_class(world)
    with Session(create_engine(TEST_URL_SYNC)) as db:
        entries = build_report_entries(
            db, semester_id=world.semester, kind="english_middle", locale="tr"
        )
    classes = packaging.group_by_class(entries)
    rendered: list[int] = []
    original = packaging.render_report_pdf

    def counting(cards, *, one_card_per_sheet=False):
        rendered.append(len(cards))
        return original(cards, one_card_per_sheet=one_card_per_sheet)

    monkeypatch.setattr(packaging, "render_report_pdf", counting)
    one_card = len(original([entries[0].card], one_card_per_sheet=True))
    with pytest.raises(packaging.ReportPackagingError, match="report_output_too_large"):
        # Room for about two of the five pupils: the projection stops after the first class.
        packaging.package_report_set(classes, "per_student", max_bytes=one_card * 2)
    assert rendered == [2]
    # The same set fits a budget sized for it.
    data, mime = packaging.package_report_set(classes, "per_student", max_bytes=one_card * 10)
    assert mime == "application/zip"
    with ZipFile(BytesIO(data)) as bundle:
        assert len(bundle.namelist()) == 5


async def test_class_sheet_download_is_named_for_its_classes(api, world) -> None:
    second = await add_class(world, 7, "B", [("Seventh Pupil", 7001)])
    async with api(world.main) as client:
        single = await client.get(
            "/api/reports/class-sheets",
            params={"semester_id": world.semester, "class_id": world.cls},
        )
        several = await client.get(
            "/api/reports/class-sheets",
            params={"semester_id": world.semester, "class_id": [world.cls, second.id]},
        )
    assert disposition_name(single.headers["content-disposition"]) == quote(
        f"5-A Sınıf Raporu {TERM}.pdf", safe=""
    )
    assert disposition_name(several.headers["content-disposition"]) == quote(
        f"Sınıf Raporları {TERM}.pdf", safe=""
    )
