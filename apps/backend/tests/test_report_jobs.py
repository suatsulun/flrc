"""Report downloads, background report jobs, the student picker and download names (ADR-077)."""

import asyncio
import os
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4
from zipfile import ZipFile

import pikepdf
import pytest
from kombu.exceptions import OperationalError
from pypdf import PdfReader
from redis.asyncio import Redis
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session

from flrc.config import settings
from flrc.core import rate_limit
from flrc.db import models as m
from flrc.modules.jobs import service as jobs_service
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


def test_ascii_fallback_cannot_gain_quotes_from_compatibility_characters() -> None:
    # NFKD turns fullwidth quotes and backslashes into ASCII ones; the quoted fallback must
    # still hold exactly one name, not a second parameter taken from a stored pupil name.
    header = content_disposition("8-A 1 Ali ＂; filename=＂evil＼.pdf")
    assert header.startswith('attachment; filename="8-A 1 Ali ; filename=evil.pdf"; ')
    fallback = header.split("; filename*=", 1)[0]
    assert fallback.count('"') == 2 and "\\" not in fallback
    assert disposition_name(header) == quote("8-A 1 Ali ＂; filename=＂evil＼.pdf", safe="")
    # A name made only of such characters still gets a usable fallback.
    assert content_disposition("＂＂").startswith('attachment; filename="download"')


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
    api, world, queued, rate_limits, monkeypatch
) -> None:
    # Four scopes are queued here at once; the waiting-job cap has its own test.
    monkeypatch.setattr(reports_router, "MAX_PENDING_REPORT_JOBS", 10)
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


async def test_each_account_has_a_bounded_number_of_waiting_report_jobs(
    api, world, queued, rate_limits
) -> None:
    coordinator = await add_coordinator()
    limit = reports_router.MAX_PENDING_REPORT_JOBS
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "combined"}
    async with api(coordinator) as client:
        # Simultaneous requests cannot all pass the check before any of them is recorded.
        responses = await asyncio.gather(
            *(client.post("/api/reports/jobs", json=body) for _ in range(limit + 2))
        )
    assert sorted(response.status_code for response in responses) == [202] * limit + [409] * 2
    refused = [response for response in responses if response.status_code == 409]
    assert {response.json()["detail"]["code"] for response in refused} == {"report_jobs_pending"}
    assert len(queued) == limit
    await rate_limits()

    # Another account's waiting work is its own.
    async with api(world.admin) as client:
        assert (await client.post("/api/reports/jobs", json=body)).status_code == 202
    # A finished job frees its place.
    async with TestSession() as db:
        finished = await db.get(m.JobRun, queued[0])
        assert finished is not None
        finished.status = "failed"
        await db.commit()
    async with api(coordinator) as client:
        assert (await client.post("/api/reports/jobs", json=body)).status_code == 202
        assert (await client.post("/api/reports/jobs", json=body)).status_code == 409


async def test_staged_parts_of_a_split_job_do_not_count_as_waiting_jobs(api, world, queued) -> None:
    limit = reports_router.MAX_PENDING_REPORT_JOBS
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "per_student"}
    async with api(world.admin) as client:
        created = await client.post("/api/reports/jobs", json=body)
        assert created.status_code == 202
    # The job is splitting its output: each finished part is staged as a running row under it.
    with Session(create_engine(TEST_URL_SYNC)) as db:
        job = db.get(m.JobRun, created.json()["id"])
        assert job is not None
        jobs_service.mark_running(db, job, total=2)
        for number in range(1, limit + 1):
            jobs_service.store_part(
                db, job, number=number, filename=f"part {number}.zip", data=b"zip"
            )
    async with api(world.admin) as client:
        # One request is waiting, however many parts it has staged.
        for _ in range(limit - 1):
            assert (await client.post("/api/reports/jobs", json=body)).status_code == 202
        refused = await client.post("/api/reports/jobs", json=body)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "report_jobs_pending"


