import asyncio

from sqlalchemy import delete, select, text, update

from flrc.db import models as m
from tests.conftest import TestSession, cell, save_grid


async def test_twenty_concurrent_grid_readers_receive_complete_tables(api, world):
    async with api(world.main) as client:
        responses = await asyncio.gather(
            *(
                client.get(
                    f"/api/classes/{world.cls}/grid",
                    params={"subject": "english", "locale": "en"},
                )
                for _ in range(20)
            )
        )

    assert all(response.status_code == 200 for response in responses)
    assert all(len(response.json()["rows"]) == 2 for response in responses)
    assert all(len(response.json()["columns"]) == 2 for response in responses)


async def test_grid_read_returns_columns_roster_and_missing_version_zero(api, world):
    response = None
    async with api(world.main) as client:
        response = await client.get(
            f"/api/classes/{world.cls}/grid",
            params={"subject": "english", "locale": "en"},
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 2
    assert body["rows"][0]["cells"] == {}
    assert body["columns"][0]["owned_by_you"] is True
    assert body["columns"][1]["owned_by_you"] is False


async def test_class_catalog_hides_unassigned_classes_from_teachers(api, world):
    async with TestSession() as db:
        other = m.SchoolClass(year_id=world.year, grade_level=5, section="B")
        db.add(other)
        await db.commit()

    async with api(world.main) as client:
        response = await client.get("/api/class-catalog")

    assert response.status_code == 200
    catalog = response.json()
    assert [item["name"] for item in catalog] == ["5/A"]


async def test_admin_is_warned_as_unassigned_but_save_authority_is_preserved(api, world):
    async with api(world.admin) as client:
        grid = await client.get(
            f"/api/classes/{world.cls}/grid",
            params={"subject": "english", "locale": "en"},
        )
    assert grid.status_code == 200
    assert grid.json()["columns"][0]["owned_by_you"] is False

    saved = await save_grid(
        api,
        world.admin,
        world.cls,
        [cell(world.student_one, world.main_column, 88)],
    )
    assert saved.json()["applied"][0]["version"] == 1


async def test_clean_save_inserts_and_audits(api, world):
    response = await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] == [
        {"student_id": world.student_one, "column_id": world.main_column, "version": 1}
    ]
    assert body["conflicts"] == []
    assert body["rejected"] == []
    async with TestSession() as db:
        entries = list((await db.execute(select(m.AuditEntry))).scalars())
    assert len(entries) == 1
    assert entries[0].old_existed is False


async def test_stale_version_conflicts_with_author_named(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    response = await save_grid(
        api,
        world.admin,
        world.cls,
        [cell(world.student_one, world.main_column, 90)],
    )
    conflict = response.json()["conflicts"][0]
    assert conflict["current_value"] == 85
    assert conflict["updated_by"] == "Main Teacher"


async def test_force_overwrites_and_marks_audit(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    response = await save_grid(
        api,
        world.admin,
        world.cls,
        [cell(world.student_one, world.main_column, 90)],
        force=True,
    )
    assert response.json()["applied"][0]["version"] == 2
    async with TestSession() as db:
        forced = list((await db.execute(select(m.AuditEntry).where(m.AuditEntry.forced))).scalars())
    assert len(forced) == 1


async def test_invalid_and_foreign_owner_values_are_rejected(api, world):
    foreign = await save_grid(
        api,
        world.skills,
        world.cls,
        [cell(world.student_one, world.main_column, 70)],
    )
    assert foreign.json()["rejected"][0]["code"] == "outside_assignment_confirmation_required"
    async with api(world.skills) as client:
        confirmed = await client.post(
            f"/api/classes/{world.cls}/grid/save",
            json={
                "subject": "english",
                "confirm_outside_assignment": True,
                "cells": [cell(world.student_one, world.main_column, 70)],
            },
        )
    assert confirmed.json()["applied"][0]["version"] == 1
    async with TestSession() as db:
        entry = (await db.execute(select(m.AuditEntry))).scalars().one()
        assert entry.via_grant_id is not None
    invalid = await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_two, world.main_column, "bad")],
    )
    assert invalid.json()["rejected"][0]["code"] == "invalid_value"


