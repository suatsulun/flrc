"""School numbers are unique per academic year and school stage.

Primary (Hazırlık to grade 4) and middle-school (grades 5-8) pupils may share a
number. The `world` fixture's middle-school class 5/A holds 51001 and 51002.
"""

from sqlalchemy import select

from flrc.db import models as m
from tests.conftest import TestSession


async def add_class(year_id: int, grade_level: int, section: str) -> int:
    async with TestSession() as db:
        school_class = m.SchoolClass(year_id=year_id, grade_level=grade_level, section=section)
        db.add(school_class)
        await db.commit()
        return school_class.id


async def enroll(year_id: int, class_id: int, school_number: int, full_name: str) -> int:
    async with TestSession() as db:
        student = m.Student(full_name=full_name, search_name=full_name.lower())
        db.add(student)
        await db.flush()
        db.add(
            m.Enrollment(
                student_id=student.id,
                year_id=year_id,
                class_id=class_id,
                school_number=school_number,
            )
        )
        await db.commit()
        return student.id


async def placement(year_id: int, student_id: int) -> tuple[int, str, int | None]:
    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(
                m.Enrollment.year_id == year_id, m.Enrollment.student_id == student_id
            )
        )
        assert enrollment is not None
        return enrollment.class_id, enrollment.stage, enrollment.school_number


async def test_orm_reads_the_database_derived_stage(world):
    primary = await add_class(world.year, 4, "A")
    async with TestSession() as db:
        student = m.Student(full_name="Synthetic Stage Pupil", search_name="synthetic stage pupil")
        db.add(student)
        await db.flush()
        enrollment = m.Enrollment(
            student_id=student.id, year_id=world.year, class_id=primary, school_number=51001
        )
        db.add(enrollment)
        await db.flush()
        assert enrollment.stage == "primary"
        enrollment.class_id = world.cls
        enrollment.school_number = 51003
        await db.flush()
        assert enrollment.stage == "middle"
        await db.rollback()


async def test_manual_numbers_are_unique_within_a_stage(api, world):
    primary = await add_class(world.year, 4, "A")
    async with api(world.admin) as client:
        shared = await client.post(
            f"/api/admin/classes/{primary}/roster",
            json={"school_number": 51001, "full_name": "Synthetic Primary Pupil"},
        )
        roster_duplicate = await client.post(
            f"/api/admin/classes/{world.cls}/roster",
            json={"school_number": 51002, "full_name": "Synthetic Middle Duplicate"},
        )
        student_duplicate = await client.post(
            "/api/admin/students",
            json={
                "school_number": 51001,
                "full_name": "Synthetic Primary Duplicate",
                "year_id": world.year,
                "class_id": primary,
            },
        )
        second = await client.post(
            "/api/admin/students",
            json={
                "school_number": 51002,
                "full_name": "Synthetic Primary Second",
                "year_id": world.year,
                "class_id": primary,
            },
        )
        numeric = await client.get(
            "/api/admin/students", params={"q": "51001", "year_id": world.year}
        )
    assert shared.status_code == 201, shared.text
    assert second.status_code == 201, second.text
    for clash in (roster_duplicate, student_duplicate):
        assert clash.status_code == 409, clash.text
        assert clash.json()["detail"]["code"] == "duplicate_school_number"
    numbers = sorted((item["class_id"], item["school_number"]) for item in numeric.json()["items"])
    assert numbers == sorted([(primary, 51001), (world.cls, 51001)])

    pupil = shared.json()["student_id"]
    async with api(world.admin) as client:
        roster_clash = await client.patch(
            f"/api/admin/classes/{primary}/roster/{pupil}", json={"school_number": 51002}
        )
        middle_clash = await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_two}",
            json={"school_number": 51001},
        )
        renumbered = await client.patch(
            f"/api/admin/students/{pupil}",
            params={"year_id": world.year},
            json={"school_number": 51003},
        )
        middle_reuse = await client.patch(
            f"/api/admin/classes/{world.cls}/roster/{world.student_two}",
            json={"school_number": 51003},
        )
        student_clash = await client.patch(
            f"/api/admin/students/{world.student_one}",
            params={"year_id": world.year},
            json={"school_number": 51003},
        )
    for clash in (roster_clash, middle_clash, student_clash):
        assert clash.status_code == 409
        assert clash.json()["detail"]["code"] == "duplicate_school_number"
    assert renumbered.status_code == 200, renumbered.text
    assert middle_reuse.status_code == 200, middle_reuse.text
    assert await placement(world.year, pupil) == (primary, "primary", 51003)
    assert await placement(world.year, world.student_two) == (world.cls, "middle", 51003)
    assert await placement(world.year, world.student_one) == (world.cls, "middle", 51001)


