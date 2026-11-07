"""Permanently deleting a deactivated teacher account (ADR-080)."""

import asyncio
import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import func, select, update

from flrc.config import settings
from flrc.db import models as m
from flrc.modules.administration.lifecycle import _create_rollover_year
from flrc.modules.administration.users import ERASED_USER_NAME
from flrc.modules.auth import demo, sessions
from flrc.modules.changes.service import utcnow
from tests.conftest import TestSession, cell, save_grid
from tests.test_admin_changes import while_held

SCHOOL_DOMAIN = "school.example"


@pytest.fixture(autouse=True)
def _school_domain(monkeypatch):
    monkeypatch.setattr(settings, "allowed_google_domain", SCHOOL_DOMAIN)


def png(color: str) -> bytes:
    data = BytesIO()
    Image.new("RGBA", (60, 20), color).save(data, format="PNG")
    return data.getvalue()


def detail_code(response) -> str:
    return response.json()["detail"]["code"]


async def deactivate(client, user_id: int):
    response = await client.patch(f"/api/admin/users/{user_id}", json={"is_active": False})
    assert response.status_code == 200, response.text
    return response


async def erase(client, user_id: int):
    return await client.delete(f"/api/admin/users/{user_id}")


async def undo(client, action_id: int):
    return await client.post(f"/api/admin/actions/{action_id}/undo")


def assert_target_missing(response) -> None:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert (detail["code"], detail["reason"]) == ("undo_blocked", "target_missing")


async def create_teacher(client, name: str) -> dict[str, object]:
    response = await client.post(
        "/api/admin/users",
        json={
            "email": f"{name}@{SCHOOL_DOMAIN}",
            "full_name": f"Synthetic {name.title()}",
            "teaching_field": "english",
            "teaching_stage": "middle",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_delete_refuses_non_admins_active_accounts_self_visitors_and_unknown_ids(
    api, world, monkeypatch
):
    async with api(world.main) as client:
        assert (await erase(client, world.skills.id)).status_code == 403
    async with api(world.admin) as client:
        active = await erase(client, world.skills.id)
        assert active.status_code == 409
        assert detail_code(active) == "user_active"
        own = await erase(client, world.admin.id)
        assert own.status_code == 409
        assert detail_code(own) == "cannot_delete_self"
        assert (await erase(client, 999999)).status_code == 404
        await deactivate(client, world.skills.id)
        with monkeypatch.context() as patch:
            patch.setattr(demo, "is_visitor", AsyncMock(return_value=True))
            visitor = await erase(client, world.skills.id)
        assert visitor.status_code == 403
        assert detail_code(visitor) == "visitor_protected"
    async with TestSession() as db:
        skills = await db.get(m.User, world.skills.id)
        assert skills.deleted_at is None
        assert skills.full_name == "Skills Teacher"
    async with api(world.admin) as client:
        assert (await erase(client, world.skills.id)).status_code == 200
        again = await erase(client, world.skills.id)
        assert again.status_code == 404
        assert detail_code(again) == "unknown_user"


async def test_delete_erases_personal_data_and_keeps_grade_history(api, world):
    signature = f"/api/admin/users/{world.skills.id}/signature"
    async with api(world.admin) as client:
        named = await client.patch(
            f"/api/admin/users/{world.skills.id}", json={"report_name": "Synthetic PRINT NAME"}
        )
        assert named.status_code == 200, named.text
        uploaded = await client.put(signature, files={"file": ("s.png", png("black"), "image/png")})
        assert uploaded.status_code == 200, uploaded.text
    assert (
        await save_grid(
            api, world.skills, world.cls, [cell(world.student_one, world.skills_column, 64)]
        )
    ).status_code == 200
    async with TestSession() as db:
        skills = await db.get(m.User, world.skills.id)
        skills.google_subject = "synthetic-google-subject"
        db.add(
            m.OverrideGrant(
                user_id=world.skills.id,
                class_id=world.cls,
                role="main",
                expires_at=utcnow() + timedelta(days=1),
            )
        )
        await db.commit()
    async with api(world.admin) as client:
        await deactivate(client, world.skills.id)
        # A session that outlived deactivation is revoked with the account.
        sid = await sessions.create_session(world.skills.id)
        deleted = await erase(client, world.skills.id)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"deleted": True, "revoked_sessions": 1}
        assert (await client.get(signature)).status_code == 404
        audit = (await client.get(f"/api/audit?class_id={world.cls}")).json()["items"]
    assert await sessions.get_user_id(sid) is None
    assert [item["actor"] for item in audit] == [ERASED_USER_NAME]

    async with TestSession() as db:
        user = await db.get(m.User, world.skills.id)
        await db.refresh(user, attribute_names=["signature_png"])
        assert user.full_name == ERASED_USER_NAME
        assert user.email == f"deleted-{user.id}@deleted.invalid"
        assert (user.google_subject, user.report_name) == (None, None)
        assert (user.signature_png, user.signature_digest) == (None, None)
        assert (user.is_active, user.is_admin, user.is_coordinator) == (False, False, False)
        assert user.deleted_at is not None
        for model, column in (
            (m.TeachingAssignment, m.TeachingAssignment.user_id),
            (m.OverrideGrant, m.OverrideGrant.user_id),
            (m.ReportIdentityAudit, m.ReportIdentityAudit.user_id),
        ):
            assert await db.scalar(select(model.id).where(column == user.id)) is None
        grade = await db.scalar(
            select(m.GradeValue).where(
                m.GradeValue.student_id == world.student_one,
                m.GradeValue.column_definition_id == world.skills_column,
            )
        )
        assert (grade.score, grade.updated_by) == (64, user.id)
        assert await db.scalar(select(m.SaveBatch.id).where(m.SaveBatch.user_id == user.id))
        assert await db.scalar(select(m.AuditEntry.id).where(m.AuditEntry.actor_id == user.id))
        # The other teacher's assignment is untouched.
        main_slot = await db.scalar(
            select(m.TeachingAssignment.user_id).where(
                m.TeachingAssignment.class_id == world.cls, m.TeachingAssignment.role == "main"
            )
        )
        assert main_slot == world.main.id


async def test_deleted_account_leaves_every_list_and_its_email_can_be_added_again(api, world):
    async with api(world.admin) as client:
        teacher = await create_teacher(client, "leaver")
        await deactivate(client, int(teacher["id"]))
        assert (await erase(client, int(teacher["id"]))).status_code == 200
        listed = [item["id"] for item in (await client.get("/api/admin/users")).json()]
        inactive = [
            item["id"] for item in (await client.get("/api/admin/users?active=false")).json()
        ]
        pickers = [item["id"] for item in (await client.get("/api/users")).json()]
        edited = await client.patch(f"/api/admin/users/{teacher['id']}", json={"is_active": True})
        assigned = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": teacher["id"]}]},
        )
        again = await create_teacher(client, "leaver")
    assert teacher["id"] not in listed
    assert teacher["id"] not in inactive
    assert teacher["id"] not in pickers
    assert world.main.id in pickers
    assert edited.status_code == 404
    assert assigned.status_code == 422
    assert again["id"] != teacher["id"]
    assert again["email"] == teacher["email"]
    async with TestSession() as db:
        old = await db.get(m.User, int(teacher["id"]))
        assert (old.is_active, old.deleted_at is not None) == (False, True)