def refuse_publication(_job_id: int) -> None:
    raise OperationalError("Error 111 connecting to the broker")


async def test_a_job_the_queue_refuses_fails_instead_of_waiting_forever(
    api, world, queued, monkeypatch
) -> None:
    monkeypatch.setattr(reports_router.report_set_job, "delay", refuse_publication)
    monkeypatch.setattr(reports_router.export_year_job, "delay", refuse_publication)
    pinged: list[bool] = []

    async def ping() -> None:
        pinged.append(True)

    monkeypatch.setattr(reports_router, "ping_worker_best_effort", ping)
    async with api(world.admin) as client:
        report = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "english_middle", "format": "combined"},
        )
        export = await client.post(f"/api/exports/year/{world.year}")
        jobs = (await client.get("/api/jobs")).json()
    for response in (report, export):
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "job_queue_unavailable"
    assert [(job["kind"], job["status"], job["error_code"]) for job in jobs] == [
        ("year_export", "failed", "job_queue_unavailable"),
        ("report_set", "failed", "job_queue_unavailable"),
    ]
    assert pinged == []
    # Both are finished, so neither counts against the account's waiting jobs.
    async with TestSession() as db:
        assert all(job.finished_at for job in await db.scalars(select(m.JobRun)))


async def test_listing_waiting_jobs_wakes_the_worker(api, world, queued, monkeypatch) -> None:
    pinged: list[bool] = []

    async def ping() -> None:
        pinged.append(True)

    monkeypatch.setattr(reports_router, "ping_worker_best_effort", ping)
    async with api(world.admin) as client:
        assert (await client.get("/api/jobs")).json() == []
        assert pinged == []
        created = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "english_middle", "format": "combined"},
        )
        assert created.status_code == 202
        pinged.clear()
        # The downloads list polls the list, not each job: a lost wake-up is sent again.
        assert [job["status"] for job in (await client.get("/api/jobs")).json()] == ["queued"]
        assert pinged == [True]
        report_tasks.report_set_job(created.json()["id"])
        pinged.clear()
        assert [job["status"] for job in (await client.get("/api/jobs")).json()] == ["succeeded"]
    assert pinged == []


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


async def test_a_selected_pupil_who_left_the_set_fails_the_job(api, world, queued) -> None:
    await add_german(world, world.student_one, world.student_two)
    body = {
        "semester_id": world.semester,
        "kind": "german_karne",
        "format": "combined",
        "student_ids": [world.student_one, world.student_two],
    }
    async with api(world.admin) as client:
        created = await client.post("/api/reports/jobs", json=body)
        assert created.status_code == 202, created.text
        # Before the worker starts, one of the two changes to French.
        async with TestSession() as db:
            language = await db.scalar(
                select(m.StudentLanguage).where(m.StudentLanguage.student_id == world.student_two)
            )
            assert language is not None
            language.language = "french"
            await db.commit()
        report_tasks.report_set_job(created.json()["id"])
        job = (await client.get(f"/api/jobs/{created.json()['id']}")).json()
    # The file would silently miss a pupil the admin chose, so none is made.
    assert (job["status"], job["error_code"]) == ("failed", "student_not_in_report_set")
    assert job["output_size"] is None


async def test_a_chosen_class_whose_pupils_all_left_the_set_fails_the_job(
    api, world, queued
) -> None:
    await add_german(world, world.student_one)
    other = await add_class(world, 5, "B", [("German Only", 5301)], language="german")
    body = {
        "semester_id": world.semester,
        "kind": "german_karne",
        "format": "per_class",
        "class_ids": [world.cls, other.id],
    }
    async with api(world.admin) as client:
        created = await client.post("/api/reports/jobs", json=body)
        assert created.status_code == 202, created.text
        # Before the worker starts, 5/B's only German pupil changes to French.
        async with TestSession() as db:
            language = await db.scalar(
                select(m.StudentLanguage).where(m.StudentLanguage.student_id == other.students[0])
            )
            assert language is not None
            language.language = "french"
            await db.commit()
        report_tasks.report_set_job(created.json()["id"])
        job = (await client.get(f"/api/jobs/{created.json()['id']}")).json()
    # The file would silently miss a class the admin chose, so none is made.
    assert (job["status"], job["error_code"]) == ("failed", "class_not_in_report_set")
    assert job["output_size"] is None