async def test_confirmed_save_allows_a_note_with_no_assigned_owner(api, world):
    async with TestSession() as db:
        await db.execute(
            delete(m.TeachingAssignment).where(
                m.TeachingAssignment.class_id == world.cls,
                m.TeachingAssignment.role == "main",
            )
        )
        await db.commit()

    async with api(world.skills) as client:
        grid = await client.get(
            f"/api/classes/{world.cls}/grid",
            params={"subject": "english", "locale": "en"},
        )
        saved = await client.post(
            f"/api/classes/{world.cls}/grid/save",
            json={
                "subject": "english",
                "confirm_outside_assignment": True,
                "cells": [cell(world.student_one, world.main_column, 75)],
            },
        )

    assert grid.json()["columns"][0]["owner_name"] is None
    assert grid.json()["columns"][0]["owned_by_you"] is False
    assert saved.json()["applied"][0]["version"] == 1


async def test_locked_semester_blocks_save(api, world):
    async with TestSession() as db:
        await db.execute(update(m.Semester).values(status="locked"))
        await db.commit()
    response = await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "semester_locked"


async def test_grant_allows_foreign_write_and_expiry_revokes_it(api, world):
    async with api(world.skills) as client:
        grant = await client.post(f"/api/classes/{world.cls}/grants", json={"role": "main"})
        grid = await client.get(
            f"/api/classes/{world.cls}/grid",
            params={"subject": "english", "locale": "en"},
        )
    assert grant.status_code == 200
    assert grid.json()["columns"][0]["owned_by_you"] is False
    saved = await save_grid(
        api,
        world.skills,
        world.cls,
        [cell(world.student_one, world.main_column, 70)],
    )
    assert saved.json()["applied"][0]["version"] == 1
    async with TestSession() as db:
        entry = (await db.execute(select(m.AuditEntry))).scalars().one()
        assert entry.via_grant_id is not None
        await db.execute(
            update(m.OverrideGrant).values(expires_at=text("now() - interval '1 minute'"))
        )
        await db.commit()
    rejected = await save_grid(
        api,
        world.skills,
        world.cls,
        [cell(world.student_two, world.main_column, 60)],
    )
    assert rejected.json()["rejected"][0]["code"] == "outside_assignment_confirmation_required"


async def _undo(api, user, class_id):
    async with api(user) as client:
        return await client.post(f"/api/classes/{class_id}/grid/undo")


async def test_undo_restores_previous_value(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 90, expected=1)],
    )
    response = await _undo(api, world.main, world.cls)
    assert response.json()["applied"][0]["version"] == 3
    async with TestSession() as db:
        grade = (await db.execute(select(m.GradeValue))).scalars().one()
    assert grade.score == 85


async def test_undo_of_fresh_insert_deletes_row(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    response = await _undo(api, world.main, world.cls)
    assert response.json()["applied"][0]["version"] == 0
    async with TestSession() as db:
        assert list((await db.execute(select(m.GradeValue))).scalars()) == []


async def test_undo_does_not_clobber_later_writer(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    await save_grid(
        api,
        world.admin,
        world.cls,
        [cell(world.student_one, world.main_column, 90)],
        force=True,
    )
    response = await _undo(api, world.main, world.cls)
    assert response.json()["applied"] == []
    assert response.json()["conflicts"][0]["current_value"] == 90


async def test_audit_requires_admin_and_exports_csv(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 85)],
    )
    async with api(world.main) as client:
        denied = await client.get("/api/audit")
    assert denied.status_code == 403
    async with api(world.admin) as client:
        page = await client.get("/api/audit")
        exported = await client.get("/api/audit/export.csv")
    assert page.status_code == 200
    assert page.json()["items"][0]["new_value"] == "85"
    assert exported.status_code == 200
    assert "Main Teacher" in exported.text
