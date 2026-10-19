import io
import json

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from flrc.db import models as m
from flrc.modules.imports.parser import parse_workbook
from flrc.modules.imports.review import ImportClassMove, ImportRosterEdits, review_sha256
from tests.conftest import TestSession, cell, save_grid


def roster_file(rows=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Students"
    sheet.append(["Okul No", "Ad Soyad", "Sınıf/Şube", "2. Yabancı Dil"])
    if rows is None:
        rows = [
            [
                70000 + index,
                "İpek Işık" if index == 205 else f"Synthetic Import {index:03}",
                "5/A" if index <= 120 else "5/B" if index <= 180 else "6/A",
                "Almanca" if index % 2 == 0 else "Fransızca",
            ]
            for index in range(1, 206)
        ]
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return {"file": ("synthetic-review.xlsx", buffer.getvalue())}


async def test_removed_manual_addition_is_omitted_from_identity_matching(api, world):
    files = roster_file([[70001, "Synthetic Kept Pupil", "5/A", None]])
    edits = {
        "additions": [
            {
                "school_number": 70002,
                "full_name": "Synthetic Removed Pupil",
                "grade_level": 5,
                "section": "A",
            }
        ],
        "removed_row_keys": ["middle:70002"],
    }
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            files=files,
            data={"roster_edits": json.dumps(edits)},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert [item["row"]["row_key"] for item in body["rows"]] == ["middle:70001"]
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": body["sha256"],
                "expected_review_sha256": body["review_sha256"],
            },
            files=files,
            data={"roster_edits": json.dumps(edits)},
        )
        assert committed.status_code == 200, committed.text
    async with TestSession() as db:
        assert (
            await db.scalar(
                select(m.Enrollment.id).where(
                    m.Enrollment.year_id == world.year, m.Enrollment.school_number == 70002
                )
            )
            is None
        )


async def test_review_pages_cover_every_student_and_filters_search_beyond_first_page(api, world):
    files = roster_file()
    async with api(world.admin) as client:
        pages = []
        offset = 0
        while offset is not None:
            response = await client.post(
                "/api/admin/import/dry-run",
                params={"year_id": world.year, "offset": offset},
                files=files,
            )
            assert response.status_code == 200
            page = response.json()
            pages.append(page)
            offset = page["next_offset"]
        filtered = await client.post(
            "/api/admin/import/dry-run",
            params={
                "year_id": world.year,
                "grade_level": 5,
                "section": "B",
                "language": "german",
                "action": "new_student",
            },
            files=files,
        )
        searched = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "q": "İPEK IŞIK"},
            files=files,
        )
    assert [len(page["rows"]) for page in pages] == [100, 100, 5]
    numbers = [item["row"]["school_number"] for page in pages for item in page["rows"]]
    assert numbers == list(range(70001, 70206))
    assert all(
        item["row"]["row_key"] == f"middle:{item['row']['school_number']}"
        for page in pages
        for item in page["rows"]
    )
    assert all(page["total_rows"] == 205 for page in pages)
    assert all(page["counts"]["new_students"] == 205 for page in pages)
    assert filtered.json()["filtered_rows"] == 30
    assert filtered.json()["total_rows"] == 205
    assert filtered.json()["next_offset"] is None
    assert searched.json()["rows"][0]["row"]["school_number"] == 70205
    assert searched.json()["filtered_rows"] == 1
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2