async def test_delete_scrubs_recorded_actions_and_no_undo_brings_the_account_back(api, world):
    async with api(world.admin) as client:
        teacher = await create_teacher(client, "former")
        teacher_id = int(teacher["id"])
        path = f"/api/admin/users/{teacher_id}"
        renamed = await client.patch(
            path, json={"full_name": "Synthetic Former Renamed", "report_name": "FORMER PRINT"}
        )
        first = await client.put(
            f"{path}/signature", files={"file": ("s.png", png("black"), "image/png")}
        )
        second = await client.put(
            f"{path}/signature", files={"file": ("s.png", png("blue"), "image/png")}
        )
        assigned = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": teacher_id}]},
        )
        handed_back = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": world.main.id}]},
        )
        deactivated = await deactivate(client, teacher_id)
        assert (await erase(client, teacher_id)).status_code == 200

        actions = {
            "create": teacher["action_id"],
            "rename": renamed.json()["action_id"],
            "first": first.json()["action_id"],
            "second": second.json()["action_id"],
            "assigned": assigned.json()["action_id"],
            "handed_back": handed_back.json()["action_id"],
            "deactivated": deactivated.json()["action_id"],
        }
        async with TestSession() as db:
            rows = {
                row.id: row
                for row in await db.scalars(
                    select(m.AdminAction).where(m.AdminAction.id.in_(actions.values()))
                )
            }
            blobs = {
                row.id: row.blob
                for row in await db.execute(
                    select(m.AdminAction.id, m.AdminAction.blob).where(
                        m.AdminAction.id.in_(actions.values())
                    )
                )
            }
        recorded = json.dumps(
            [[row.summary, row.undo_data] for row in rows.values()], ensure_ascii=False
        )
        for personal in (
            "Synthetic Former",
            "FORMER PRINT",
            teacher["email"],
        ):
            assert personal not in recorded
        assert all(blob is None for blob in blobs.values())
        for key in ("create", "rename", "first", "second", "deactivated"):
            row = rows[actions[key]]
            assert row.undo_data == {"user_id": teacher_id}
            assert row.summary["params"]["user"] == ERASED_USER_NAME
        rename_fields = [
            item["field"] for item in rows[actions["rename"]].summary["params"]["changes"]
        ]
        assert rename_fields == []
        assert rows[actions["assigned"]].summary["params"]["changes"][0]["to_teacher"] == (
            ERASED_USER_NAME
        )
        assert rows[actions["handed_back"]].summary["params"]["changes"][0] == {
            "class": "5/A",
            "role": "main",
            "from_teacher": ERASED_USER_NAME,
            "to_teacher": "Main Teacher",
        }

        for key in ("deactivated", "second", "rename", "create"):
            assert_target_missing(await undo(client, actions[key]))
        assert_target_missing(await undo(client, actions["handed_back"]))
        listed = (await client.get("/api/admin/actions")).json()["items"]
    assert ERASED_USER_NAME in json.dumps(listed, ensure_ascii=False)
    async with TestSession() as db:
        user = await db.get(m.User, teacher_id)
        assert (user.is_active, user.full_name, user.signature_digest) == (
            False,
            ERASED_USER_NAME,
            None,
        )
        assert (
            await db.scalar(
                select(m.TeachingAssignment.user_id).where(
                    m.TeachingAssignment.class_id == world.cls, m.TeachingAssignment.role == "main"
                )
            )
            == world.main.id
        )


