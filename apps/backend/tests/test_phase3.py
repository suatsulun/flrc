import io

from openpyxl import Workbook
from sqlalchemy import select, update

from flrc.db import models as m
from flrc.modules.administration.names import search_key
from flrc.modules.imports.parser import parse_workbook
from tests.conftest import TestSession, cell, save_grid


def workbook_bytes(rows: list[list[object]], title: str = "5-A") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_turkish_search_key_equivalence() -> None:
    assert search_key("İPEK IŞIK") == search_key("İpek Işık")


async def test_student_management_search_and_duplicate_guard(api, world):
    async with api(world.admin) as client:
        created = await client.post(
            "/api/admin/students",
            json={
                "school_number": 59999,
                "full_name": "İpek Işık",
                "year_id": world.year,
                "class_id": world.cls,
            },
        )
        found = await client.get("/api/admin/students", params={"q": "ipek"})
        numeric = await client.get("/api/admin/students", params={"q": "59999"})
        duplicate = await client.post(
            "/api/admin/students",
            json={
                "school_number": 59999,
                "full_name": "Synthetic Duplicate",
                "year_id": world.year,
                "class_id": world.cls,
            },
        )
    assert created.status_code == 201
    assert found.json()["items"][0]["full_name"] == "İpek Işık"
    assert numeric.json()["items"][0]["school_number"] == 59999
    assert duplicate.status_code == 409


async def test_admin_resources_reject_teacher_and_coordinator_reads_are_separate(api, world):
    async with api(world.main) as client:
        denied = await client.get("/api/admin/students")
        coordinator_denied = await client.get("/api/coordinator/overview")
    assert denied.status_code == 403
    assert coordinator_denied.status_code == 403

    coordinator = m.User(
        id=999,
        email="coordinator@example.test",
        full_name="Synthetic Coordinator",
        is_coordinator=True,
    )
    async with api(coordinator) as client:
        overview = await client.get("/api/coordinator/overview")
        admin_denied = await client.get("/api/admin/students")
    assert overview.status_code == 200
    assert admin_denied.status_code == 403


async def test_roster_move_preserves_grade_identity_and_version(api, world):
    await save_grid(
        api,
        world.main,
        world.cls,
        [cell(world.student_one, world.main_column, 88)],
    )
    async with TestSession() as db:
        target = m.SchoolClass(year_id=world.year, grade_level=5, section="B")
        db.add(target)
        await db.commit()
        target_id = target.id
        before = (await db.execute(select(m.GradeValue))).scalars().one()
        before_identity = (before.id, before.version, before.score)
    async with api(world.admin) as client:
        moved = await client.post(
            "/api/admin/roster/move",
            json={"student_ids": [world.student_one], "target_class_id": target_id},
        )
    assert moved.status_code == 200
    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(m.Enrollment.student_id == world.student_one)
        )
        after = (await db.execute(select(m.GradeValue))).scalars().one()
    assert enrollment is not None and enrollment.class_id == target_id
    assert (after.id, after.version, after.score) == before_identity


async def test_lifecycle_transitions_are_explicit(api, world):
    async with api(world.admin) as client:
        created = await client.post("/api/admin/years", json={"label": "2027-2028"})
    year_id = created.json()["id"]
    async with api(world.admin) as client:
        blocked = await client.post(f"/api/admin/years/{year_id}/activate")
    assert blocked.status_code == 409
    async with TestSession() as db:
        await db.execute(
            update(m.AcademicYear).where(m.AcademicYear.id == world.year).values(status="archived")
        )
        await db.commit()
    async with api(world.admin) as client:
        activated = await client.post(f"/api/admin/years/{year_id}/activate")
        advanced = await client.post(f"/api/admin/years/{year_id}/advance-semester")
        reopened = await client.post(
            f"/api/admin/years/{year_id}/reopen-semester",
            json={"number": 1, "confirm_label": "2027-2028"},
        )
        advanced_again = await client.post(f"/api/admin/years/{year_id}/advance-semester")
        locked = await client.post(f"/api/admin/years/{year_id}/lock-semester-2")
    assert activated.json()["semesters"][0]["status"] == "open"
    assert activated.json()["missing_school_numbers"] == 0
    assert advanced.json()["semesters"][0]["status"] == "locked"
    assert advanced.json()["semesters"][1]["status"] == "open"
    assert reopened.json()["semesters"][0]["status"] == "open"
    assert reopened.json()["semesters"][1]["status"] == "locked"
    assert advanced_again.json()["semesters"][1]["status"] == "open"
    assert all(item["status"] == "locked" for item in locked.json()["semesters"])