async def test_class_move_is_preview_only_until_matching_review_is_committed(api, world):
    files = roster_file()
    move = [{"row_key": "middle:70205", "grade_level": 5, "section": "B"}]
    async with api(world.admin) as client:
        original = (
            await client.post(
                "/api/admin/import/dry-run",
                params={"year_id": world.year},
                files=files,
            )
        ).json()
        reviewed = (
            await client.post(
                "/api/admin/import/dry-run",
                params={"year_id": world.year, "action": "class_changed"},
                data={"class_moves": json.dumps(move)},
                files=files,
            )
        ).json()
        assert reviewed["sha256"] == original["sha256"]
        assert reviewed["review_sha256"] != original["review_sha256"]
        assert reviewed["filtered_rows"] == 1
        assert reviewed["rows"][0]["original_class"] == "6/A"
        assert reviewed["rows"][0]["row"]["section"] == "B"
        assert (
            next(
                c["count"]
                for c in reviewed["classes"]
                if c["grade_level"] == 5 and c["section"] == "B"
            )
            == 61
        )
        async with TestSession() as db:
            assert await db.scalar(select(func.count()).select_from(m.Student)) == 2
        stale = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": original["sha256"],
                "expected_review_sha256": original["review_sha256"],
            },
            data={"class_moves": json.dumps(move)},
            files=files,
        )
        omitted = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": original["sha256"],
                "expected_review_sha256": reviewed["review_sha256"],
            },
            files=files,
        )
        assert stale.status_code == omitted.status_code == 409
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": reviewed["sha256"],
                "expected_review_sha256": reviewed["review_sha256"],
            },
            data={"class_moves": json.dumps(move)},
            files=files,
        )
        assert committed.status_code == 200
        repeated = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"class_moves": json.dumps(move)},
            files=files,
        )
        assert repeated.json()["counts"]["unchanged"] == 205
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 207
        destination = (
            await db.execute(
                select(m.SchoolClass.grade_level, m.SchoolClass.section)
                .join(m.Enrollment, m.Enrollment.class_id == m.SchoolClass.id)
                .where(m.Enrollment.year_id == world.year, m.Enrollment.school_number == 70205)
            )
        ).one()
        assert tuple(destination) == (5, "B")


@pytest.mark.parametrize(
    "moves",
    [
        "not-json",
        '[{"row_key":"middle:99999","grade_level":5,"section":"B"}]',
        # The source stage is part of the row identity: 70001 is a grade 5 row.
        '[{"row_key":"primary:70001","grade_level":5,"section":"B"}]',
        '[{"row_key":"70001","grade_level":5,"section":"B"}]',
        # The number-only identity was retired with stage-scoped numbers.
        '[{"school_number":70001,"grade_level":5,"section":"B"}]',
        '[{"row_key":"middle:70001","grade_level":5,"section":"Z"}]',
        '[{"row_key":"middle:70001","grade_level":9,"section":"B"}]',
        '[{"row_key":"middle:70001","grade_level":5,"section":"B","full_name":"Injected"}]',
        '[{"row_key":"middle:70001","grade_level":5,"section":"B"},{"row_key":"middle:70001","grade_level":6,"section":"A"}]',
    ],
)
async def test_invalid_review_edits_are_rejected_without_writes(api, world, moves):
    async with api(world.admin) as client:
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"class_moves": moves},
            files=roster_file(),
        )
    assert response.status_code == 422
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2


async def test_review_rejects_teachers_and_archived_years(api, world):
    async with api(world.main) as client:
        forbidden = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            files=roster_file(),
        )
    assert forbidden.status_code == 403
    async with TestSession() as db:
        year = await db.get(m.AcademicYear, world.year)
        year.status = "archived"
        await db.commit()
    async with api(world.admin) as client:
        archived = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            files=roster_file(),
        )
    assert archived.status_code == 409


async def test_review_accepts_existing_classes_with_multi_character_sections(api, world):
    async with TestSession() as db:
        db.add(m.SchoolClass(year_id=world.year, grade_level=5, section="A1"))
        await db.commit()
    async with api(world.admin) as client:
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "section": "A1"},
            data={
                "class_moves": json.dumps(
                    [{"row_key": "middle:70001", "grade_level": 5, "section": "A1"}]
                )
            },
            files=roster_file(),
        )
    assert response.status_code == 200
    assert response.json()["filtered_rows"] == 1
    assert response.json()["rows"][0]["row"]["section"] == "A1"


async def test_reviewed_move_preserves_student_identity_grades_and_audit(api, world):
    saved = await save_grid(
        api, world.main, world.cls, [cell(world.student_one, world.main_column, 75)]
    )
    assert saved.status_code == 200
    files = roster_file(
        [
            [51001, "Synthetic Student One", "5/A", None],
            [79001, "Synthetic New Classmate", "5/B", None],
        ]
    )
    moves = json.dumps([{"row_key": "middle:51001", "grade_level": 5, "section": "B"}])
    async with api(world.admin) as client:
        preview = (
            await client.post(
                "/api/admin/import/dry-run",
                params={"year_id": world.year},
                data={"class_moves": moves},
                files=files,
            )
        ).json()
        assert preview["counts"]["moved_students"] == 1
        result = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": preview["sha256"],
                "expected_review_sha256": preview["review_sha256"],
            },
            data={"class_moves": moves},
            files=files,
        )
    assert result.status_code == 200
    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(
                m.Enrollment.year_id == world.year, m.Enrollment.school_number == 51001
            )
        )
        assert enrollment.student_id == world.student_one
        assert enrollment.class_id != world.cls
        grade = await db.scalar(
            select(m.GradeValue).where(
                m.GradeValue.student_id == world.student_one,
                m.GradeValue.column_definition_id == world.main_column,
            )
        )
        assert (grade.score, grade.version, grade.updated_by) == (75, 1, world.main.id)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(m.AuditEntry)
                .where(m.AuditEntry.student_id == world.student_one)
            )
            == 1
        )