async def test_delete_keeps_grant_backed_saves_and_ends_the_grants(api, world):
    async with api(world.skills) as client:
        granted = await client.post(f"/api/classes/{world.cls}/grants", json={"role": "main"})
    assert granted.status_code == 200, granted.text
    saved = await save_grid(
        api, world.skills, world.cls, [cell(world.student_one, world.main_column, 70)]
    )
    assert saved.status_code == 200, saved.text
    async with api(world.admin) as client:
        await deactivate(client, world.skills.id)
        deleted = await erase(client, world.skills.id)
    assert deleted.status_code == 200, deleted.text
    async with TestSession() as db:
        entry = (
            await db.scalars(select(m.AuditEntry).where(m.AuditEntry.actor_id == world.skills.id))
        ).one()
        # The audit row still names the grant the save went through.
        assert entry.via_grant_id is not None
        assert await db.get(m.OverrideGrant, entry.via_grant_id) is not None
        live = await db.scalar(
            select(m.OverrideGrant.id).where(
                m.OverrideGrant.user_id == world.skills.id,
                m.OverrideGrant.expires_at > func.now(),
            )
        )
        assert live is None


def mark_deleted(user_id: int):
    """What a permanent deletion holding the account's row lock has written so far."""

    async def hold(db) -> None:
        await db.execute(
            update(m.User)
            .where(m.User.id == user_id)
            .values(is_active=False, deleted_at=utcnow(), full_name=ERASED_USER_NAME)
        )

    return hold


@pytest.mark.parametrize("endpoint", ["matrix", "slot"])
async def test_assignment_waits_for_a_concurrent_deletion_and_refuses(api, world, endpoint):
    async with api(world.admin) as client:
        teacher = await create_teacher(client, "racing")
        teacher_id = int(teacher["id"])

        def request():
            if endpoint == "matrix":
                return client.put(
                    f"/api/admin/years/{world.year}/assignments",
                    json={
                        "changes": [{"class_id": world.cls, "role": "main", "user_id": teacher_id}]
                    },
                )
            return client.put(
                f"/api/classes/{world.cls}/assignments/main", json={"user_id": teacher_id}
            )

        response = await while_held(mark_deleted(teacher_id), request)
    assert response.status_code == 422, response.text
    async with TestSession() as db:
        assert (
            await db.scalar(
                select(m.TeachingAssignment.id).where(m.TeachingAssignment.user_id == teacher_id)
            )
            is None
        )
        kinds = list(await db.scalars(select(m.AdminAction.kind)))
    assert "assignments.replace" not in kinds


async def test_rollover_does_not_copy_a_deleted_teacher(world):
    async with TestSession() as db:
        year = await db.get(m.AcademicYear, world.year)
        year.label = "2026-2027"
        await mark_deleted(world.skills.id)(db)
        await db.commit()
    async with TestSession() as db:
        target = await _create_rollover_year(db, await db.get(m.AcademicYear, world.year))
        await db.commit()
        holders = set(
            await db.scalars(
                select(m.TeachingAssignment.user_id)
                .join(m.SchoolClass, m.SchoolClass.id == m.TeachingAssignment.class_id)
                .where(m.SchoolClass.year_id == target.id)
            )
        )
    assert holders == {world.main.id}


@pytest.mark.parametrize("kind", ["user.edit", "assignments.replace"])
async def test_undo_and_a_concurrent_deletion_lock_the_account_first(api, world, kind):
    async with api(world.admin) as client:
        teacher = await create_teacher(client, "undone")
        teacher_id = int(teacher["id"])
        if kind == "assignments.replace":
            for holder in (teacher_id, world.main.id):
                handed = await client.put(
                    f"/api/admin/years/{world.year}/assignments",
                    json={"changes": [{"class_id": world.cls, "role": "main", "user_id": holder}]},
                )
                assert handed.status_code == 200, handed.text
            action_id = handed.json()["action_id"]
        else:
            action_id = (await deactivate(client, teacher_id)).json()["action_id"]

        # A deletion locks the account, then the account's recorded actions to scrub them.
        async with TestSession() as db:
            await mark_deleted(teacher_id)(db)
            await db.flush()
            pending = asyncio.create_task(undo(client, action_id))
            await asyncio.sleep(0.5)
            await db.execute(
                select(m.AdminAction.id).where(m.AdminAction.id == action_id).with_for_update()
            )
            await db.commit()
        assert_target_missing(await pending)
