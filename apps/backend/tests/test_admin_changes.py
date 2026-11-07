"""Undoable admin changes (ADR-075) and field renaming (ADR-076)."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from io import BytesIO
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import Session

from flrc.config import settings
from flrc.db import models as m
from flrc.modules.changes.service import (
    ADMIN_ACTION_TTL,
    purge_expired_actions,
    utcnow,
)
from tests.conftest import TEST_URL_SYNC, TestSession, cell, save_grid

SCHOOL_DOMAIN = "school.example"


@pytest.fixture(autouse=True)
def _school_domain(monkeypatch):
    monkeypatch.setattr(settings, "allowed_google_domain", SCHOOL_DOMAIN)


def png(color: str) -> bytes:
    data = BytesIO()
    Image.new("RGBA", (60, 20), color).save(data, format="PNG")
    return data.getvalue()


async def undo(client, action_id: int):
    return await client.post(f"/api/admin/actions/{action_id}/undo")


def assert_blocked(response, reason: str, **params) -> None:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "undo_blocked"
    assert detail["reason"] == reason
    for key, value in params.items():
        assert detail["params"][key] == value, detail


async def add_class(year_id: int, grade: int, section: str) -> int:
    async with TestSession() as db:
        school_class = m.SchoolClass(year_id=year_id, grade_level=grade, section=section)
        db.add(school_class)
        await db.commit()
        return school_class.id


async def placement(student_id: int, year_id: int) -> tuple[int, int | None] | None:
    async with TestSession() as db:
        row = (
            await db.execute(
                select(m.Enrollment.class_id, m.Enrollment.school_number).where(
                    m.Enrollment.student_id == student_id, m.Enrollment.year_id == year_id
                )
            )
        ).first()
        return None if row is None else (row[0], row[1])


async def language(student_id: int, year_id: int) -> str | None:
    async with TestSession() as db:
        return await db.scalar(
            select(m.StudentLanguage.language).where(
                m.StudentLanguage.student_id == student_id,
                m.StudentLanguage.year_id == year_id,
            )
        )


async def grade_row(student_id: int, column_id: int) -> tuple[int, int | None] | None:
    async with TestSession() as db:
        row = (
            await db.execute(
                select(m.GradeValue.id, m.GradeValue.score).where(
                    m.GradeValue.student_id == student_id,
                    m.GradeValue.column_definition_id == column_id,
                )
            )
        ).first()
        return None if row is None else (row[0], row[1])


async def column_row(column_id: int) -> m.ColumnDefinition | None:
    async with TestSession() as db:
        return await db.get(m.ColumnDefinition, column_id)


# Students -------------------------------------------------------------------


async def test_undo_roster_add_removes_enrollment_and_keeps_a_graded_person(api, world):
    async with api(world.admin) as client:
        added = await client.post(
            f"/api/admin/classes/{world.cls}/roster",
            json={"school_number": 51003, "full_name": "Synthetic Newcomer", "language": "german"},
        )
        assert added.status_code == 201, added.text
        newcomer = added.json()["student_id"]
        plain = await client.post(
            f"/api/admin/classes/{world.cls}/roster",
            json={"school_number": 51004, "full_name": "Synthetic Ungraded"},
        )
        ungraded = plain.json()["student_id"]
    assert (
        await save_grid(api, world.main, world.cls, [cell(newcomer, world.main_column, 77)])
    ).status_code == 200
    graded = await grade_row(newcomer, world.main_column)
    async with api(world.admin) as client:
        assert (await undo(client, added.json()["action_id"])).status_code == 200
        assert (await undo(client, plain.json()["action_id"])).status_code == 200
    assert await placement(newcomer, world.year) is None
    assert await language(newcomer, world.year) is None
    assert await grade_row(newcomer, world.main_column) == graded
    async with TestSession() as db:
        assert await db.get(m.Student, newcomer) is not None
        assert await db.get(m.Student, ungraded) is None


async def test_undo_student_create_endpoint_removes_the_new_pupil(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/students",
            json={
                "school_number": 51005,
                "full_name": "Synthetic Created",
                "year_id": world.year,
                "class_id": world.cls,
            },
        )
        assert created.status_code == 201, created.text
        restored = await undo(client, created.json()["action_id"])
        assert restored.status_code == 200
        assert restored.json()["status"] == "undone"
    async with TestSession() as db:
        assert await db.get(m.Student, created.json()["id"]) is None


async def test_undo_roster_removal_restores_number_language_and_grades(api, world):
    assert (
        await save_grid(
            api, world.main, world.cls, [cell(world.student_one, world.main_column, 81)]
        )
    ).status_code == 200
    graded = await grade_row(world.student_one, world.main_column)
    async with api(world.admin) as client:
        await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_one}",
            json={"language": "german"},
        )
        removed = await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        assert removed.status_code == 200
        assert removed.json()["removed"] is True
        assert (await undo(client, removed.json()["action_id"])).status_code == 200
    assert await placement(world.student_one, world.year) == (world.cls, 51001)
    assert await language(world.student_one, world.year) == "german"
    assert await grade_row(world.student_one, world.main_column) == graded


async def test_undo_roster_removal_refuses_a_taken_number_or_a_new_enrollment(api, world):
    other = await add_class(world.year, 5, "B")
    async with api(world.admin) as client:
        removed = await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        taker = await client.post(
            f"/api/admin/classes/{other}/roster",
            json={"school_number": 51001, "full_name": "Synthetic Number Taker"},
        )
        assert taker.status_code == 201
        assert_blocked(
            await undo(client, removed.json()["action_id"]),
            "school_number_taken",
            number=51001,
            student="Synthetic Number Taker",
            **{"class": "5/B"},
        )
        await undo(client, taker.json()["action_id"])
    async with TestSession() as db:
        db.add(
            m.Enrollment(
                student_id=world.student_one, year_id=world.year, class_id=other, school_number=9
            )
        )
        await db.commit()
    async with api(world.admin) as client:
        assert_blocked(
            await undo(client, removed.json()["action_id"]),
            "enrollment_exists",
            student="Synthetic Student One",
            **{"class": "5/B"},
        )
    assert await placement(world.student_one, world.year) == (other, 9)


async def test_undo_move_returns_pupils_and_refuses_as_a_whole(api, world):
    five_b = await add_class(world.year, 5, "B")
    five_c = await add_class(world.year, 5, "C")
    async with api(world.admin) as client:
        moved = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [world.student_one, world.student_two],
                "target_class_id": five_b,
            },
        )
        assert moved.status_code == 200
        assert moved.json()["changed"] == 2
        again = await client.post(
            "/api/admin/roster/move",
            json={"student_ids": [world.student_two], "target_class_id": five_c},
        )
        assert_blocked(
            await undo(client, moved.json()["action_id"]),
            "changed_since",
            student="Synthetic Student Two",
            **{"class": "5/C"},
        )
        assert await placement(world.student_one, world.year) == (five_b, 51001)
        assert (await undo(client, again.json()["action_id"])).status_code == 200
        assert (await undo(client, moved.json()["action_id"])).status_code == 200
    assert await placement(world.student_one, world.year) == (world.cls, 51001)
    assert await placement(world.student_two, world.year) == (world.cls, 51002)


async def test_undo_cross_stage_move_refuses_a_number_taken_in_the_old_stage(api, world):
    four_a = await add_class(world.year, 4, "A")
    four_b = await add_class(world.year, 4, "B")
    async with api(world.admin) as client:
        pupil = await client.post(
            f"/api/admin/classes/{four_a}/roster",
            json={"school_number": 7, "full_name": "Synthetic Primary Pupil"},
        )
        moved = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [pupil.json()["student_id"]],
                "target_class_id": world.cls,
                "allow_grade_change": True,
            },
        )
        assert moved.status_code == 200
        await client.post(
            f"/api/admin/classes/{four_b}/roster",
            json={"school_number": 7, "full_name": "Synthetic Number Seven"},
        )
        assert_blocked(
            await undo(client, moved.json()["action_id"]),
            "school_number_taken",
            number=7,
            student="Synthetic Number Seven",
            **{"class": "4/B"},
        )


async def test_undo_roster_edit_restores_name_number_and_language(api, world):
    url = f"/api/admin/classes/{world.cls}/roster/{world.student_one}"
    async with api(world.admin) as client:
        edited = await client.patch(
            url,
            json={"full_name": "Synthetic Renamed", "school_number": 51009, "language": "french"},
        )
        assert edited.status_code == 200
        actions = (await client.get("/api/admin/actions")).json()["items"]
        assert actions[0]["kind"] == "student.edit"
        assert {item["field"] for item in actions[0]["params"]["changes"]} == {
            "full_name",
            "school_number",
            "language",
        }
        assert (await undo(client, edited.json()["action_id"])).status_code == 200
        roster = (await client.get(f"/api/admin/classes/{world.cls}/roster")).json()
    restored = next(item for item in roster if item["student_id"] == world.student_one)
    assert restored == {
        "student_id": world.student_one,
        "school_number": 51001,
        "full_name": "Synthetic Student One",
        "language": None,
    }
    async with TestSession() as db:
        student = await db.get(m.Student, world.student_one)
        assert student.search_name == "synthetic student one"


async def test_undo_student_edit_refuses_taken_number_and_later_edits(api, world):
    async with api(world.admin) as client:
        renumbered = await client.patch(
            f"/api/admin/students/{world.student_one}",
            params={"year_id": world.year},
            json={"school_number": 51009},
        )
        assert renumbered.status_code == 200
        await client.patch(
            f"/api/admin/students/{world.student_two}",
            params={"year_id": world.year},
            json={"school_number": 51001},
        )
        assert_blocked(
            await undo(client, renumbered.json()["action_id"]),
            "school_number_taken",
            number=51001,
            student="Synthetic Student Two",
            **{"class": "5/A"},
        )
        renamed = await client.patch(
            f"/api/admin/students/{world.student_one}",
            params={"year_id": world.year},
            json={"full_name": "Synthetic First Rename"},
        )
        second = await client.patch(
            f"/api/admin/students/{world.student_one}",
            params={"year_id": world.year},
            json={"full_name": "Synthetic Second Rename"},
        )
        assert_blocked(await undo(client, renamed.json()["action_id"]), "changed_since")
        assert (await undo(client, second.json()["action_id"])).status_code == 200
        assert (await undo(client, renamed.json()["action_id"])).status_code == 200
    assert await placement(world.student_one, world.year) == (world.cls, 51009)
    async with TestSession() as db:
        assert (await db.get(m.Student, world.student_one)).full_name == "Synthetic Student One"


async def test_undo_bulk_language_restores_each_previous_choice(api, world):
    async with api(world.admin) as client:
        await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_one}",
            json={"language": "french"},
        )
        changed = await client.put(
            f"/api/admin/years/{world.year}/student-language",
            json={"student_ids": [world.student_one, world.student_two], "language": "german"},
        )
        assert changed.status_code == 200
        assert changed.json()["changed"] == 2
        assert (await undo(client, changed.json()["action_id"])).status_code == 200
    assert await language(world.student_one, world.year) == "french"
    assert await language(world.student_two, world.year) is None


async def test_undo_language_edit_refuses_a_grade_without_second_languages(api, world):
    async with api(world.admin) as client:
        await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_one}",
            json={"language": "german"},
        )
        switched = await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_one}",
            json={"language": None},
        )
        regraded = await client.patch(f"/api/admin/classes/{world.cls}", json={"grade_level": 3})
        assert regraded.status_code == 200
        assert_blocked(
            await undo(client, switched.json()["action_id"]),
            "language_grade_too_low",
            student="Synthetic Student One",
            **{"class": "3/A"},
        )
    assert await language(world.student_one, world.year) is None


# Classes --------------------------------------------------------------------


async def test_undo_class_create_and_refusal_when_used(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "a"}
        )
        assert created.status_code == 201
        used = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "B"}
        )
        await client.post(
            f"/api/admin/classes/{used.json()['id']}/roster",
            json={"school_number": 61001, "full_name": "Synthetic Sixth Grader"},
        )
        assert (await undo(client, created.json()["action_id"])).status_code == 200
        assert_blocked(
            await undo(client, used.json()["action_id"]), "class_in_use", **{"class": "6/B"}
        )
    async with TestSession() as db:
        assert await db.get(m.SchoolClass, created.json()["id"]) is None
        assert await db.get(m.SchoolClass, used.json()["id"]) is not None


async def test_undo_class_edit_restores_grade_and_section(api, world):
    async with api(world.admin) as client:
        edited = await client.patch(f"/api/admin/classes/{world.cls}", json={"section": "D"})
        assert edited.json()["name"] == "5/D"
        replacement = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 5, "section": "A"}
        )
        assert_blocked(
            await undo(client, edited.json()["action_id"]), "duplicate_class", **{"class": "5/A"}
        )
        await undo(client, replacement.json()["action_id"])
        assert (await undo(client, edited.json()["action_id"])).status_code == 200
    async with TestSession() as db:
        school_class = await db.get(m.SchoolClass, world.cls)
        assert (school_class.grade_level, school_class.section) == (5, "A")


async def test_undo_refuses_when_the_changed_class_is_gone(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "B"}
        )
        edited = await client.patch(
            f"/api/admin/classes/{created.json()['id']}", json={"section": "C"}
        )
        assert (await undo(client, created.json()["action_id"])).status_code == 200
        assert_blocked(
            await undo(client, edited.json()["action_id"]), "target_missing", **{"class": "6/C"}
        )


async def test_undo_class_delete_recreates_the_same_class(api, world):
    async with TestSession() as db:
        setup = m.AcademicYear(label="Synthetic setup year", status="setup")
        db.add(setup)
        await db.commit()
        setup_id = setup.id
    empty = await add_class(setup_id, 3, "A")
    async with api(world.admin) as client:
        deleted = await client.delete(f"/api/admin/classes/{empty}")
        assert deleted.json()["deleted"] is True
        assert (await undo(client, deleted.json()["action_id"])).status_code == 200
        # Restored under its old id, so it can be deleted again by that id.
        again = await client.delete(f"/api/admin/classes/{empty}")
        assert again.status_code == 200
        await client.post(
            "/api/admin/classes", json={"year_id": setup_id, "grade_level": 3, "section": "A"}
        )
        assert_blocked(
            await undo(client, again.json()["action_id"]), "duplicate_class", **{"class": "3/A"}
        )
    async with TestSession() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(m.SchoolClass)
                .where(m.SchoolClass.year_id == setup_id)
            )
            == 1
        )


# Fields ---------------------------------------------------------------------


def _field(name: str, owner: str = "main") -> dict[str, object]:
    return {
        "grade_level": 5,
        "subject": "english",
        "value_type": "score",
        "owner_role": owner,
        "name": name,
    }


async def test_undo_field_create_and_refusal_once_graded(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/columns", params={"semester_id": world.semester}, json=_field("Synthetic Quiz")
        )
        assert created.status_code == 201
        graded = await client.post(
            "/api/columns", params={"semester_id": world.semester}, json=_field("Synthetic Exam")
        )
    assert (
        await save_grid(
            api, world.main, world.cls, [cell(world.student_one, graded.json()["id"], 60)]
        )
    ).status_code == 200
    async with api(world.admin) as client:
        assert (await undo(client, created.json()["action_id"])).status_code == 200
        assert_blocked(
            await undo(client, graded.json()["action_id"]),
            "field_has_grades",
            field="Synthetic Exam",
        )
    assert await column_row(created.json()["id"]) is None
    assert await column_row(graded.json()["id"]) is not None


async def test_undo_field_delete_restores_empty_field_and_reenables_graded_one(api, world):
    assert (
        await save_grid(
            api, world.main, world.cls, [cell(world.student_one, world.main_column, 88)]
        )
    ).status_code == 200
    graded = await grade_row(world.student_one, world.main_column)
    original = await column_row(world.skills_column)
    async with api(world.admin) as client:
        hidden = await client.delete(
            f"/api/columns/{world.main_column}", params={"semester_id": world.semester}
        )
        assert hidden.json()["disabled"] is True
        removed = await client.delete(
            f"/api/columns/{world.skills_column}", params={"semester_id": world.semester}
        )
        assert removed.json()["deleted"] is True
        # A field added meanwhile takes the free position; the restored one returns before it.
        added = await client.post(
            "/api/columns", params={"semester_id": world.semester}, json=_field("Synthetic Later")
        )
        assert added.json()["position"] == 2
        assert (await undo(client, removed.json()["action_id"])).status_code == 200
        assert (await undo(client, hidden.json()["action_id"])).status_code == 200
        listed = (
            await client.get(
                "/api/columns",
                params={"semester_id": world.semester, "grade_level": 5, "subject": "english"},
            )
        ).json()
    assert [item["id"] for item in listed] == [
        world.main_column,
        world.skills_column,
        added.json()["id"],
    ]
    restored = await column_row(world.skills_column)
    assert restored is not None and original is not None
    assert (restored.labels, restored.owner_role, restored.position, restored.is_active) == (
        original.labels,
        original.owner_role,
        original.position,
        True,
    )
    assert (await column_row(world.main_column)).is_active is True
    assert await grade_row(world.student_one, world.main_column) == graded


async def test_undo_field_edit_restores_name_and_attributes(api, world):
    async with api(world.admin) as client:
        edited = await client.patch(
            f"/api/columns/{world.main_column}",
            params={"semester_id": world.semester},
            json={"name": "  Synthetic Renamed  ", "counts_in_average": True},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["name"] == "Synthetic Renamed"
        # Edits of other attributes do not block; a later edit of the same one does.
        await client.patch(
            f"/api/columns/{world.main_column}",
            params={"semester_id": world.semester},
            json={"owner_role": "skills"},
        )
        later = await client.patch(
            f"/api/columns/{world.main_column}",
            params={"semester_id": world.semester},
            json={"counts_in_average": False},
        )
        assert_blocked(
            await undo(client, edited.json()["action_id"]),
            "changed_since",
            field="Synthetic Renamed",
        )
        assert (await undo(client, later.json()["action_id"])).status_code == 200
        assert (await undo(client, edited.json()["action_id"])).status_code == 200
    column = await column_row(world.main_column)
    assert column.labels == {"tr": "Main score", "en": "Main score", "de": "", "fr": ""}
    assert (column.counts_in_average, column.owner_role) == (False, "skills")


async def test_undo_reorder_and_refusal_after_a_later_reorder(api, world):
    async with api(world.admin) as client:
        swapped = await client.post(
            "/api/columns/reorder",
            params={"semester_id": world.semester},
            json={"ordered_ids": [world.skills_column, world.main_column]},
        )
        assert swapped.json()["ok"] is True
        back = await client.post(
            "/api/columns/reorder",
            params={"semester_id": world.semester},
            json={"ordered_ids": [world.main_column, world.skills_column]},
        )
        assert_blocked(
            await undo(client, swapped.json()["action_id"]),
            "order_changed",
            grade_level=5,
            subject="english",
        )
        assert (await undo(client, back.json()["action_id"])).status_code == 200
        assert (await undo(client, swapped.json()["action_id"])).status_code == 200
    assert (await column_row(world.main_column)).position == 1
    assert (await column_row(world.skills_column)).position == 2


async def test_undo_copy_removes_copies_unless_graded(api, world):
    copy = {
        "source_grade_level": 5,
        "source_subject": "english",
        "target_grade_level": 6,
        "target_subject": "english",
    }
    async with api(world.admin) as client:
        copied = await client.post(
            "/api/columns/copy", params={"semester_id": world.semester}, json=copy
        )
        assert copied.json()["copied"] == 2
        assert (await undo(client, copied.json()["action_id"])).status_code == 200
        emptied = await client.get(
            "/api/columns",
            params={"semester_id": world.semester, "grade_level": 6, "subject": "english"},
        )
        assert emptied.json() == []
        again = await client.post(
            "/api/columns/copy", params={"semester_id": world.semester}, json=copy
        )
    async with TestSession() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(m.ColumnDefinition)
                .where(m.ColumnDefinition.grade_level == 6)
            )
            == 2
        )
        copied_id = await db.scalar(
            select(m.ColumnDefinition.id).where(m.ColumnDefinition.grade_level == 6).limit(1)
        )
        db.add(
            m.GradeValue(
                student_id=world.student_one,
                column_definition_id=copied_id,
                score=50,
                updated_by=world.main.id,
            )
        )
        await db.commit()
    async with api(world.admin) as client:
        assert_blocked(await undo(client, again.json()["action_id"]), "field_has_grades")


# Field renaming (ADR-076) ------------------------------------------------------


async def test_rename_stores_the_subject_language_name_only(api, world):
    async with TestSession() as db:
        german = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="german",
            value_type="scale3",
            owner_role="german",
            labels={"tr": "Okuma", "de": "Lesen"},
            group_labels={"tr": "Beceriler", "de": "Fertigkeiten"},
            position=1,
        )
        db.add(german)
        await db.commit()
        german_id = german.id
    async with api(world.admin) as client:
        renamed = await client.patch(
            f"/api/columns/{german_id}",
            params={"semester_id": world.semester},
            json={"name": "Leseverstehen"},
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Leseverstehen"
        assert isinstance(renamed.json()["action_id"], int)
        english = await client.patch(
            f"/api/columns/{world.main_column}",
            params={"semester_id": world.semester},
            json={"name": "Synthetic Speaking"},
        )
        assert english.json()["labels"]["en"] == "Synthetic Speaking"
        blank = await client.patch(
            f"/api/columns/{german_id}",
            params={"semester_id": world.semester},
            json={"name": "   "},
        )
        assert blank.status_code == 422
    column = await column_row(german_id)
    assert column.labels == {"tr": "Okuma", "de": "Leseverstehen"}
    assert column.group_labels == {"tr": "Beceriler", "de": "Fertigkeiten"}
    assert (await column_row(world.main_column)).labels == {
        "tr": "Main score",
        "en": "Synthetic Speaking",
        "de": "",
        "fr": "",
    }


@pytest.mark.parametrize("state", ["locked", "archived"])
async def test_rename_refuses_locked_and_archived_terms(api, world, state):
    async with TestSession() as db:
        if state == "locked":
            semester = await db.get(m.Semester, world.semester)
            semester.status = "locked"
        else:
            year = await db.get(m.AcademicYear, world.year)
            year.status = "archived"
        await db.commit()
    async with api(world.admin) as client:
        response = await client.patch(
            f"/api/columns/{world.main_column}",
            params={"semester_id": world.semester},
            json={"name": "Synthetic Late Rename"},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "semester_locked"
    assert (await column_row(world.main_column)).labels["en"] == "Main score"


# Accounts -------------------------------------------------------------------


def _teacher(email: str, **extra) -> dict[str, object]:
    return {
        "email": f"{email}@{SCHOOL_DOMAIN}",
        "full_name": f"Synthetic {email.title()}",
        "teaching_field": "english",
        "teaching_stage": "middle",
        **extra,
    }


async def test_undo_user_create_and_refusal_once_assigned(api, world):
    async with api(world.admin) as client:
        created = await client.post("/api/admin/users", json=_teacher("fresh"))
        assert created.status_code == 201, created.text
        assigned = await client.post("/api/admin/users", json=_teacher("busy"))
        await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={
                "changes": [
                    {"class_id": world.cls, "role": "main", "user_id": assigned.json()["id"]}
                ]
            },
        )
        assert (await undo(client, created.json()["action_id"])).status_code == 200
        assert_blocked(
            await undo(client, assigned.json()["action_id"]),
            "user_in_use",
            user="Synthetic Busy",
        )
    async with TestSession() as db:
        assert await db.get(m.User, created.json()["id"]) is None


async def test_undo_user_edit_restores_account_and_audits_report_name(api, world):
    async with api(world.admin) as client:
        edited = await client.patch(
            f"/api/admin/users/{world.skills.id}",
            json={
                "full_name": "Synthetic Renamed Teacher",
                "is_coordinator": True,
                "report_name": "Synthetic Printed Name",
            },
        )
        assert edited.status_code == 200
        assert (await undo(client, edited.json()["action_id"])).status_code == 200
    async with TestSession() as db:
        user = await db.get(m.User, world.skills.id)
        assert (user.full_name, user.is_coordinator, user.report_name) == (
            "Skills Teacher",
            False,
            None,
        )
        audits = list(
            await db.scalars(
                select(m.ReportIdentityAudit.after)
                .where(m.ReportIdentityAudit.user_id == world.skills.id)
                .order_by(m.ReportIdentityAudit.id)
            )
        )
        assert [item["report_name"] for item in audits] == ["Synthetic Printed Name", None]


async def test_undo_user_edit_refuses_removing_the_last_admin(api, world):
    async with api(world.admin) as client:
        promoted = await client.patch(
            f"/api/admin/users/{world.skills.id}", json={"is_admin": True}
        )
    async with TestSession() as db:
        skills = await db.get(m.User, world.skills.id)
    async with api(skills) as client:
        assert (
            await client.patch(f"/api/admin/users/{world.admin.id}", json={"is_admin": False})
        ).status_code == 200
        assert_blocked(await undo(client, promoted.json()["action_id"]), "last_admin")
    async with TestSession() as db:
        assert (await db.get(m.User, world.skills.id)).is_admin is True


async def test_undo_user_edit_refuses_deactivating_yourself(api, world):
    async with TestSession() as db:
        deputy = m.User(
            email=f"deputy@{SCHOOL_DOMAIN}",
            full_name="Synthetic Deputy",
            is_admin=True,
            is_active=False,
            teaching_stage="middle",
        )
        db.add(deputy)
        await db.commit()
    async with api(world.admin) as client:
        activated = await client.patch(f"/api/admin/users/{deputy.id}", json={"is_active": True})
    async with api(deputy) as client:
        assert_blocked(await undo(client, activated.json()["action_id"]), "cannot_deactivate_self")


async def test_undo_teaching_change_refuses_incompatible_assignments(api, world):
    primary = await add_class(world.year, 3, "A")
    async with api(world.admin) as client:
        await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": None}]},
        )
        moved_stage = await client.patch(
            f"/api/admin/users/{world.main.id}", json={"teaching_stage": "primary"}
        )
        assert moved_stage.status_code == 200
        await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": primary, "role": "main", "user_id": world.main.id}]},
        )
        assert_blocked(
            await undo(client, moved_stage.json()["action_id"]),
            "teacher_assignments_incompatible",
        )


async def test_undo_signature_upload_and_delete_keep_the_images(api, world):
    path = f"/api/admin/users/{world.skills.id}/signature"
    async with api(world.admin) as client:
        first = await client.put(path, files={"file": ("s.png", png("black"), "image/png")})
        first_image = (await client.get(path)).content
        second = await client.put(path, files={"file": ("s.png", png("blue"), "image/png")})
        assert second.json()["signature_url"] != first.json()["signature_url"]
        assert_blocked(await undo(client, first.json()["action_id"]), "changed_since")
        assert (await undo(client, second.json()["action_id"])).status_code == 200
        assert (await client.get(path)).content == first_image
        removed = await client.delete(path)
        assert (await client.get(path)).status_code == 404
        assert (await undo(client, removed.json()["action_id"])).status_code == 200
        assert (await client.get(path)).content == first_image
        assert (await undo(client, first.json()["action_id"])).status_code == 200
        assert (await client.get(path)).status_code == 404


async def crossed(*requests: Callable[[], Awaitable[Any]]) -> list[Any]:
    """Run requests at once, each held at its first admin-action write until all arrive.

    A share lock on ``admin_actions`` lets every request take the row locks it takes before
    recording, then releases them together, the worst interleaving of simultaneous requests.
    """
    async with TestSession() as db:
        await db.execute(text("LOCK TABLE admin_actions IN SHARE MODE"))
        pending = [asyncio.create_task(request()) for request in requests]
        await asyncio.sleep(0.5)
        await db.commit()
    return await asyncio.gather(*pending)


@pytest.mark.parametrize("write", ["edit", "signature", "undo"])
async def test_two_admins_changing_each_others_accounts_do_not_deadlock(api, world, write):
    async with TestSession() as db:
        deputy = m.User(
            email=f"deputy@{SCHOOL_DOMAIN}",
            full_name="Synthetic Deputy",
            is_admin=True,
            teaching_stage="middle",
        )
        db.add(deputy)
        await db.commit()
    pairs = [(world.admin, deputy), (deputy, world.admin)]
    renames: list[int] = []
    if write == "undo":
        for index, (actor, target) in enumerate(pairs):
            async with api(actor) as client:
                renamed = await client.patch(
                    f"/api/admin/users/{target.id}",
                    json={"full_name": f"Synthetic Renamed {index}"},
                )
            renames.append(renamed.json()["action_id"])

    def change(index: int) -> Callable[[], Awaitable[Any]]:
        actor, target = pairs[index]

        async def request():
            async with api(actor) as client:
                if write == "edit":
                    return await client.patch(
                        f"/api/admin/users/{target.id}",
                        json={"full_name": f"Synthetic Renamed {index}"},
                    )
                if write == "signature":
                    return await client.put(
                        f"/api/admin/users/{target.id}/signature",
                        files={"file": ("s.png", png("black"), "image/png")},
                    )
                return await undo(client, renames[index])

        return request

    responses = await crossed(change(0), change(1))
    assert [response.status_code for response in responses] == [200, 200]
    async with TestSession() as db:
        targets = [await db.get(m.User, target.id) for _, target in pairs]
    if write == "signature":
        assert all(target.signature_digest for target in targets)
    else:
        expected = {
            "edit": ["Synthetic Renamed 0", "Synthetic Renamed 1"],
            "undo": ["Synthetic Deputy", "Synthetic Admin"],
        }[write]
        assert [target.full_name for target in targets] == expected


# Assignments ----------------------------------------------------------------


async def test_undo_assignment_matrix_and_single_slot(api, world):
    async with TestSession() as db:
        substitute = m.User(
            email=f"substitute@{SCHOOL_DOMAIN}",
            full_name="Synthetic Substitute",
            teaching_stage="middle",
        )
        db.add(substitute)
        await db.commit()
    async with api(world.admin) as client:
        replaced = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": substitute.id}]},
        )
        assert replaced.status_code == 200
        slots = {
            (item["class_id"], item["role"]): item["user_id"] for item in replaced.json()["slots"]
        }
        assert slots[(world.cls, "main")] == substitute.id
        assert (await undo(client, replaced.json()["action_id"])).status_code == 200
        single = await client.put(
            f"/api/classes/{world.cls}/assignments/skills", json={"user_id": substitute.id}
        )
        assert single.json()["ok"] is True
        assert (await undo(client, single.json()["action_id"])).status_code == 200
        matrix = (await client.get(f"/api/admin/years/{world.year}/assignments")).json()
    assert {(item["role"], item["user_id"]) for item in matrix} == {
        ("main", world.main.id),
        ("skills", world.skills.id),
    }


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"is_active": False}, "teacher_inactive"),
        ({"teaching_field": "german"}, "teacher_field_mismatch"),
        ({"teaching_stage": "primary"}, "teacher_stage_mismatch"),
    ],
)
async def test_undo_assignment_refuses_a_teacher_who_no_longer_fits(api, world, change, reason):
    async with TestSession() as db:
        substitute = m.User(
            email=f"substitute@{SCHOOL_DOMAIN}",
            full_name="Synthetic Substitute",
            teaching_stage="middle",
        )
        db.add(substitute)
        await db.commit()
    async with api(world.admin) as client:
        replaced = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": substitute.id}]},
        )
        assert (
            await client.patch(f"/api/admin/users/{world.main.id}", json=change)
        ).status_code == 200
        assert_blocked(
            await undo(client, replaced.json()["action_id"]),
            reason,
            teacher="Main Teacher",
            role="main",
            **{"class": "5/A"},
        )


# Actions list, states and permissions ------------------------------------------


async def test_actions_list_newest_first_with_cursor_and_states(api, world):
    async with api(world.admin) as client:
        ids = []
        for section in ("B", "C", "D"):
            created = await client.post(
                "/api/admin/classes",
                json={"year_id": world.year, "grade_level": 6, "section": section},
            )
            ids.append(created.json()["action_id"])
        await undo(client, ids[0])
        first = (await client.get("/api/admin/actions", params={"limit": 2})).json()
        second = (
            await client.get(
                "/api/admin/actions", params={"limit": 2, "cursor": first["next_cursor"]}
            )
        ).json()
    assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None
    newest = first["items"][0]
    assert newest["kind"] == "class.create"
    assert newest["actor"] == "Synthetic Admin"
    assert newest["status"] == "available"
    assert newest["params"] == {"class": "6/D"}
    assert second["items"][0]["status"] == "undone"
    assert second["items"][0]["undone_by"] == "Synthetic Admin"
    created_at = newest["created_at"]
    assert newest["expires_at"] > created_at


async def test_undo_refuses_unknown_undone_and_expired_actions(api, world):
    async with api(world.admin) as client:
        assert (await undo(client, 999999)).status_code == 404
        created = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "B"}
        )
        action_id = created.json()["action_id"]
        assert (await undo(client, action_id)).status_code == 200
        twice = await undo(client, action_id)
        assert twice.status_code == 409
        assert twice.json()["detail"]["code"] == "action_already_undone"
        old = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "C"}
        )
    async with TestSession() as db:
        await db.execute(
            update(m.AdminAction)
            .where(m.AdminAction.id == old.json()["action_id"])
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()
    async with api(world.admin) as client:
        expired = await undo(client, old.json()["action_id"])
        assert expired.status_code == 410
        assert expired.json()["detail"]["code"] == "action_expired"
        listed = (await client.get("/api/admin/actions")).json()["items"]
    assert listed[0]["status"] == "expired"
    async with TestSession() as db:
        assert await db.get(m.SchoolClass, old.json()["id"]) is not None


async def test_undo_reports_year_rules_with_their_own_reason(api, world):
    async with api(world.admin) as client:
        removed = await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
    async with TestSession() as db:
        year = await db.get(m.AcademicYear, world.year)
        year.status = "archived"
        await db.commit()
    async with api(world.admin) as client:
        assert_blocked(await undo(client, removed.json()["action_id"]), "year_not_writable")
    assert await placement(world.student_one, world.year) is None


@pytest.mark.parametrize("role", ["teacher", "coordinator"])
async def test_only_admins_list_or_undo_actions(api, world, role):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "B"}
        )
    async with TestSession() as db:
        user = m.User(
            email=f"{role}@{SCHOOL_DOMAIN}",
            full_name=f"Synthetic {role}",
            is_coordinator=role == "coordinator",
            teaching_stage="middle",
        )
        db.add(user)
        await db.commit()
    async with api(user) as client:
        assert (await client.get("/api/admin/actions")).status_code == 403
        assert (await undo(client, created.json()["action_id"])).status_code == 403
    async with TestSession() as db:
        assert await db.get(m.SchoolClass, created.json()["id"]) is not None


async def test_purge_deletes_only_expired_actions_and_their_images(api, world):
    path = f"/api/admin/users/{world.skills.id}/signature"
    async with api(world.admin) as client:
        kept = await client.put(path, files={"file": ("s.png", png("black"), "image/png")})
        expired = await client.delete(path)
    with Session(create_engine(TEST_URL_SYNC)) as db:
        db.execute(
            update(m.AdminAction)
            .where(m.AdminAction.id == expired.json()["action_id"])
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )
        db.commit()
        assert purge_expired_actions(db) == 1
        db.commit()
        remaining = list(db.scalars(select(m.AdminAction.id)))
    assert remaining == [kept.json()["action_id"]]


async def test_actions_expire_seven_days_after_the_write(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/classes", json={"year_id": world.year, "grade_level": 6, "section": "B"}
        )
    async with TestSession() as db:
        action = await db.get(m.AdminAction, created.json()["action_id"])
        assert action.expires_at - action.created_at == ADMIN_ACTION_TTL
        assert action.actor_id == world.admin.id