async def test_backfilled_years_sort_chronologically_and_keep_current_school_number(api, world):
    async with TestSession() as db:
        current = await db.get(m.AcademicYear, world.year)
        current.label = "2026-2027"
        for label in ("2025-2026", "2023-2024", "2024-2025"):
            year = m.AcademicYear(label=label, status="archived")
            db.add(year)
            await db.flush()
            school_class = m.SchoolClass(year_id=year.id, grade_level=4, section="A")
            db.add(school_class)
            await db.flush()
            db.add(
                m.Enrollment(
                    year_id=year.id,
                    class_id=school_class.id,
                    student_id=world.student_one,
                    school_number=100,
                )
            )
        await db.commit()
    async with api(world.admin) as client:
        years = await client.get("/api/admin/years")
        archived = await client.get("/api/archive/years")
        history = await client.get(f"/api/archive/students/{world.student_one}/history")
    labels = ["2023-2024", "2024-2025", "2025-2026", "2026-2027"]
    assert [year["label"] for year in years.json()] == labels[::-1]
    assert [year["label"] for year in archived.json()] == labels[-2::-1]
    assert [year["label"] for year in history.json()["years"]] == labels
    assert history.json()["school_number"] == 51001


def test_import_parser_reports_conflicting_duplicate() -> None:
    data = workbook_bytes(
        [
            ["Okul No", "Ad Soyad", "Sınıf/Şube"],
            [70001, "Synthetic One", "5/A"],
            [70001, "Synthetic One", "5/B"],
        ],
        title="Mixed",
    )
    plan = parse_workbook(data)
    assert plan.has_errors
    assert any(issue.code == "duplicate_conflict" for issue in plan.issues)


async def test_import_dry_run_is_write_free_hash_checked_and_idempotent(api, world):
    data = workbook_bytes(
        [
            ["Okul No", "Ad Soyad", "Yabancı Dil"],
            [52000, "Synthetic Import Student", "Almanca"],
        ]
    )
    files = {
        "file": (
            "synthetic.xlsx",
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
    assert preview.status_code == 200
    assert preview.json()["counts"]["new_students"] == 1
    async with TestSession() as db:
        assert (
            await db.scalar(
                select(m.Enrollment.id).where(
                    m.Enrollment.year_id == world.year,
                    m.Enrollment.school_number == 52000,
                )
            )
            is None
        )
    async with api(world.admin) as client:
        mismatch = await client.post(
            "/api/admin/import/commit",
            params={"year_id": world.year, "expected_sha256": "0" * 64},
            files=files,
        )
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": preview.json()["sha256"],
            },
            files=files,
        )
        second = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
    assert mismatch.status_code == 409
    assert committed.status_code == 200
    assert second.json()["counts"]["unchanged"] == 1


async def test_school_numbers_are_unique_per_year_not_globally(api, world):
    async with TestSession() as db:
        future = m.AcademicYear(label="2030-2031", status="setup")
        db.add(future)
        await db.flush()
        future_class = m.SchoolClass(year_id=future.id, grade_level=5, section="A")
        db.add(future_class)
        await db.commit()
        future_class_id = future_class.id

    async with api(world.admin) as client:
        reused = await client.post(
            f"/api/admin/classes/{future_class_id}/roster",
            json={"school_number": 51001, "full_name": "Different Synthetic Student"},
        )
    assert reused.status_code == 201

    async with TestSession() as db:
        matching = list(
            (
                await db.execute(select(m.Enrollment).where(m.Enrollment.school_number == 51001))
            ).scalars()
        )
    assert len(matching) == 2
    assert len({item.year_id for item in matching}) == 2