async def test_a_page_mapping_mismatch_fails_the_job_instead_of_misfiling(
    api, world, queued, monkeypatch
) -> None:
    original = packaging.render_cards_to_file

    def one_page_short(cards, output, **options):
        original(cards, output, **options)
        # Every karne is two pages; keep only the first, as a layout overflow bug might.
        with pikepdf.open(output, allow_overwriting_input=True) as document:
            del document.pages[1:]
            document.save(output)
        return 1

    # The double must run in this process, not in a render process.
    monkeypatch.setattr(settings, "report_render_workers", 1)
    monkeypatch.setattr(packaging, "render_cards_to_file", one_page_short)
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


async def test_only_a_single_file_larger_than_a_part_fails_the_set(world, monkeypatch) -> None:
    await three_pupil_class(world)
    classes = middle_classes(world.semester)
    one_card = min(pupil_file_sizes(classes[0]))
    rendered: list[int] = []
    original = packaging.render_cards_to_file

    def counting(cards, output, **options):
        rendered.append(len(cards))
        return original(cards, output, **options)

    monkeypatch.setattr(settings, "report_render_workers", 1)
    monkeypatch.setattr(packaging, "render_cards_to_file", counting)
    with pytest.raises(packaging.ReportPackagingError, match="report_output_too_large"):
        packaging.package_report_set(classes, "per_student", max_bytes=one_card // 2)
    # The first pupil's file already cannot fit any part: nothing else is rendered.
    assert rendered == [2]


def pupil_file_sizes(class_set: packaging.ClassSet) -> list[int]:
    """The sizes of a class's pupil files, rendered exactly as a per-pupil job renders them."""
    with TemporaryDirectory() as folder:
        cards = [entry.card for entry in class_set.entries]
        paths = packaging.render_class_files(cards, folder, 0, "per_student", None)
        return [Path(path).stat().st_size for path in paths]


def class_file_size(class_set: packaging.ClassSet) -> int:
    with TemporaryDirectory() as folder:
        cards = [entry.card for entry in class_set.entries]
        (path,) = packaging.render_class_files(cards, folder, 0, "per_class", None)
        return Path(path).stat().st_size


def zip_names(data: bytes) -> list[str]:
    with ZipFile(BytesIO(data)) as bundle:
        return bundle.namelist()


async def test_an_oversized_pupil_zip_splits_into_parts_between_whole_files(world) -> None:
    await three_pupil_class(world)
    classes = middle_classes(world.semester)
    largest = max(pupil_file_sizes(classes[0]))
    # Room for two pupil files per part, never three.
    overhead = packaging.ARCHIVE_OVERHEAD + 2 * (packaging.ENTRY_OVERHEAD + 300)
    budget = int(largest * 2.1) + overhead
    parts: dict[int, bytes] = {}
    result = packaging.package_report_set(
        classes, "per_student", max_bytes=budget, on_part=parts.__setitem__
    )
    parts[result.parts] = result.data
    assert result.parts == len(parts) >= 2
    assert list(parts) == list(range(1, result.parts + 1))
    assert all(len(data) <= budget for data in parts.values())
    names = [name for number in sorted(parts) for name in zip_names(parts[number])]
    # Every pupil exactly once across the parts, in print order, each a whole one-page file.
    assert names == [
        f"5-A 51001 Synthetic Student One İngilizce Karne {TERM}.pdf",
        f"5-A 51002 Synthetic Student Two İngilizce Karne {TERM}.pdf",
        f"6-A 6001 Pupil Alpha İngilizce Karne {TERM}.pdf",
        f"6-A 6002 Pupil Beta İngilizce Karne {TERM}.pdf",
        f"6-A 6003 Pupil Gamma İngilizce Karne {TERM}.pdf",
    ]
    for data in parts.values():
        with ZipFile(BytesIO(data)) as bundle:
            for name in bundle.namelist():
                assert len(PdfReader(BytesIO(bundle.read(name))).pages) == 1


async def test_a_set_that_fits_one_part_stays_one_file(world) -> None:
    await three_pupil_class(world)
    parts: dict[int, bytes] = {}
    result = packaging.package_report_set(
        middle_classes(world.semester), "per_student", on_part=parts.__setitem__
    )
    assert result.parts == 1 and parts == {}
    assert len(zip_names(result.data)) == 5


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


def middle_classes(world_semester: int, student_ids: list[int] | None = None):
    with Session(create_engine(TEST_URL_SYNC)) as db:
        entries = build_report_entries(
            db,
            semester_id=world_semester,
            kind="english_middle",
            locale="tr",
            student_ids=student_ids,
        )
    return packaging.group_by_class(entries)


async def test_combined_set_is_joined_from_class_files_on_disk(world, monkeypatch) -> None:
    await three_pupil_class(world)
    await add_class(world, 7, "A", [("Seventh One", 7001), ("Seventh Two", 7002)])
    joined: list[list[int]] = []
    original = packaging.concatenate_pdfs

    def recording(files, output):
        # Each class is on disk, not in memory, by the time qpdf joins them.
        joined.append([path.stat().st_size for path in files])
        original(files, output)

    monkeypatch.setattr(packaging, "concatenate_pdfs", recording)
    result = packaging.package_report_set(middle_classes(world.semester), "combined")
    assert len(joined) == 1 and len(joined[0]) == 3 and all(joined[0])
    pages = pdf_text(result.data)
    # Two-up sheets per class, in print order: 5/A one sheet, 6/A two, 7/A one.
    assert len(pages) == 1 + 2 + 1
    assert "Synthetic Student One" in pages[0]
    assert "Pupil Alpha" in pages[1] and "Pupil Beta" in pages[2]
    assert "Seventh One" in pages[3]
    assert PdfReader(BytesIO(result.data)).metadata.title


async def test_class_zip_parts_hold_whole_class_files(world) -> None:
    pupils = await three_pupil_class(world)
    # One pupil from 5/A, then all three of 6/A: two class files, four pupils.
    classes = middle_classes(world.semester, [world.student_one, *pupils.students])
    assert [len(item.entries) for item in classes] == [1, 3]
    largest = max(class_file_size(item) for item in classes)
    budget = int(largest * 1.5) + packaging.ARCHIVE_OVERHEAD + packaging.ENTRY_OVERHEAD + 300
    parts: dict[int, bytes] = {}
    result = packaging.package_report_set(
        classes, "per_class", max_bytes=budget, on_part=parts.__setitem__
    )
    parts[result.parts] = result.data
    assert [zip_names(parts[number]) for number in sorted(parts)] == [
        [f"5-A İngilizce Karne {TERM}.pdf"],
        [f"6-A İngilizce Karne {TERM}.pdf"],
    ]
    assert all(len(data) <= budget for data in parts.values())


async def test_jobs_list_reaches_every_unexpired_download(api, world) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    async with TestSession() as db:
        for index in range(30):
            db.add(
                m.JobRun(
                    kind="report_set",
                    status="succeeded",
                    requested_by=world.admin.id,
                    payload={},
                    progress=1,
                    total=1,
                    output_filename=f"file {index}.pdf",
                    output_size=3,
                    output_blob=b"pdf",
                    output_expires_at=now + timedelta(hours=20),
                )
            )
        await db.flush()
        for index in range(30):
            db.add(
                m.JobRun(
                    kind="report_set",
                    status="succeeded",
                    requested_by=world.admin.id,
                    payload={},
                    progress=1,
                    total=1,
                    output_filename=f"newer expired {index}.pdf",
                    output_expires_at=now - timedelta(hours=1),
                )
            )
        await db.commit()
    async with api(world.admin) as client:
        listed = (await client.get("/api/jobs")).json()
    names = [job["output_filename"] for job in listed]
    # The 25 newest history rows, plus every older file that can still be downloaded.
    assert all(f"file {index}.pdf" in names for index in range(30))
    assert len(names) == 25 + 30
    assert [job["id"] for job in listed] == sorted((job["id"] for job in listed), reverse=True)


async def test_a_split_job_lists_numbered_parts_with_one_expiry_and_its_access(
    api, world, queued, monkeypatch
) -> None:
    await three_pupil_class(world)
    coordinator = await add_coordinator()
    classes = middle_classes(world.semester)
    largest = max(pupil_file_sizes(classes[1]))
    overhead = packaging.ARCHIVE_OVERHEAD + 2 * (packaging.ENTRY_OVERHEAD + 300)
    monkeypatch.setattr(packaging, "MAX_OUTPUT_BYTES", int(largest * 2.1) + overhead)
    body = {"semester_id": world.semester, "kind": "english_middle", "format": "per_student"}
    async with api(coordinator) as client:
        created = (await client.post("/api/reports/jobs", json=body)).json()
        report_tasks.report_set_job(created["id"])
        listed = (await client.get("/api/jobs")).json()
        request = next(job for job in listed if job["id"] == created["id"])
        parts = sorted(
            (job for job in listed if job["parent_id"] == created["id"]),
            key=lambda job: job["part"],
        )
        downloads = [await client.get(f"/api/jobs/{part['id']}/download") for part in parts]
        whole = await client.get(f"/api/jobs/{created['id']}/download")

    base = f"Tüm Okul İngilizce Karne {TERM}"
    assert request["status"] == "succeeded"
    assert request["output_filename"] == f"{base}.zip"
    assert [part["output_filename"] for part in parts] == [
        f"{base} (Bölüm {number}).zip" for number in range(1, len(parts) + 1)
    ]
    assert len(parts) == 3
    assert {part["output_expires_at"] for part in parts} == {request["output_expires_at"]}
    assert all(part["status"] == "succeeded" for part in parts)
    assert whole.status_code == 409
    assert whole.json()["detail"]["code"] == "job_output_in_parts"

    pupils: list[str] = []
    for part, download in zip(parts, downloads, strict=True):
        assert download.status_code == 200
        assert disposition_name(download.headers["content-disposition"]) == quote(
            part["output_filename"], safe=""
        )
        assert len(download.content) <= packaging.MAX_OUTPUT_BYTES
        pupils.extend(zip_names(download.content))
    assert len(pupils) == len(set(pupils)) == 5

    # Parts carry the request's access: another teacher cannot read them.
    async with api(world.main) as client:
        for part in parts:
            assert (await client.get(f"/api/jobs/{part['id']}/download")).status_code == 403

    # A part past its expiry is gone like any other output.
    async with TestSession() as db:
        first = await db.get(m.JobRun, parts[0]["id"])
        assert first is not None
        first.output_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        await db.commit()
    async with api(coordinator) as client:
        expired = await client.get(f"/api/jobs/{parts[0]['id']}/download")
    assert expired.status_code == 410


async def test_classes_are_built_only_as_render_processes_take_them(world, monkeypatch) -> None:
    await three_pupil_class(world)
    await add_class(world, 7, "A", [("Seventh One", 7001), ("Seventh Two", 7002)])
    classes = middle_classes(world.semester)
    monkeypatch.setattr(settings, "report_render_workers", 2)
    taken: list[int] = []

    def lazily():
        for class_set in classes:
            taken.append(class_set.class_id)
            yield class_set

    taken_when_done: list[int] = []
    result = packaging.package_report_set(
        lazily(), "per_class", lambda _done: taken_when_done.append(len(taken))
    )
    # Two render processes: a class is taken only when one of them can start on it, so the
    # job never holds more than two classes' cards (and never any class's PDF bytes).
    assert taken_when_done == [2, 3, 3]
    assert len(zip_names(result.data)) == 3


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def test_a_pupil_moved_mid_job_fails_the_set_instead_of_misfiling(
    api,
    world,
    queued,
    monkeypatch,  # noqa: F811
) -> None:
    other = await add_class(world, 6, "A", [("Pupil Alpha", 6001)])
    original = report_tasks.build_report_entries
    moved = False

    def move_then_build(db, **arguments):
        nonlocal moved
        if not moved:
            # Another admin moves a pupil while the job runs, before the first class renders.
            moved = True
            with Session(create_engine(TEST_URL_SYNC)) as other_db:
                other_db.execute(
                    update(m.Enrollment)
                    .where(m.Enrollment.student_id == world.student_two)
                    .values(class_id=other.id)
                )
                other_db.commit()
        return original(db, **arguments)

    monkeypatch.setattr(report_tasks, "build_report_entries", move_then_build)
    async with api(world.admin) as client:
        created = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "english_middle", "format": "per_class"},
        )
        job_id = created.json()["id"]
        report_tasks.report_set_job(job_id)
        job = (await client.get(f"/api/jobs/{job_id}")).json()
    # The pupil left 5/A after the set was frozen and was not in 6/A when it was: printing
    # would drop them silently, so the job refuses.
    assert job["status"] == "failed"
    assert job["error_code"] == "report_roster_changed"