@pytest.mark.parametrize("verify_stale_review", [True, False], ids=["stale-review", "idempotency"])
async def test_review_add_exclude_and_clear_language_are_hashed_and_idempotent(
    api, world, verify_stale_review
):
    async with TestSession() as db:
        db.add(
            m.StudentLanguage(student_id=world.student_one, year_id=world.year, language="german")
        )
        await db.commit()
    files = roster_file(
        [
            [51001, "Synthetic Student One", "5/A", "Almanca"],
            [51002, "Synthetic Student Two", "5/A", "Fransızca"],
            [79001, "Synthetic Excluded New", "5/A", None],
        ]
    )
    edits = {
        "additions": [
            {
                "school_number": 79002,
                "full_name": "  Synthetic Manual Student  ",
                "grade_level": 5,
                "section": "A",
                "language": "french",
            }
        ],
        "removed_row_keys": ["middle:51002", "middle:79001"],
        "language_changes": [{"row_key": "middle:51001", "language": None}],
    }
    async with api(world.admin) as client:
        original = (
            await client.post(
                "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
            )
        ).json()
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "language": "none"},
            data={"roster_edits": json.dumps(edits)},
            files=files,
        )
        assert response.status_code == 200
        preview = response.json()
        assert preview["total_rows"] == 2
        assert preview["filtered_rows"] == 1
        assert preview["rows"][0]["row"]["language"] is None
        assert "language_edited" in preview["rows"][0]["actions"]
        assert preview["counts"]["new_students"] == 1
        async with TestSession() as db:
            assert await db.scalar(select(func.count()).select_from(m.Student)) == 2
            assert await db.scalar(select(m.StudentLanguage.language)) == "german"
        # Exercise stale hashes and replay separately: four rapid commits now
        # exceed the intentional three-request allowance for one account.
        stale_reviews = (
            [
                (original["review_sha256"], edits),
                (preview["review_sha256"], {}),
            ]
            if verify_stale_review
            else []
        )
        for stale_hash, payload in stale_reviews:
            stale = await client.post(
                "/api/admin/import/commit",
                params={
                    "year_id": world.year,
                    "expected_sha256": preview["sha256"],
                    "expected_review_sha256": stale_hash,
                },
                data={"roster_edits": json.dumps(payload)},
                files=files,
            )
            assert stale.status_code == 409
        for _ in range(1 if verify_stale_review else 2):
            committed = await client.post(
                "/api/admin/import/commit",
                params={
                    "year_id": world.year,
                    "expected_sha256": preview["sha256"],
                    "expected_review_sha256": preview["review_sha256"],
                },
                data={"roster_edits": json.dumps(edits)},
                files=files,
            )
            assert committed.status_code == 200
        if not verify_stale_review:
            assert committed.json()["counts"]["unchanged"] == 2
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 3
        numbers = set(
            (
                await db.execute(
                    select(m.Enrollment.school_number).where(m.Enrollment.year_id == world.year)
                )
            ).scalars()
        )
        assert numbers == {
            51001,
            51002,
            79002,
        }  # Excluding a file row never removes a saved enrollment.
        assert (
            await db.scalar(
                select(m.StudentLanguage.language).where(
                    m.StudentLanguage.student_id == world.student_one
                )
            )
            is None
        )
        manual = await db.scalar(
            select(m.Student).where(m.Student.full_name == "Synthetic Manual Student")
        )
        assert (
            await db.scalar(
                select(m.StudentLanguage.language).where(m.StudentLanguage.student_id == manual.id)
            )
            == "french"
        )


