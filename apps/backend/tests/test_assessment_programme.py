import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from flrc.cli import seed_columns
from flrc.db import models as m
from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.render import karne_sheet, render_report_html
from tests.conftest import TEST_URL_SYNC, TestSession


def column_body(subject: str, value_type: str, grade: int = 4) -> dict[str, object]:
    return {
        "grade_level": grade,
        "subject": subject,
        "value_type": value_type,
        "owner_role": subject,
        "labels": {"tr": f"Synthetic {value_type}"},
    }


@pytest.mark.parametrize("subject", ["german", "french"])
async def test_grade_four_l2_create_update_and_copy(api, world, subject):
    async with api(world.main) as client:
        denied = await client.post("/api/columns", json=column_body(subject, "scale3"))
    assert denied.status_code == 403
    async with api(world.admin) as client:
        rejected = await client.post("/api/columns", json=column_body(subject, "score"))
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "grade_four_l2_scale_only"
        for value_type in ("score", "scale3", "text"):
            older = await client.post("/api/columns", json=column_body(subject, value_type, 5))
            assert older.status_code == 201
        copied = await client.post(
            "/api/columns/copy",
            json={
                "source_grade_level": 5,
                "source_subject": subject,
                "target_grade_level": 4,
                "target_subject": subject,
            },
        )
        assert copied.status_code == 200
        assert copied.json() == {"copied": 2}
        columns = await client.get("/api/columns", params={"grade_level": 4, "subject": subject})
        assert [c["value_type"] for c in columns.json()] == ["scale3", "text"]
        column_id = columns.json()[0]["id"]
        for body in ({"value_type": "score"}, {"counts_in_average": True}):
            rejected = await client.patch(f"/api/columns/{column_id}", json=body)
            assert rejected.status_code == 422
        created = await client.post("/api/columns", json=column_body(subject, "scale3"))
        assert created.status_code == 201
        assert created.json()["counts_in_average"] is False
        note = await client.post("/api/columns", json=column_body(subject, "text"))
        assert note.status_code == 201
        assert note.json()["counts_in_average"] is False
        changed = await client.patch(
            f"/api/columns/{created.json()['id']}", json={"value_type": "text"}
        )
        assert changed.status_code == 200
        assert changed.json()["value_type"] == "text"
        average = await client.post(
            "/api/columns", json={**column_body(subject, "scale3"), "counts_in_average": True}
        )
        assert average.status_code == 422


async def test_seed_includes_teacher_comments_without_grade_four_numeric_scores(world):
    with Session(create_engine(TEST_URL_SYNC)) as db:
        seed_columns(db, world.semester)
        db.flush()
        columns = list(db.scalars(select(m.ColumnDefinition)))
        for subject in ("german", "french"):
            primary = [c for c in columns if c.grade_level == 4 and c.subject == subject]
            older = [c for c in columns if c.grade_level == 5 and c.subject == subject]
            assert primary and {c.value_type for c in primary} == {"scale3", "text"}
            assert not any(c.counts_in_average for c in primary)
            assert {c.value_type for c in older} == {"scale3", "score", "text"}
        for grade in range(1, 9):
            english = [c for c in columns if c.grade_level == grade and c.subject == "english"]
            notes = [c for c in english if c.value_type == "text"]
            assert len(notes) == 1
            assert notes[0].position == max(c.position for c in english)


