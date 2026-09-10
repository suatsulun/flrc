"""Existing schools receive comment fields without losing report history."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.modules.reports.builder import build_report_set
from flrc.modules.reports.render import karne_sheet
from tests.conftest import TEST_URL_SYNC, TestSession


async def test_missing_notes_migration_preserves_history_and_can_save_comments(api, world):
    async with TestSession() as db:
        school_class = await db.get(m.SchoolClass, world.cls)
        school_class.grade_level = 4
        archived = m.AcademicYear(label="Synthetic archive", status="archived")
        setup = m.AcademicYear(label="Synthetic setup", status="setup")
        db.add_all([archived, setup])
        await db.flush()
        archive_term = m.Semester(year_id=archived.id, number=1, status="locked")
        setup_term = m.Semester(year_id=setup.id, number=1, status="open")
        db.add_all([archive_term, setup_term])
        await db.flush()
        db.add(
            m.StudentLanguage(student_id=world.student_one, year_id=world.year, language="german")
        )
        db.add(m.TeachingAssignment(class_id=world.cls, role="german", user_id=world.admin.id))
        definitions = []
        for term in (world.semester, archive_term.id, setup_term.id):
            for subject in ("german", "french"):
                definitions.append(
                    m.ColumnDefinition(
                        semester_id=term,
                        grade_level=4,
                        subject=subject,
                        value_type="scale3",
                        owner_role=subject,
                        labels={"tr": "Synthetic assessment"},
                        position=1,
                    )
                )
        old_note = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=4,
            subject="german",
            value_type="text",
            owner_role="german",
            labels={"tr": "Disabled historical comments"},
            position=9,
            is_active=False,
        )
        existing_note = m.ColumnDefinition(
            semester_id=setup_term.id,
            grade_level=4,
            subject="french",
            value_type="text",
            owner_role="french",
            labels={"tr": "Custom existing comments"},
            position=2,
        )
        db.add_all([*definitions, old_note, existing_note])
        await db.flush()
        old_value = m.GradeValue(
            student_id=world.student_one,
            column_definition_id=old_note.id,
            text_value="Retained historical note",
            version=6,
            updated_by=world.admin.id,
        )
        db.add(old_value)
        await db.commit()
        archive_id, setup_id = archive_term.id, setup_term.id
        old_note_id, old_value_id, existing_note_id = old_note.id, old_value.id, existing_note.id

    path = Path("migrations/versions/7d26cb91a540_restore_teacher_notes.py")
    spec = importlib.util.spec_from_file_location("teacher_notes_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(TEST_URL_SYNC)
    with Session(engine) as db:
        before = {
            c.id: (c.is_active, c.position, c.labels)
            for c in db.scalars(select(m.ColumnDefinition))
        }
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        migration.upgrade()  # Existing active comments make this idempotent.
        migration.downgrade()  # A code rollback must not delete any notes.
    with Session(engine) as db:
        columns = list(db.scalars(select(m.ColumnDefinition)))
        added = [c for c in columns if c.id not in before]
        assert len(added) == 4  # Active German/French/English and setup German.
        assert all(
            c.value_type == "text" and c.is_active and not c.counts_in_average for c in added
        )
        assert all(set(c.labels) == {"tr", "en", "de", "fr"} for c in added)
        for c in columns:
            if c.id in before:
                assert (c.is_active, c.position, c.labels) == before[c.id]
        assert not db.get(m.ColumnDefinition, old_note_id).is_active
        old = db.get(m.GradeValue, old_value_id)
        assert (old.text_value, old.version) == ("Retained historical note", 6)
        assert db.get(m.ColumnDefinition, existing_note_id).is_active
        assert not any(c.semester_id == archive_id for c in added)
        assert not any(c.semester_id == setup_id and c.subject == "french" for c in added)
        german = next(c for c in added if c.semester_id == world.semester and c.subject == "german")
        assert german.position == 10
        assert german.owner_role == "german"
        assert next(c for c in added if c.subject == "english").owner_role == "main"
        comment_id = german.id

    async with api(world.admin) as client:
        grid = await client.get(f"/api/classes/{world.cls}/grid", params={"subject": "german"})
        assert grid.status_code == 200
        assert [c["value_type"] for c in grid.json()["columns"]] == ["scale3", "text"]
        saved = await client.post(
            f"/api/classes/{world.cls}/grid/save",
            json={
                "subject": "german",
                "cells": [
                    {
                        "student_id": world.student_one,
                        "column_id": comment_id,
                        "value": "Synthetic current teacher note",
                        "expected_version": 0,
                    }
                ],
            },
        )
        assert saved.status_code == 200
        assert saved.json()["applied"] == [
            {"student_id": world.student_one, "column_id": comment_id, "version": 1}
        ]
    with Session(engine) as db:
        cards = build_report_set(db, semester_id=world.semester, kind="german_karne", locale="tr")
        sheet = karne_sheet(cards[0])
        assert not sheet["show_grade"]
        assert "Synthetic current teacher note" in str(sheet["comments"])
        audit = db.scalar(
            select(m.AuditEntry).where(m.AuditEntry.column_definition_id == comment_id)
        )
        assert audit is not None