@pytest.mark.parametrize(
    "edits",
    [
        {"removed_row_keys": ["middle:99999"]},
        # The source stage is part of the row identity: 70001 is a grade 5 row.
        {"removed_row_keys": ["primary:70001"]},
        {"removed_row_keys": ["middle:70001", "middle:70001"]},
        {"removed_row_keys": ["70001"]},
        # The number-only identities were retired with stage-scoped numbers.
        {"removed_school_numbers": [70001]},
        {"language_changes": [{"school_number": 70001, "language": None}]},
        {"language_changes": [{"row_key": "middle:99999", "language": None}]},
        {"language_changes": [{"row_key": "middle:70001", "language": "spanish"}]},
        {
            "language_changes": [
                {"row_key": "middle:70001", "language": None},
                {"row_key": "middle:70001", "language": "french"},
            ]
        },
        {
            "additions": [
                {
                    # An addition's row key is derived from its class, never supplied.
                    "row_key": "middle:79999",
                    "school_number": 79999,
                    "full_name": "Synthetic Supplied Key",
                    "grade_level": 5,
                    "section": "A",
                }
            ]
        },
        {
            "additions": [
                {
                    "school_number": 79999,
                    "full_name": "Synthetic Invalid Class",
                    "grade_level": 5,
                    "section": "Z",
                }
            ]
        },
        {
            "additions": [
                {"school_number": 79999, "full_name": "  ", "grade_level": 5, "section": "A"}
            ]
        },
        {
            "additions": [
                {
                    "school_number": 79999,
                    "full_name": "Synthetic Injection",
                    "grade_level": 5,
                    "section": "A",
                    "student_id": 1,
                }
            ]
        },
    ],
)
async def test_invalid_roster_drafts_cannot_write(api, world, edits):
    async with api(world.admin) as client:
        result = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"roster_edits": json.dumps(edits)},
            files=roster_file(),
        )
    assert result.status_code == 422
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2


async def test_manual_add_cannot_rename_an_existing_student(api, world):
    edits = {
        "additions": [
            {
                "school_number": 51001,
                "full_name": "Synthetic Wrong Identity",
                "grade_level": 5,
                "section": "A",
            }
        ]
    }
    async with api(world.admin) as client:
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"roster_edits": json.dumps(edits)},
            files=roster_file(),
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "duplicate_school_number"


async def test_added_student_keeps_original_class_when_moved_in_review(api, world):
    edits = {
        "additions": [
            {
                "school_number": 79999,
                "full_name": "Synthetic Added Then Moved",
                "grade_level": 5,
                "section": "A",
            }
        ]
    }
    moves = [{"row_key": "middle:79999", "grade_level": 5, "section": "B"}]
    async with api(world.admin) as client:
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "q": "79999"},
            data={"roster_edits": json.dumps(edits), "class_moves": json.dumps(moves)},
            files=roster_file(),
        )
    assert response.status_code == 200
    item = response.json()["rows"][0]
    assert item["original_class"] == "5/A"
    assert item["row"]["section"] == "B"
    assert "manual_added" in item["actions"]
    assert "class_changed" in item["actions"]


def reviewed_commit_params(year_id, files, moves=(), edits=None):
    """Commit parameters for a review the server rejects before it can return a digest."""
    plan = parse_workbook(files["file"][1])
    digest = review_sha256(
        year_id,
        plan,
        [ImportClassMove.model_validate(move) for move in moves],
        ImportRosterEdits.model_validate(edits or {}),
    )
    return {"year_id": year_id, "expected_sha256": plan.sha256, "expected_review_sha256": digest}


async def test_grade_four_and_five_pupils_share_a_number_through_preview_and_commit(api, world):
    files = roster_file(
        [
            [70001, "Synthetic Primary Pupil", "4/A", None],
            [70001, "Synthetic Middle Pupil", "5/A", None],
        ]
    )
    async with api(world.admin) as client:
        response = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["issues"] == []
        assert preview["counts"]["new_students"] == 2
        # Equal numbers order by stage, so paging stays deterministic.
        assert [(item["row"]["row_key"], item["row"]["full_name"]) for item in preview["rows"]] == [
            ("middle:70001", "Synthetic Middle Pupil"),
            ("primary:70001", "Synthetic Primary Pupil"),
        ]
        searched = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year, "q": "70001"},
            files=files,
        )
        assert searched.json()["filtered_rows"] == 2
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": preview["sha256"],
                "expected_review_sha256": preview["review_sha256"],
            },
            files=files,
        )
        assert committed.status_code == 200, committed.text
        replayed = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        assert replayed.json()["counts"]["unchanged"] == 2
    async with TestSession() as db:
        enrolled = (
            await db.execute(
                select(m.SchoolClass.grade_level, m.Student.full_name)
                .join(m.Enrollment, m.Enrollment.class_id == m.SchoolClass.id)
                .join(m.Student, m.Student.id == m.Enrollment.student_id)
                .where(m.Enrollment.year_id == world.year, m.Enrollment.school_number == 70001)
                .order_by(m.SchoolClass.grade_level)
            )
        ).all()
    assert [tuple(row) for row in enrolled] == [
        (4, "Synthetic Primary Pupil"),
        (5, "Synthetic Middle Pupil"),
    ]


