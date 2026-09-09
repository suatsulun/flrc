import pytest
from sqlalchemy import func, select

from flrc.db import models as m
from tests.conftest import TestSession, cell, save_grid


async def test_remove_roster_membership_preserves_identity_grades_audit_and_other_years(api, world):
    assert (
        await save_grid(
            api, world.main, world.cls, [cell(world.student_one, world.main_column, 81)]
        )
    ).status_code == 200
    async with TestSession() as db:
        past = m.AcademicYear(label="Synthetic archived year", status="archived")
        db.add(past)
        await db.flush()
        past_class = m.SchoolClass(year_id=past.id, grade_level=4, section="A")
        db.add(past_class)
        await db.flush()
        db.add_all(
            [
                m.Enrollment(
                    student_id=world.student_one,
                    year_id=past.id,
                    class_id=past_class.id,
                    school_number=41,
                ),
                m.StudentLanguage(student_id=world.student_one, year_id=past.id, language="french"),
                m.StudentLanguage(
                    student_id=world.student_one, year_id=world.year, language="german"
                ),
            ]
        )
        await db.commit()
        past_id = past.id
        grade = await db.scalar(select(m.GradeValue))
        original = (grade.id, grade.version, grade.score)
    async with api(world.admin) as client:
        removed = await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        assert removed.status_code == 200
        assert removed.json() == {"student_id": world.student_one, "removed": True}
        assert (await client.get(f"/api/admin/classes/{world.cls}/roster")).json()[0][
            "student_id"
        ] == world.student_two
        assert (
            await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        ).status_code == 404
    async with TestSession() as db:
        assert await db.get(m.Student, world.student_one) is not None
        assert await db.scalar(select(func.count()).select_from(m.AuditEntry)) == 1
        grade = await db.scalar(select(m.GradeValue))
        assert (grade.id, grade.version, grade.score) == original
        assert (
            await db.scalar(
                select(m.Enrollment.year_id).where(m.Enrollment.student_id == world.student_one)
            )
            == past_id
        )
        assert (
            await db.scalar(
                select(m.StudentLanguage.language).where(
                    m.StudentLanguage.student_id == world.student_one
                )
            )
            == "french"
        )


async def test_roster_removal_rejects_teacher_wrong_class_and_archived_year(api, world):
    async with api(world.main) as client:
        assert (
            await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        ).status_code == 403
    async with TestSession() as db:
        other = m.SchoolClass(year_id=world.year, grade_level=5, section="B")
        db.add(other)
        await db.commit()
        other_id = other.id
    async with api(world.admin) as client:
        assert (
            await client.delete(f"/api/admin/classes/{other_id}/roster/{world.student_one}")
        ).status_code == 404
    async with TestSession() as db:
        year = await db.get(m.AcademicYear, world.year)
        year.status = "archived"
        await db.commit()
    async with api(world.admin) as client:
        assert (
            await client.delete(f"/api/admin/classes/{world.cls}/roster/{world.student_one}")
        ).status_code == 409
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Enrollment)) == 2


@pytest.mark.parametrize("language", ["german", "french"])
async def test_grade_four_can_assign_and_clear_second_language(api, world, language):
    async with TestSession() as db:
        cls = await db.get(m.SchoolClass, world.cls)
        cls.grade_level = 4
        await db.commit()
    async with api(world.admin) as client:
        url = f"/api/admin/classes/{world.cls}/roster/{world.student_one}"
        assigned = await client.patch(url, json={"language": language})
        assert assigned.status_code == 200
        assert assigned.json()["language"] == language
        cleared = await client.patch(url, json={"language": None})
        assert cleared.status_code == 200
        assert cleared.json()["language"] is None


async def test_reorder_keeps_all_columns_and_rejects_duplicate_or_mixed_subject_ids(api, world):
    async with TestSession() as db:
        german = m.ColumnDefinition(
            semester_id=world.semester,
            grade_level=5,
            subject="german",
            value_type="text",
            owner_role="german",
            labels={"tr": "Synthetic German note"},
            position=1,
        )
        db.add(german)
        await db.commit()
        german_id = german.id
    async with api(world.admin) as client:
        for ids in [
            [world.main_column, world.main_column],
            [world.main_column],
            [world.main_column, german_id],
        ]:
            assert (
                await client.post(
                    "/api/columns/reorder",
                    params={"semester_id": world.semester},
                    json={"ordered_ids": ids},
                )
            ).status_code == 422
        response = await client.post(
            "/api/columns/reorder",
            params={"semester_id": world.semester},
            json={"ordered_ids": [world.skills_column, world.main_column]},
        )
        assert response.status_code == 200
        columns = (
            await client.get(
                "/api/columns",
                params={"semester_id": world.semester, "grade_level": 5, "subject": "english"},
            )
        ).json()
        assert [c["id"] for c in columns] == [world.skills_column, world.main_column]


async def test_removing_used_column_preserves_grades_and_audit_and_keeps_reordering_valid(
    api, world
):
    assert (
        await save_grid(
            api, world.main, world.cls, [cell(world.student_one, world.main_column, 88)]
        )
    ).status_code == 200
    async with api(world.admin) as client:
        removed = await client.delete(
            f"/api/columns/{world.main_column}", params={"semester_id": world.semester}
        )
        assert removed.status_code == 200
        assert removed.json() == {"deleted": False, "disabled": True}
        reordered = await client.post(
            "/api/columns/reorder",
            params={"semester_id": world.semester},
            json={"ordered_ids": [world.skills_column, world.main_column]},
        )
        assert reordered.status_code == 200
        unused = await client.delete(
            f"/api/columns/{world.skills_column}", params={"semester_id": world.semester}
        )
        assert unused.json() == {"deleted": True, "disabled": False}
    async with TestSession() as db:
        assert (await db.get(m.ColumnDefinition, world.main_column)).is_active is False
        assert await db.get(m.ColumnDefinition, world.skills_column) is None
        assert await db.scalar(select(m.GradeValue.score)) == 88
        assert await db.scalar(select(func.count()).select_from(m.AuditEntry)) == 1