async def test_archiving_standard_year_builds_connected_rollover(api, world):
    async with TestSession() as db:
        existing_year = await db.get(m.AcademicYear, world.year)
        assert existing_year is not None
        existing_year.status = "archived"
        source = m.AcademicYear(label="2026-2027", status="active")
        db.add(source)
        await db.flush()
        first = m.Semester(year_id=source.id, number=1, status="locked")
        second = m.Semester(year_id=source.id, number=2, status="locked")
        grade_five = m.SchoolClass(year_id=source.id, grade_level=5, section="A")
        grade_six = m.SchoolClass(year_id=source.id, grade_level=6, section="A")
        db.add_all([first, second, grade_five, grade_six])
        await db.flush()
        student = m.Student(full_name="Rollover Student", search_name="rollover student")
        db.add(student)
        await db.flush()
        db.add_all(
            [
                m.Enrollment(
                    student_id=student.id,
                    year_id=source.id,
                    class_id=grade_five.id,
                    school_number=200,
                ),
                m.StudentLanguage(
                    student_id=student.id,
                    year_id=source.id,
                    language="german",
                ),
                m.TeachingAssignment(
                    class_id=grade_five.id,
                    role="main",
                    user_id=world.main.id,
                ),
                m.ColumnDefinition(
                    semester_id=first.id,
                    grade_level=5,
                    subject="english",
                    value_type="score",
                    owner_role="main",
                    labels={"tr": "Sınav", "en": "Exam", "de": "", "fr": ""},
                    position=1,
                ),
            ]
        )
        await db.commit()
        source_id = source.id
        student_id = student.id

    async with api(world.admin) as client:
        exported = await client.get(f"/api/admin/years/{source_id}/audit-export.csv")
        closed = await client.post(
            f"/api/admin/years/{source_id}/close",
            json={
                "confirm_label": "2026-2027",
                "audit_sha256": exported.headers["x-audit-sha256"],
            },
        )
    assert closed.status_code == 200

    async with api(world.admin) as client:
        years = await client.get("/api/admin/years")
        target_id = next(item["id"] for item in years.json() if item["label"] == "2027-2028")
        activated = await client.post(f"/api/admin/years/{target_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["missing_school_numbers"] == 0

    async with TestSession() as db:
        target = await db.scalar(select(m.AcademicYear).where(m.AcademicYear.label == "2027-2028"))
        assert target is not None and target.status == "active"
        promoted = await db.scalar(
            select(m.Enrollment).where(
                m.Enrollment.year_id == target.id,
                m.Enrollment.student_id == student_id,
            )
        )
        promoted_class = await db.get(m.SchoolClass, promoted.class_id if promoted else 0)
        assert promoted is not None and promoted.school_number == 1
        assert promoted_class is not None and promoted_class.grade_level == 6
        assert await db.scalar(
            select(m.StudentLanguage.id).where(
                m.StudentLanguage.year_id == target.id,
                m.StudentLanguage.student_id == student_id,
            )
        )


async def test_assignment_rejects_teacher_outside_their_field(api, world):
    async with TestSession() as db:
        teacher = await db.get(m.User, world.main.id)
        assert teacher is not None
        teacher.teaching_field = "german"
        teacher.teaching_stage = None
        await db.commit()

    async with api(world.admin) as client:
        rejected = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "main", "user_id": world.main.id}]},
        )
        accepted = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={"changes": [{"class_id": world.cls, "role": "german", "user_id": world.main.id}]},
        )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "teacher_field_mismatch"
    assert accepted.status_code == 200


async def test_assignment_rejects_english_teacher_from_wrong_school_stage(api, world):
    async with TestSession() as db:
        primary_class = m.SchoolClass(
            year_id=world.year,
            grade_level=2,
            section="A",
        )
        primary_teacher = m.User(
            email="primary@example.test",
            full_name="Primary Teacher",
            teaching_stage="primary",
        )
        db.add_all([primary_class, primary_teacher])
        await db.commit()
        primary_class_id = primary_class.id
        primary_teacher_id = primary_teacher.id

    async with api(world.admin) as client:
        rejected = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={
                "changes": [
                    {"class_id": primary_class_id, "role": "main", "user_id": world.main.id}
                ]
            },
        )
        accepted = await client.put(
            f"/api/admin/years/{world.year}/assignments",
            json={
                "changes": [
                    {
                        "class_id": primary_class_id,
                        "role": "main",
                        "user_id": primary_teacher_id,
                    }
                ]
            },
        )

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "teacher_stage_mismatch"
    assert accepted.status_code == 200


async def test_teacher_stage_cannot_invalidate_existing_assignments(api, world):
    async with api(world.admin) as client:
        rejected = await client.patch(
            f"/api/admin/users/{world.main.id}",
            json={"teaching_stage": "primary"},
        )

    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "teacher_assignments_incompatible"


async def test_column_owner_must_match_subject(api, world):
    async with api(world.admin) as client:
        rejected = await client.post(
            "/api/columns",
            params={"semester_id": world.semester},
            json={
                "grade_level": 5,
                "subject": "english",
                "value_type": "score",
                "owner_role": "german",
                "labels": {"tr": "Uyumsuz", "en": "Mismatch", "de": "", "fr": ""},
                "counts_in_average": False,
            },
        )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "owner_subject_mismatch"