async def test_same_stage_number_conflict_blocks_the_import(api, world):
    files = roster_file(
        [
            [70001, "Synthetic Third Grader", "3/A", None],
            [70001, "Synthetic Fourth Grader", "4/A", None],
        ]
    )
    async with api(world.admin) as client:
        preview = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        committed = await client.post(
            "/api/admin/import/commit",
            params={"year_id": world.year, "expected_sha256": preview.json()["sha256"]},
            files=files,
        )
    assert preview.status_code == 200, preview.text
    assert [issue["code"] for issue in preview.json()["issues"]] == ["duplicate_conflict"]
    assert committed.status_code == 422
    assert committed.json()["detail"]["code"] == "import_has_errors"
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2


async def test_manual_addition_number_is_unique_within_its_stage_only(api, world):
    async with TestSession() as db:
        db.add(m.SchoolClass(year_id=world.year, grade_level=4, section="A"))
        await db.commit()
    files = roster_file([[70001, "Synthetic File Pupil", "5/A", None]])

    def addition(grade_level: int) -> dict[str, object]:
        return {
            "additions": [
                {
                    "school_number": 70001,
                    "full_name": "Synthetic Manual Pupil",
                    "grade_level": grade_level,
                    "section": "A",
                }
            ]
        }

    cross_stage = json.dumps(addition(4))
    async with api(world.admin) as client:
        duplicate = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"roster_edits": json.dumps(addition(5))},
            files=files,
        )
        response = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"roster_edits": cross_stage},
            files=files,
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        rows = {item["row"]["row_key"]: item for item in preview["rows"]}
        assert set(rows) == {"middle:70001", "primary:70001"}
        assert "manual_added" in rows["primary:70001"]["actions"]
        assert "manual_added" not in rows["middle:70001"]["actions"]
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": preview["sha256"],
                "expected_review_sha256": preview["review_sha256"],
            },
            data={"roster_edits": cross_stage},
            files=files,
        )
        assert committed.status_code == 200, committed.text
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_school_number"
    async with TestSession() as db:
        enrolled = (
            await db.execute(
                select(m.SchoolClass.grade_level, m.Student.full_name)
                .join(m.Enrollment, m.Enrollment.class_id == m.SchoolClass.id)
                .join(m.Student, m.Student.id == m.Enrollment.student_id)
                .where(m.Enrollment.year_id == world.year, m.Enrollment.school_number == 70001)
                .order_by(m.SchoolClass.grade_level)
            )
        ).all()
    assert [tuple(row) for row in enrolled] == [
        (4, "Synthetic Manual Pupil"),
        (5, "Synthetic File Pupil"),
    ]


SHARED_NUMBER_ROWS = [
    [70001, "Synthetic Primary Pupil", "4/A", None],
    [70001, "Synthetic Middle Pupil", "5/A", None],
]


@pytest.mark.parametrize(
    ("rows", "move"),
    [
        (SHARED_NUMBER_ROWS, {"row_key": "primary:70001", "grade_level": 5, "section": "A"}),
        (SHARED_NUMBER_ROWS, {"row_key": "middle:70001", "grade_level": 4, "section": "A"}),
        (
            [[51001, "Synthetic Primary Namesake", "4/A", None]],
            {"row_key": "primary:51001", "grade_level": 5, "section": "A"},
        ),
    ],
    ids=["primary-onto-file-row", "middle-onto-file-row", "primary-onto-enrolled-pupil"],
)
async def test_cross_stage_move_onto_a_taken_number_is_rejected_without_writes(
    api, world, rows, move
):
    files = roster_file(rows)
    moves = [move]
    async with api(world.admin) as client:
        unmoved = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        previewed = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"class_moves": json.dumps(moves)},
            files=files,
        )
        # A correct review digest reaches the commit's own collision check.
        committed = await client.post(
            "/api/admin/import/commit",
            params=reviewed_commit_params(world.year, files, moves),
            data={"class_moves": json.dumps(moves)},
            files=files,
        )
    assert unmoved.status_code == 200, unmoved.text
    for response in (previewed, committed):
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "duplicate_school_number"
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 2
        assert await db.scalar(select(func.count()).select_from(m.SchoolClass)) == 1
        enrolled = (
            await db.execute(
                select(m.Enrollment.student_id, m.Enrollment.class_id, m.Enrollment.school_number)
                .where(m.Enrollment.year_id == world.year)
                .order_by(m.Enrollment.school_number)
            )
        ).all()
    assert [tuple(row) for row in enrolled] == [
        (world.student_one, world.cls, 51001),
        (world.student_two, world.cls, 51002),
    ]


