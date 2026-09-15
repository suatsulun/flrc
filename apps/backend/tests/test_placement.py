"""Rollover stops at stage boundaries; the roster import places pupils by name (ADR-066)."""

import io

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from flrc.db import models as m
from flrc.modules.academics.class_names import PREP_GRADE
from flrc.modules.academics.programme import carries_over
from tests.conftest import TestSession
from tests.test_import_review import roster_file


def test_only_pupils_inside_a_stage_carry_over() -> None:
    assert [grade for grade in range(0, 9) if carries_over(grade)] == [1, 2, 3, 5, 6, 7]


def placement_roster() -> dict[str, tuple[str, bytes]]:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Liste"
    sheet.append(["Okul No", "Ad Soyad", "Sınıf/Şube"])
    sheet.append([91001, "Synthetic Prep Pupil", "1/A"])
    sheet.append([91002, "Synthetic Fourth Grader", "5/B"])
    sheet.append([91003, "Synthetic Graduate", "5/B"])
    sheet.append([91004, "Synthetic Twin", "1/A"])
    sheet.append([91005, "Synthetic Newcomer", "5/B"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return {"file": ("synthetic-placement.xlsx", buffer.getvalue())}


async def test_rollover_leaves_placement_grades_and_import_reattaches_them(api, world):
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
            grade: m.SchoolClass(year_id=source.id, grade_level=grade, section=section)
            for grade, section in (
                (PREP_GRADE, "Bulut"),
                (3, "A"),
                (4, "A"),
                (5, "A"),
                (6, "A"),
                (8, "A"),
            )
        }
        db.add_all(classes.values())
        await db.flush()
        pupils = {
            key: m.Student(full_name=name, search_name=name.casefold())
            for key, name in (
                ("prep", "Synthetic Prep Pupil"),
                ("third", "Synthetic Third Grader"),
                ("fourth", "Synthetic Fourth Grader"),
                ("fifth", "Synthetic Fifth Grader"),
                ("graduate", "Synthetic Graduate"),
                ("twin_one", "Synthetic Twin"),
                ("twin_two", "Synthetic Twin"),
            )
        }
        db.add_all(pupils.values())
        await db.flush()
        placements = {
            "prep": PREP_GRADE,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "graduate": 8,
            "twin_one": PREP_GRADE,
            "twin_two": PREP_GRADE,
        }
        db.add_all(
            [
                m.Enrollment(
                    student_id=pupils[key].id,
                    year_id=source.id,
                    class_id=classes[grade].id,
                    school_number=index,
                )
                for index, (key, grade) in enumerate(placements.items(), start=1)
            ]
        )
        await db.commit()
        source_id = source.id
        ids = {key: pupil.id for key, pupil in pupils.items()}

    async with api(world.admin) as client:
        exported = await client.get(f"/api/admin/years/{source_id}/audit-export.csv")
        closed = await client.post(
            f"/api/admin/years/{source_id}/close",
            json={"confirm_label": "2026-2027", "audit_sha256": exported.headers["x-audit-sha256"]},
        )
        assert closed.status_code == 200, closed.text
        years = await client.get("/api/admin/years")
        target_id = next(item["id"] for item in years.json() if item["label"] == "2027-2028")

    async with TestSession() as db:
        carried = (
            await db.execute(
                select(m.Enrollment.student_id, m.SchoolClass.grade_level, m.SchoolClass.section)
                .join(m.SchoolClass, m.SchoolClass.id == m.Enrollment.class_id)
                .where(m.Enrollment.year_id == target_id)
                .order_by(m.SchoolClass.grade_level)
            )
        ).all()
    assert [tuple(row) for row in carried] == [(ids["third"], 4, "A"), (ids["fifth"], 6, "A")]

    files = placement_roster()
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": target_id}, files=files
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        actions = {row["row"]["school_number"]: row["actions"] for row in body["rows"]}
        assert actions[91001] == ["new_class", "placed", "new_enrollment"]
        assert actions[91002] == ["new_class", "placed", "new_enrollment"]
        # A graduate is never re-attached, and two awaiting namesakes match nothing.
        assert "placed" not in actions[91003] and "new_student" in actions[91003]
        assert "placed" not in actions[91004] and "new_student" in actions[91004]
        assert "new_student" in actions[91005]
        assert body["counts"]["placed_students"] == 2
        assert body["counts"]["new_students"] == 3
        placed_only = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": target_id, "action": "placed"},
            files=files,
        )
        assert placed_only.json()["filtered_rows"] == 2
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": target_id,
                "expected_sha256": body["sha256"],
                "expected_review_sha256": body["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text

    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == len(ids) + 3 + 2
        placed = (
            await db.execute(
                select(m.Enrollment.student_id, m.Enrollment.school_number)
                .where(
                    m.Enrollment.year_id == target_id,
                    m.Enrollment.student_id.in_([ids["prep"], ids["fourth"]]),
                )
                .order_by(m.Enrollment.school_number)
            )
        ).all()
        assert [tuple(row) for row in placed] == [(ids["prep"], 91001), (ids["fourth"], 91002)]
        graduate_enrollments = await db.scalar(
            select(func.count())
            .select_from(m.Enrollment)
            .where(
                m.Enrollment.year_id == target_id,
                m.Enrollment.student_id == ids["graduate"],
            )
        )
    assert graduate_enrollments == 0


@pytest.mark.parametrize(
    ("source_label", "source_grade", "target_grade", "incoming_count", "expected_matches"),
    [
        ("2026-2027", 0, 1, 1, 1),
        ("2026-2027", 4, 5, 1, 1),
        ("2026-2027", 0, 5, 1, 0),
        ("2026-2027", 4, 1, 1, 0),
        ("2024-2025", 0, 1, 1, 0),
        ("2026-2027", 0, 1, 2, 0),
    ],
)
async def test_placement_requires_the_previous_year_correct_stage_and_unique_incoming_name(
    api, world, source_label, source_grade, target_grade, incoming_count, expected_matches
):
    async with TestSession() as db:
        source = m.AcademicYear(label=source_label, status="archived")
        target = m.AcademicYear(label="2027-2028", status="setup")
        student = m.Student(full_name="Synthetic Namesake", search_name="synthetic namesake")
        db.add_all([source, target, student])
        await db.flush()
        school_class = m.SchoolClass(year_id=source.id, grade_level=source_grade, section="A")
        db.add(school_class)
        await db.flush()
        db.add(
            m.Enrollment(
                student_id=student.id, year_id=source.id, class_id=school_class.id, school_number=1
            )
        )
        await db.commit()
        target_id, student_id = target.id, student.id

    files = roster_file(
        [
            [92000 + index, "Synthetic Namesake", f"{target_grade}/A", None]
            for index in range(incoming_count)
        ]
    )
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": target_id}, files=files
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["counts"]["placed_students"] == expected_matches
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": target_id,
                "expected_sha256": body["sha256"],
                "expected_review_sha256": body["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text
    async with TestSession() as db:
        matched = await db.scalar(
            select(func.count())
            .select_from(m.Enrollment)
            .where(m.Enrollment.year_id == target_id, m.Enrollment.student_id == student_id)
        )
        assert matched == expected_matches


async def test_numberless_namesakes_are_not_claimed_by_workbook_order(api, world):
    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(m.Enrollment.student_id == world.student_one)
        )
        enrollment.school_number = None
        await db.commit()
    files = roster_file(
        [
            [93001, "Synthetic Student One", "5/A", None],
            [93002, "Synthetic Student One", "5/A", None],
        ]
    )
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        body = preview.json()
        assert body["counts"]["assigned_numbers"] == 0
        assert body["counts"]["new_students"] == 2
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": body["sha256"],
                "expected_review_sha256": body["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text
    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(m.Enrollment.student_id == world.student_one)
        )
        assert enrollment.school_number is None