def test_stale_workspaces_are_reclaimed_but_a_live_jobs_is_kept(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    live = tmp_path / f"{packaging.workspace_prefix(7)}abc"
    finished = tmp_path / f"{packaging.workspace_prefix(8)}def"
    stuck = tmp_path / f"{packaging.workspace_prefix(9)}ghi"
    unrelated = tmp_path / "something-else"
    for folder in (live, finished, stuck, unrelated):
        folder.mkdir()
        (folder / "class-0000.pdf").write_bytes(b"%PDF-")
    # Job 9 still says running, but nothing has touched its workspace for a day.
    old = time.time() - 24 * 3600
    os.utime(stuck, (old, old))

    removed = packaging.reclaim_workspaces(live_job_ids={7, 9})

    assert removed == 2
    assert live.exists() and unrelated.exists()
    assert not finished.exists() and not stuck.exists()


async def test_staged_parts_expire_on_their_own_and_purge_reclaims_aborted_ones(world) -> None:
    async with TestSession() as db:
        request = m.JobRun(
            kind="report_set", status="running", requested_by=world.admin.id, payload={}
        )
        db.add(request)
        await db.commit()
        request_id = request.id
    with Session(create_engine(TEST_URL_SYNC)) as db:
        job = db.get(m.JobRun, request_id)
        assert job is not None
        jobs_service.store_part(db, job, number=1, filename="part 1.zip", data=b"zip")
        part = db.scalar(select(m.JobRun).where(m.JobRun.parent_id == request_id))
        assert part is not None
        # Staged with a bounded expiry of its own, even before the set succeeds.
        assert part.output_expires_at is not None
        assert part.output_expires_at <= now() + jobs_service.STAGED_PART_TTL

        # The worker died before cleanup: the request failed and the part is past its bound.
        job.status = "failed"
        part.output_expires_at = now() - timedelta(seconds=1)
        db.commit()
        assert jobs_service.purge_job_outputs(db) == 1
        assert db.scalar(select(m.JobRun).where(m.JobRun.parent_id == request_id)) is None


async def test_a_finished_job_reclaims_the_workspace_of_its_interrupted_attempt(
    api, world, queued, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    async with api(world.admin) as client:
        created = await client.post(
            "/api/reports/jobs",
            json={"semester_id": world.semester, "kind": "english_middle", "format": "per_class"},
        )
        job_id = created.json()["id"]
    # A killed attempt left its PDFs behind, and the job still says running when the
    # redelivered attempt takes it, so neither the restart nor the new attempt may remove them.
    abandoned = tmp_path / f"{packaging.workspace_prefix(job_id)}killed"
    abandoned.mkdir()
    (abandoned / "class-0000.pdf").write_bytes(b"%PDF-")
    async with TestSession() as db:
        job = await db.get(m.JobRun, job_id)
        assert job is not None
        job.status = "running"
        await db.commit()

    report_tasks.report_set_job(job_id)

    async with TestSession() as db:
        job = await db.get(m.JobRun, job_id)
        assert job is not None
        assert job.status == "succeeded"
    # Once the job is finished, nothing of either attempt stays on disk.
    assert list(tmp_path.glob(f"{packaging.WORKSPACE_PREFIX}*")) == []


async def three_part_pupil_set(world, monkeypatch) -> dict[str, object]:
    """A per-pupil set of 5/A and 6/A that comes out in three parts."""
    await three_pupil_class(world)
    classes = middle_classes(world.semester)
    largest = max(pupil_file_sizes(classes[1]))
    overhead = packaging.ARCHIVE_OVERHEAD + 2 * (packaging.ENTRY_OVERHEAD + 300)
    monkeypatch.setattr(packaging, "MAX_OUTPUT_BYTES", int(largest * 2.1) + overhead)
    return {"semester_id": world.semester, "kind": "english_middle", "format": "per_student"}


def age_part(request_id: int, number: int) -> None:
    """Let a staged part's bound run out, as if it was stored more than six hours ago."""
    with Session(create_engine(TEST_URL_SYNC)) as other:
        other.execute(
            update(m.JobRun)
            .where(m.JobRun.parent_id == request_id, m.JobRun.part == number)
            .values(output_expires_at=now() - timedelta(seconds=1))
        )
        other.commit()


def nightly_purge() -> None:
    """The backup sidecar's purge, in its own connection while the job runs."""
    with Session(create_engine(TEST_URL_SYNC)) as other:
        jobs_service.purge_job_outputs(other)


async def test_a_split_job_that_keeps_advancing_keeps_its_staged_parts(
    api, world, queued, monkeypatch
) -> None:
    body = await three_part_pupil_set(world, monkeypatch)
    store, publish = report_tasks.store_part, report_tasks.mark_parts_succeeded

    def store_then_age(db, job, **part):
        store(db, job, **part)
        if part["number"] == 1:
            age_part(job.id, 1)

    def purge_then_publish(db, job, *args, **kwargs):
        # The job has finished classes since its first part: the purge must leave it alone.
        nightly_purge()
        publish(db, job, *args, **kwargs)

    monkeypatch.setattr(report_tasks, "store_part", store_then_age)
    monkeypatch.setattr(report_tasks, "mark_parts_succeeded", purge_then_publish)
    async with api(world.admin) as client:
        job_id = (await client.post("/api/reports/jobs", json=body)).json()["id"]
        report_tasks.report_set_job(job_id)
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        listed = (await client.get("/api/jobs")).json()

    assert job["status"] == "succeeded"
    parts = [item for item in listed if item["parent_id"] == job_id]
    assert sorted(part["part"] for part in parts) == [1, 2, 3]


async def test_purge_fails_a_stalled_split_job_instead_of_it_publishing_a_partial_set(
    api, world, queued, monkeypatch
) -> None:
    body = await three_part_pupil_set(world, monkeypatch)
    store = report_tasks.store_part

    def store_then_stall(db, job, **part):
        store(db, job, **part)
        if part["number"] == 1:
            # The job stops advancing past the staging bound right after its first part, and
            # the nightly purge reclaims that part before the job resumes.
            age_part(job.id, 1)
            nightly_purge()

    monkeypatch.setattr(report_tasks, "store_part", store_then_stall)
    async with api(world.admin) as client:
        job_id = (await client.post("/api/reports/jobs", json=body)).json()["id"]
        with pytest.raises(jobs_service.IncompletePartsError):
            report_tasks.report_set_job(job_id)
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        listed = (await client.get("/api/jobs")).json()

    assert job["status"] == "failed"
    assert job["error_code"] == "report_set_failed"
    assert [item for item in listed if item["parent_id"] == job_id] == []
    async with TestSession() as db:
        assert (
            await db.scalars(select(m.JobRun.id).where(m.JobRun.parent_id == job_id))
        ).all() == []


async def test_purge_spares_parts_a_job_renews_while_the_purge_waits(world, monkeypatch) -> None:
    async with TestSession() as db:
        request = m.JobRun(
            kind="report_set", status="running", requested_by=world.admin.id, payload={}
        )
        db.add(request)
        await db.commit()
        request_id = request.id
    engine = create_engine(TEST_URL_SYNC)
    with Session(engine) as worker, Session(engine) as observer:
        job = worker.get(m.JobRun, request_id)
        assert job is not None
        jobs_service.store_part(worker, job, number=1, filename="part 1.zip", data=b"zip")
        age_part(request_id, 1)
        # The job finishes a class at the six-hour boundary: its heartbeat has written the
        # request and renewed the part, but has not committed when the nightly purge starts.
        with monkeypatch.context() as patch:
            patch.setattr(worker, "commit", worker.flush)
            jobs_service.record_progress(worker, job, 1)
        purge = threading.Thread(target=nightly_purge)
        purge.start()
        deadline = time.monotonic() + 10
        while not observer.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        ):
            observer.rollback()
            assert time.monotonic() < deadline, "the purge never waited for the request row"
            time.sleep(0.05)
        worker.commit()
        purge.join(timeout=10)
        assert not purge.is_alive()

    with Session(engine) as db:
        # The purge waited for the heartbeat and saw the renewed part: nothing was reclaimed.
        assert db.get_one(m.JobRun, request_id).status == "running"
        part = db.scalar(select(m.JobRun).where(m.JobRun.parent_id == request_id))
        assert part is not None
        assert part.output_expires_at is not None and part.output_expires_at > now()


async def test_a_split_set_missing_a_part_is_never_published(world) -> None:
    async with TestSession() as db:
        request = m.JobRun(
            kind="report_set", status="running", requested_by=world.admin.id, payload={}
        )
        db.add(request)
        await db.commit()
        request_id = request.id
    with Session(create_engine(TEST_URL_SYNC)) as db:
        job = db.get(m.JobRun, request_id)
        assert job is not None
        for number in (2, 3):
            jobs_service.store_part(
                db, job, number=number, filename=f"part {number}.zip", data=b"zip"
            )
        with pytest.raises(jobs_service.IncompletePartsError):
            jobs_service.mark_parts_succeeded(db, job, parts=3)
        db.rollback()
        statuses = db.scalars(
            select(m.JobRun.status).where(
                (m.JobRun.id == request_id) | (m.JobRun.parent_id == request_id)
            )
        ).all()
        # Nothing was published: the request and both parts are still staged.
        assert statuses == ["running"] * 3


async def test_a_coordinator_sees_their_own_year_export(api, world) -> None:
    coordinator = await add_coordinator()
    async with TestSession() as db:
        mine = m.JobRun(
            kind="year_export", status="queued", requested_by=coordinator.id, payload={}
        )
        theirs = m.JobRun(
            kind="year_export", status="queued", requested_by=world.admin.id, payload={}
        )
        db.add_all([mine, theirs])
        await db.commit()
        mine_id, theirs_id = mine.id, theirs.id
    async with api(coordinator) as client:
        listed = {job["id"] for job in (await client.get("/api/jobs")).json()}
        assert (await client.get(f"/api/jobs/{mine_id}")).status_code == 200
    # The list shows exactly what the coordinator may open.
    assert mine_id in listed
    assert theirs_id not in listed