async def test_correction_preserves_history_and_updates_grids_and_reports(api, world):
    async with TestSession() as db:
        school_class = await db.get(m.SchoolClass, world.cls)
        school_class.grade_level = 4
        archived = m.AcademicYear(label="Synthetic archive", status="archived")
        setup = m.AcademicYear(label="Synthetic setup", status="setup")
        db.add_all([archived, setup])
        await db.flush()
        old_term = m.Semester(year_id=archived.id, number=1, status="locked")
        setup_term = m.Semester(year_id=setup.id, number=1, status="open")
        db.add_all([old_term, setup_term])
        await db.flush()
        for subject, student in (("german", world.student_one), ("french", world.student_two)):
            db.add(m.StudentLanguage(student_id=student, year_id=world.year, language=subject))
        column_ids: dict[tuple[int, str, str], int] = {}
        for term in (world.semester, old_term.id, setup_term.id):
            for subject in ("german", "french"):
                for position, value_type in enumerate(("score", "scale3", "text"), 1):
                    column = m.ColumnDefinition(
                        semester_id=term,
                        grade_level=4,
                        subject=subject,
                        value_type=value_type,
                        owner_role=subject,
                        labels={"tr": f"Synthetic {value_type}"},
                        counts_in_average=value_type == "score",
                        position=position,
                    )
                    db.add(column)
                    await db.flush()
                    column_ids[term, subject, value_type] = column.id
        saved = m.GradeValue(
            student_id=world.student_one,
            column_definition_id=column_ids[world.semester, "german", "score"],
            score=85,
            version=3,
            updated_by=world.admin.id,
        )
        db.add(saved)
        await db.commit()
        saved_id = saved.id
        archived_term_id, setup_term_id = old_term.id, setup_term.id

    path = Path("migrations/versions/f4b82d903e61_grade_four_l2_scale_only.py")
    spec = importlib.util.spec_from_file_location("programme_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(TEST_URL_SYNC)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        migration.upgrade()
    with Session(engine) as db:
        for (term, _subject, value_type), column_id in column_ids.items():
            column = db.get(m.ColumnDefinition, column_id)
            assert column.is_active == (term == archived_term_id or value_type == "scale3")
            if term in (world.semester, setup_term_id):
                assert column.counts_in_average is False
        saved = db.get(m.GradeValue, saved_id)
        assert (saved.score, saved.version) == (85, 3)
        assert db.get(m.ColumnDefinition, world.main_column).is_active
        for subject in ("german", "french"):
            cards = build_report_set(
                db, semester_id=world.semester, kind=f"{subject}_karne", locale="tr"
            )
            assert len(cards) == 1
            assert [field.value_type for field in cards[0].fields] == ["scale3"]
            sheet = karne_sheet(cards[0])
            assert not sheet["comments"] and not sheet["show_grade"]
            html = render_report_html(cards)
            assert "Synthetic scale3" in html
            assert "Synthetic score" not in html and "Synthetic text" not in html
    async with api(world.admin) as client:
        for subject in ("german", "french"):
            grid = await client.get(f"/api/classes/{world.cls}/grid", params={"subject": subject})
            assert grid.status_code == 200
            assert [c["value_type"] for c in grid.json()["columns"]] == ["scale3"]
            assert len(grid.json()["rows"]) == 1


async def test_rollover_does_not_reintroduce_legacy_grade_four_scores(api, world):
    async with TestSession() as db:
        year = await db.get(m.AcademicYear, world.year)
        year.label = "2026-2027"
        term = await db.get(m.Semester, world.semester)
        term.status = "locked"
        for subject in ("german", "french"):
            for index, value_type in enumerate(("score", "scale3", "text"), 1):
                db.add(
                    m.ColumnDefinition(
                        semester_id=world.semester,
                        grade_level=4,
                        subject=subject,
                        value_type=value_type,
                        owner_role=subject,
                        labels={"tr": f"Synthetic {value_type}"},
                        counts_in_average=True,
                        position=index,
                    )
                )
        await db.commit()
    async with api(world.admin) as client:
        exported = await client.get(f"/api/admin/years/{world.year}/audit-export.csv")
        closed = await client.post(
            f"/api/admin/years/{world.year}/close",
            json={"confirm_label": "2026-2027", "audit_sha256": exported.headers["x-audit-sha256"]},
        )
        assert closed.status_code == 200
    async with TestSession() as db:
        target = await db.scalar(select(m.AcademicYear).where(m.AcademicYear.label == "2027-2028"))
        assert target and target.status == "setup"
        columns = list(
            (
                await db.execute(
                    select(m.ColumnDefinition)
                    .join(m.Semester)
                    .where(m.Semester.year_id == target.id, m.ColumnDefinition.grade_level == 4)
                )
            ).scalars()
        )
        assert {(c.subject, c.value_type) for c in columns} == {
            ("german", "scale3"),
            ("german", "text"),
            ("french", "scale3"),
            ("french", "text"),
        }
        assert all(not c.counts_in_average for c in columns)
