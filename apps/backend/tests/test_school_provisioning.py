import io

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from flrc import cli
from flrc.config import settings
from flrc.db import models as m
from tests.conftest import TEST_URL_SYNC, TestSession

runner = CliRunner()


@pytest.fixture
def school_db(monkeypatch):
    engine = create_engine(TEST_URL_SYNC)
    monkeypatch.setattr(cli, "sync_engine", lambda: engine)
    monkeypatch.setattr(settings, "allowed_google_domain", "school.example")
    yield engine
    engine.dispose()


def bootstrap(email="admin@school.example"):
    return runner.invoke(
        cli.app,
        ["bootstrap-admin", "--email", email, "--name", "Synthetic Administrator"],
    )


def test_bootstrap_creates_only_one_middle_english_administrator(school_db):
    result = bootstrap(" ADMIN@school.example ")
    assert result.exit_code == 0, result.output
    with Session(school_db) as db:
        admin = db.scalars(select(m.User)).one()
        assert admin.email == "admin@school.example"
        assert admin.full_name == "Synthetic Administrator"
        assert admin.is_admin and admin.is_active
        assert not admin.is_coordinator
        assert admin.teaching_field == "english"
        assert admin.teaching_stage == "middle"
        assert admin.google_subject is None
        for model in (
            m.AcademicYear,
            m.SchoolClass,
            m.Student,
            m.TeachingAssignment,
            m.ColumnDefinition,
            m.DemoVisitor,
        ):
            assert db.scalar(select(func.count()).select_from(model)) == 0

    assert bootstrap().exit_code == 0
    assert bootstrap("second@school.example").exit_code != 0
    with Session(school_db) as db:
        assert db.scalar(select(func.count()).select_from(m.User)) == 1


def test_bootstrap_rejects_non_school_identity_without_creating_users(school_db):
    assert bootstrap("admin@outside.example").exit_code != 0
    with Session(school_db) as db:
        assert db.scalar(select(func.count()).select_from(m.User)) == 0


async def test_empty_school_import_and_manual_teacher_creation(api, school_db):
    result = bootstrap()
    assert result.exit_code == 0, result.output
    async with TestSession() as db:
        admin = (await db.scalars(select(m.User))).one()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "5-A"
    sheet.append(["Okul No", "Ad Soyad", "2. Yabancı Dil"])
    sheet.append([101, "Synthetic First Pupil", "Almanca"])
    sheet.append([102, "Synthetic Second Pupil", "Fransızca"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    files = {"file": ("synthetic-roster.xlsx", buffer.getvalue())}

    async with api(admin) as client:
        assert (await client.get("/api/admin/years")).json() == []
        created_year = await client.post("/api/admin/years", json={"label": "2026-2027"})
        assert created_year.status_code == 201, created_year.text
        year = created_year.json()
        assert year["status"] == "setup"
        assert [term["status"] for term in year["semesters"]] == ["locked", "locked"]
        year_id = year["id"]
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": year_id}, files=files
        )
        assert preview.status_code == 200, preview.text
        review = preview.json()
        assert len(review["rows"]) == 2
        assert all("new_student" in row["actions"] for row in review["rows"])
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": year_id,
                "expected_sha256": review["sha256"],
                "expected_review_sha256": review["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text
        assert len((await client.get("/api/admin/users")).json()) == 1
        classes = (await client.get(f"/api/admin/years/{year_id}/classes")).json()
        assert len(classes) == 1
        assert classes[0]["student_count"] == 2
        assignment_url = f"/api/admin/years/{year_id}/assignments"
        sole_admin_assignment = await client.put(
            assignment_url,
            json={"changes": [{"class_id": classes[0]["id"], "role": "main", "user_id": admin.id}]},
        )
        assert sole_admin_assignment.status_code == 200, sole_admin_assignment.text
        teacher = await client.post(
            "/api/admin/users",
            json={
                "email": "teacher@school.example",
                "full_name": "Synthetic New Teacher",
                "teaching_field": "english",
                "teaching_stage": "middle",
            },
        )
        assert teacher.status_code == 201, teacher.text
        assert teacher.json()["is_active"]
        assert not teacher.json()["is_admin"]
        assert not teacher.json()["is_coordinator"]
        assert teacher.json()["teaching_field"] == "english"
        assert teacher.json()["teaching_stage"] == "middle"
        assignment = await client.put(
            assignment_url,
            json={
                "changes": [
                    {
                        "class_id": classes[0]["id"],
                        "role": "skills",
                        "user_id": teacher.json()["id"],
                    }
                ]
            },
        )
        assert assignment.status_code == 200, assignment.text
        activated = await client.post(f"/api/admin/years/{year_id}/activate")
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "active"
        assert [term["status"] for term in activated.json()["semesters"]] == ["open", "locked"]

    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.User)) == 2
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2
        assert await db.scalar(select(func.count()).select_from(m.Enrollment)) == 2
        assert await db.scalar(select(func.count()).select_from(m.StudentLanguage)) == 2
        assert await db.scalar(select(func.count()).select_from(m.TeachingAssignment)) == 2
        for model in (m.DemoVisitor, m.ColumnDefinition, m.GradeValue):
            assert await db.scalar(select(func.count()).select_from(model)) == 0