async def test_row_key_keeps_its_source_identity_across_a_stage_move(api, world):
    files = roster_file(
        [
            [51001, "Synthetic Student One", "5/A", None],
            [51002, "Synthetic Student Two", "5/A", None],
            [70001, "Synthetic Primary Pupil", "4/A", None],
        ]
    )
    moves = [{"row_key": "middle:51001", "grade_level": 4, "section": "A"}]
    edits = {
        "removed_row_keys": ["middle:51002"],
        "language_changes": [{"row_key": "middle:51001", "language": "german"}],
    }
    data = {"class_moves": json.dumps(moves), "roster_edits": json.dumps(edits)}
    # The destination stage never becomes a second identity for the moved row.
    destination_key = {"language_changes": [{"row_key": "primary:51001", "language": "german"}]}
    async with api(world.admin) as client:
        rejected = await client.post(
            "/api/admin/import/dry-run",
            params={"year_id": world.year},
            data={"class_moves": json.dumps(moves), "roster_edits": json.dumps(destination_key)},
            files=files,
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "invalid_import_student"
        response = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, data=data, files=files
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["total_rows"] == 2
        rows = {item["row"]["row_key"]: item for item in preview["rows"]}
        assert set(rows) == {"middle:51001", "primary:70001"}
        moved = rows["middle:51001"]
        assert (
            moved["row"]["school_number"],
            moved["row"]["grade_level"],
            moved["row"]["section"],
            moved["row"]["language"],
        ) == (51001, 4, "A", "german")
        assert moved["original_class"] == "5/A"
        assert {"move", "class_changed", "language_change", "language_edited"} <= set(
            moved["actions"]
        )
        assert preview["class_moves"] == moves
        assert preview["roster_edits"]["removed_row_keys"] == ["middle:51002"]
        committed = await client.post(
            "/api/admin/import/commit",
            params={
                "year_id": world.year,
                "expected_sha256": preview["sha256"],
                "expected_review_sha256": preview["review_sha256"],
            },
            data=data,
            files=files,
        )
        assert committed.status_code == 200, committed.text
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(m.Student)) == 3
        moved_enrollment = await db.scalar(
            select(m.Enrollment).where(m.Enrollment.student_id == world.student_one)
        )
        destination = await db.get(m.SchoolClass, moved_enrollment.class_id)
        assert (
            moved_enrollment.school_number,
            destination.grade_level,
            destination.section,
        ) == (51001, 4, "A")
        assert (
            await db.scalar(
                select(m.StudentLanguage.language).where(
                    m.StudentLanguage.student_id == world.student_one
                )
            )
            == "german"
        )
        # Excluding a file row skips it; the saved enrollment stays where it was.
        assert (
            await db.scalar(
                select(m.Enrollment.class_id).where(m.Enrollment.student_id == world.student_two)
            )
            == world.cls
        )


async def test_preview_rate_limit_allows_paging_without_spending_commit_budget(
    api, world, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from flrc.core import rate_limit

    evaluate = AsyncMock(side_effect=[(10, 50), (11, 49), (30, 48), (31, 47), (3, 46), (4, 45)])
    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    files = roster_file([[70123, "Synthetic Review", "5/A", "Almanca"]])
    async with api(world.admin) as client:
        for _ in range(3):
            preview = await client.post(
                "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
            )
            assert preview.status_code == 200
        limited = await client.post(
            "/api/admin/import/dry-run", params={"year_id": world.year}, files=files
        )
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == "47"
        params = {"year_id": world.year, "expected_sha256": preview.json()["sha256"]}
        committed = await client.post("/api/admin/import/commit", params=params, files=files)
        assert committed.status_code == 200
        limited_commit = await client.post("/api/admin/import/commit", params=params, files=files)
        assert limited_commit.status_code == 429
    assert evaluate.call_args_list[0].args[2] != evaluate.call_args_list[4].args[2]