async def test_cross_stage_move_keeps_numbers_and_refuses_clashes_atomically(api, world):
    primary = await add_class(world.year, 4, "A")
    other_middle = await add_class(world.year, 5, "B")
    clashing = await enroll(world.year, primary, 51001, "Synthetic Clashing Pupil")
    free = await enroll(world.year, primary, 40001, "Synthetic Free Pupil")
    async with api(world.admin) as client:
        into_taken = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [clashing, free],
                "target_class_id": world.cls,
                "allow_grade_change": True,
            },
        )
        together = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [clashing, world.student_one],
                "target_class_id": other_middle,
                "allow_grade_change": True,
            },
        )
        back_into_taken = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [world.student_one],
                "target_class_id": primary,
                "allow_grade_change": True,
            },
        )
        moved = await client.post(
            "/api/admin/roster/move",
            json={
                "student_ids": [free],
                "target_class_id": world.cls,
                "allow_grade_change": True,
            },
        )
    for refused in (into_taken, together, back_into_taken):
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "duplicate_school_number"
    assert moved.status_code == 200, moved.text
    assert moved.json() == {"changed": 1, "unchanged": 0}
    assert await placement(world.year, clashing) == (primary, "primary", 51001)
    assert await placement(world.year, world.student_one) == (world.cls, "middle", 51001)
    assert await placement(world.year, free) == (world.cls, "middle", 40001)


async def test_class_grade_edit_crosses_stage_only_when_numbers_are_free(api, world):
    primary = await add_class(world.year, 4, "A")
    pupil = await enroll(world.year, primary, 51001, "Synthetic Grade Edit Pupil")
    async with api(world.admin) as client:
        refused = await client.patch(f"/api/admin/classes/{primary}", json={"grade_level": 6})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "duplicate_school_number"
    async with TestSession() as db:
        school_class = await db.get(m.SchoolClass, primary)
        assert school_class is not None and school_class.grade_level == 4
    assert await placement(world.year, pupil) == (primary, "primary", 51001)

    async with api(world.admin) as client:
        renumbered = await client.patch(
            f"/api/admin/classes/{primary}/roster/{pupil}", json={"school_number": 41001}
        )
        promoted = await client.patch(f"/api/admin/classes/{primary}", json={"grade_level": 6})
    assert renumbered.status_code == 200, renumbered.text
    assert promoted.status_code == 200, promoted.text
    assert await placement(world.year, pupil) == (primary, "middle", 41001)

    async with api(world.admin) as client:
        demoted = await client.patch(f"/api/admin/classes/{primary}", json={"grade_level": 3})
    assert demoted.status_code == 200, demoted.text
    assert await placement(world.year, pupil) == (primary, "primary", 41001)


async def test_rollover_numbers_each_stage_from_one(api, world):
    async with TestSession() as db:
        existing_year = await db.get(m.AcademicYear, world.year)
        assert existing_year is not None
        existing_year.status = "archived"
        source = m.AcademicYear(label="2026-2027", status="active")
        db.add(source)
        await db.flush()
        db.add_all(
            [
                m.Semester(year_id=source.id, number=1, status="locked"),
                m.Semester(year_id=source.id, number=2, status="locked"),
            ]
        )
        classes = {
            grade: m.SchoolClass(year_id=source.id, grade_level=grade, section="A")
            for grade in (2, 3, 6, 7)
        }
        db.add_all(classes.values())
        await db.flush()
        students = {
            (grade, number): m.Student(
                full_name=f"Synthetic Rollover {grade}-{number}",
                search_name=f"synthetic rollover {grade}-{number}",
            )
            for grade in (2, 6)
            for number in (11, 10)
        }
        db.add_all(students.values())
        await db.flush()
        # Both stages already reuse the same numbers in the source year.
        db.add_all(
            [
                m.Enrollment(
                    student_id=student.id,
                    year_id=source.id,
                    class_id=classes[grade].id,
                    school_number=number,
                )
                for (grade, number), student in students.items()
            ]
        )
        await db.commit()
        source_id = source.id
        student_ids = {key: student.id for key, student in students.items()}

    async with api(world.admin) as client:
        exported = await client.get(f"/api/admin/years/{source_id}/audit-export.csv")
        closed = await client.post(
            f"/api/admin/years/{source_id}/close",
            json={
                "confirm_label": "2026-2027",
                "audit_sha256": exported.headers["x-audit-sha256"],
            },
        )
    assert closed.status_code == 200, closed.text

    async with TestSession() as db:
        target = await db.scalar(select(m.AcademicYear).where(m.AcademicYear.label == "2027-2028"))
        assert target is not None
        rows = (
            await db.execute(
                select(
                    m.Enrollment.student_id,
                    m.SchoolClass.grade_level,
                    m.Enrollment.stage,
                    m.Enrollment.school_number,
                )
                .join(m.SchoolClass, m.SchoolClass.id == m.Enrollment.class_id)
                .where(m.Enrollment.year_id == target.id)
            )
        ).all()
    promoted = {student_id: (grade, stage, number) for student_id, grade, stage, number in rows}
    # Fresh numbers follow the old class order, counted separately per stage.
    assert promoted == {
        student_ids[(2, 10)]: (3, "primary", 1),
        student_ids[(2, 11)]: (3, "primary", 2),
        student_ids[(6, 10)]: (7, "middle", 1),
        student_ids[(6, 11)]: (7, "middle", 2),
    }
