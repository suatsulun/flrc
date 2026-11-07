from types import SimpleNamespace

from sqlalchemy import delete, select

from flrc.db import models as m
from tests.conftest import TestSession

ADMIN = m.User(id=90001, email="dash-admin@example.test", full_name="Dash Admin", is_admin=True)
COORDINATOR = m.User(
    id=90002, email="dash-coordinator@example.test", full_name="Dash Coord", is_coordinator=True
)
TEACHER = m.User(id=90003, email="dash-teacher@example.test", full_name="Dash Teacher")


async def get_dashboard(api, user: m.User = ADMIN) -> dict:
    async with api(user) as client:
        response = await client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


async def make_school(
    *,
    year_status: str = "active",
    semesters: tuple[str, str] = ("open", "locked"),
    label: str = "2030-2031",
) -> SimpleNamespace:
    """A year with a fully staffed, fully numbered grade-5 class and one English field."""
    async with TestSession() as db:
        year = m.AcademicYear(label=label, status=year_status)
        db.add(year)
        await db.flush()
        terms = [
            m.Semester(year_id=year.id, number=number, status=status)
            for number, status in zip((1, 2), semesters, strict=True)
        ]
        school_class = m.SchoolClass(year_id=year.id, grade_level=5, section="A")
        main = m.User(
            email=f"main-{label}@example.test",
            full_name="Synthetic Main",
            teaching_stage="middle",
            report_name="Synthetic Main",
            signature_png=b"png",
        )
        skills = m.User(
            email=f"skills-{label}@example.test",
            full_name="Synthetic Skills",
            teaching_stage="middle",
            report_name="Synthetic Skills",
            signature_png=b"png",
        )
        student = m.Student(full_name="Synthetic Pupil", search_name="synthetic pupil")
        db.add_all([*terms, school_class, main, skills, student])
        await db.flush()
        columns = [
            m.ColumnDefinition(
                semester_id=term.id,
                grade_level=5,
                subject="english",
                value_type="score",
                owner_role="main",
                labels={"tr": "Sınav", "en": "Exam"},
                position=1,
            )
            for term in terms
        ]
        db.add_all(
            [
                *columns,
                m.TeachingAssignment(class_id=school_class.id, role="main", user_id=main.id),
                m.TeachingAssignment(class_id=school_class.id, role="skills", user_id=skills.id),
                m.Enrollment(
                    student_id=student.id,
                    year_id=year.id,
                    class_id=school_class.id,
                    school_number=7,
                ),
                m.StudentLanguage(student_id=student.id, year_id=year.id, language="german"),
            ]
        )
        await db.flush()
        db.add_all(
            [
                m.ColumnDefinition(
                    semester_id=term.id,
                    grade_level=5,
                    subject="german",
                    value_type="score",
                    owner_role="german",
                    labels={"tr": "Almanca sınav", "de": "Prüfung"},
                    position=1,
                )
                for term in terms
            ]
        )
        german = m.User(
            email=f"german-{label}@example.test",
            full_name="Synthetic German",
            teaching_field="german",
            teaching_stage=None,
            report_name="Synthetic German",
            signature_png=b"png",
        )
        db.add(german)
        await db.flush()
        db.add(m.TeachingAssignment(class_id=school_class.id, role="german", user_id=german.id))
        await db.commit()
        return SimpleNamespace(
            year=year.id,
            terms=[term.id for term in terms],
            cls=school_class.id,
            columns=[column.id for column in columns],
            student=student.id,
            main=main,
        )


async def fill_everything(school: SimpleNamespace, term_index: int = 0) -> None:
    async with TestSession() as db:
        columns = list(
            await db.scalars(
                select(m.ColumnDefinition.id).where(
                    m.ColumnDefinition.semester_id == school.terms[term_index]
                )
            )
        )
        db.add_all(
            [
                m.GradeValue(
                    student_id=school.student,
                    column_definition_id=column_id,
                    score=80,
                    updated_by=school.main.id,
                )
                for column_id in columns
            ]
        )
        await db.commit()


async def test_dashboard_is_for_admins_and_coordinators(api) -> None:
    async with api(TEACHER) as client:
        denied = await client.get("/api/dashboard")
    assert denied.status_code == 403
    assert (await get_dashboard(api, ADMIN))["next_step"]["code"] == "create_year"
    assert (await get_dashboard(api, COORDINATOR))["next_step"]["code"] == "create_year"


async def test_without_a_current_year_the_next_step_is_creating_one(api) -> None:
    async with TestSession() as db:
        db.add(m.AcademicYear(label="2020-2021", status="archived"))
        await db.commit()
    body = await get_dashboard(api)
    assert body["next_step"]["code"] == "create_year"
    assert body["term"]["year_id"] is None
    assert body["completion"] is None
    assert body["problems"] is None
    assert body["readiness"] == []
    assert body["overview"]["classes"] == 0


async def test_setup_year_activation_lists_missing_school_numbers(api) -> None:
    school = await make_school(year_status="setup", semesters=("locked", "locked"))
    ready = await get_dashboard(api)
    assert ready["term"]["year_status"] == "setup"
    assert ready["term"]["semester_number"] == 1
    assert ready["next_step"] == {
        "code": "activate_year",
        "semester_number": None,
        "completion_percent": None,
        "missing_cells": None,
        "blockers": [],
    }
    assert ready["completion"] is None
    assert ready["readiness"] == []

    async with TestSession() as db:
        enrollment = await db.scalar(
            select(m.Enrollment).where(m.Enrollment.student_id == school.student)
        )
        assert enrollment is not None
        enrollment.school_number = None
        await db.commit()
    blocked = await get_dashboard(api)
    assert blocked["next_step"]["blockers"] == [{"code": "missing_school_numbers", "count": 1}]


async def test_active_year_dashboard_wins_over_a_year_in_setup(api) -> None:
    await make_school(year_status="setup", semesters=("locked", "locked"), label="2031-2032")
    await make_school(label="2030-2031")
    body = await get_dashboard(api)
    assert body["term"]["year_label"] == "2030-2031"
    assert body["term"]["year_status"] == "active"


async def test_open_semester_collects_grades_then_advances_or_locks(api) -> None:
    school = await make_school()
    collecting = await get_dashboard(api)
    assert collecting["term"]["semester_status"] == "open"
    assert collecting["next_step"]["code"] == "collect_grades"
    assert collecting["next_step"]["semester_number"] == 1
    assert collecting["next_step"]["completion_percent"] == 0.0
    assert collecting["next_step"]["missing_cells"] == 2

    await fill_everything(school)
    complete = await get_dashboard(api)
    assert complete["next_step"]["code"] == "advance_semester"
    assert complete["next_step"]["completion_percent"] == 100.0
    assert complete["completion"]["complete_rows"] == 2
    assert complete["completion"]["incomplete_rows"] == 0

    async with TestSession() as db:
        first = await db.get(m.Semester, school.terms[0])
        second = await db.get(m.Semester, school.terms[1])
        assert first is not None and second is not None
        first.status = "locked"
        await db.flush()
        second.status = "open"
        await db.commit()
    second_term = await get_dashboard(api)
    assert second_term["next_step"]["code"] == "collect_grades"
    assert second_term["next_step"]["semester_number"] == 2

    await fill_everything(school, term_index=1)
    assert (await get_dashboard(api))["next_step"]["code"] == "lock_semester"


async def test_a_semester_without_fields_is_not_complete(api) -> None:
    school = await make_school()
    async with TestSession() as db:
        for column in await db.scalars(
            select(m.ColumnDefinition).where(m.ColumnDefinition.semester_id == school.terms[0])
        ):
            column.is_active = False
        await db.commit()
    body = await get_dashboard(api)
    assert body["next_step"]["code"] == "collect_grades"
    assert body["next_step"]["completion_percent"] is None
    assert body["completion"]["expected_cells"] == 0


async def test_both_semesters_locked_means_closing_the_year(api) -> None:
    school = await make_school(semesters=("locked", "locked"))
    await fill_everything(school, term_index=1)
    body = await get_dashboard(api)
    assert body["next_step"]["code"] == "close_year"
    assert body["term"]["semester_number"] == 2
    assert body["term"]["semester_status"] == "locked"
    assert body["completion"]["semester_number"] == 2
    assert body["completion"]["percent"] == 100.0


async def test_a_fully_prepared_school_has_no_setup_problems(api) -> None:
    await make_school()
    problems = (await get_dashboard(api))["problems"]
    for key in (
        "unassigned_roles",
        "classes_without_fields",
        "teachers_without_report_name",
        "teachers_without_signature",
        "students_without_number",
        "students_without_language",
    ):
        assert problems[key] == {"count": 0, "items": []}, key


async def test_setup_problem_detectors_name_the_concrete_items(api) -> None:
    school = await make_school()
    async with TestSession() as db:
        year_id = school.year
        # Grade 2: English only, no pupils, no fields, nobody assigned.
        lower = m.SchoolClass(year_id=year_id, grade_level=2, section="B")
        # Grade 6: a French pupil without a French teacher or French fields, and a pupil
        # without a number or second language.
        upper = m.SchoolClass(year_id=year_id, grade_level=6, section="C")
        unnamed = m.User(
            email="unnamed@example.test",
            full_name="Unnamed Teacher",
            teaching_stage="primary",
            signature_png=b"png",
        )
        unsigned = m.User(
            email="unsigned@example.test",
            full_name="Unsigned Teacher",
            teaching_stage="middle",
            report_name="Unsigned Teacher",
        )
        unassigned = m.User(
            email="idle@example.test", full_name="Idle Teacher", teaching_stage="middle"
        )
        french_pupil = m.Student(full_name="French Pupil", search_name="french pupil")
        bare_pupil = m.Student(full_name="Bare Pupil", search_name="bare pupil")
        young_pupil = m.Student(full_name="Young Pupil", search_name="young pupil")
        db.add_all(
            [lower, upper, unnamed, unsigned, unassigned, french_pupil, bare_pupil, young_pupil]
        )
        await db.flush()
        db.add_all(
            [
                m.TeachingAssignment(class_id=lower.id, role="main", user_id=unnamed.id),
                m.TeachingAssignment(class_id=upper.id, role="main", user_id=unsigned.id),
                m.Enrollment(
                    student_id=french_pupil.id, year_id=year_id, class_id=upper.id, school_number=8
                ),
                m.Enrollment(student_id=bare_pupil.id, year_id=year_id, class_id=upper.id),
                m.Enrollment(
                    student_id=young_pupil.id, year_id=year_id, class_id=lower.id, school_number=9
                ),
                m.StudentLanguage(student_id=french_pupil.id, year_id=year_id, language="french"),
            ]
        )
        await db.commit()

    problems = (await get_dashboard(api))["problems"]
    assert problems["semester_id"] == school.terms[0]
    assert {(gap["class_name"], gap["role"]) for gap in problems["unassigned_roles"]["items"]} == {
        ("2/B", "skills"),
        ("6/C", "skills"),
        ("6/C", "french"),
    }
    assert problems["unassigned_roles"]["count"] == 3
    assert {
        (gap["class_name"], gap["subject"]) for gap in problems["classes_without_fields"]["items"]
    } == {("2/B", "english"), ("6/C", "english"), ("6/C", "french")}
    assert [item["full_name"] for item in problems["teachers_without_report_name"]["items"]] == [
        "Unnamed Teacher"
    ]
    assert [item["full_name"] for item in problems["teachers_without_signature"]["items"]] == [
        "Unsigned Teacher"
    ]
    assert problems["students_without_number"] == {
        "count": 1,
        "items": [
            {
                "student_id": bare_pupil.id,
                "full_name": "Bare Pupil",
                "school_number": None,
                "class_id": upper.id,
                "class_name": "6/C",
                "grade_level": 6,
            }
        ],
    }
    # The grade-2 pupil is below the second-language grades; the French pupil has one.
    assert [item["full_name"] for item in problems["students_without_language"]["items"]] == [
        "Bare Pupil"
    ]
    assert (await get_dashboard(api))["overview"]["missing_assignments"] == 3


async def test_report_readiness_counts_classes_with_pupils_on_each_card(api) -> None:
    school = await make_school()
    async with TestSession() as db:
        # A second grade-5 class with one pupil and no German: complete once its cell is filled.
        other = m.SchoolClass(year_id=school.year, grade_level=5, section="B")
        # A grade-2 class without pupils is not eligible for the primary English card.
        empty = m.SchoolClass(year_id=school.year, grade_level=2, section="A")
        pupil = m.Student(full_name="Second Pupil", search_name="second pupil")
        db.add_all([other, empty, pupil])
        await db.flush()
        db.add(
            m.Enrollment(
                student_id=pupil.id, year_id=school.year, class_id=other.id, school_number=8
            )
        )
        db.add(
            m.GradeValue(
                student_id=pupil.id,
                column_definition_id=school.columns[0],
                score=90,
                updated_by=school.main.id,
            )
        )
        await db.commit()

    readiness = {item["kind"]: item for item in (await get_dashboard(api))["readiness"]}
    # 5/A's German pupil needs an English and a German score cell; 5/B's pupil only English.
    assert readiness["english_middle"] == {
        "kind": "english_middle",
        "eligible_classes": 2,
        "complete_classes": 1,
        "students": 2,
        "expected_cells": 3,
        "filled_cells": 1,
        "percent": 33.3,
    }
    assert readiness["german_karne"]["eligible_classes"] == 1
    assert readiness["german_karne"]["students"] == 1
    assert readiness["german_karne"]["percent"] == 0.0
    for kind in ("english_elementary", "french_karne"):
        assert readiness[kind]["eligible_classes"] == 0
        assert readiness[kind]["percent"] is None


async def test_middle_english_readiness_waits_for_second_language_scores(api) -> None:
    """The middle-school English card prints the pupil's German scores, not German notes."""
    school = await make_school()
    async with TestSession() as db:
        db.add(
            m.ColumnDefinition(
                semester_id=school.terms[0],
                grade_level=5,
                subject="german",
                value_type="text",
                owner_role="german",
                labels={"tr": "Almanca görüş", "de": "Bemerkung"},
                position=2,
            )
        )
        db.add(
            m.GradeValue(
                student_id=school.student,
                column_definition_id=school.columns[0],
                score=90,
                updated_by=school.main.id,
            )
        )
        await db.commit()

    english_only = {item["kind"]: item for item in (await get_dashboard(api))["readiness"]}
    assert english_only["english_middle"]["expected_cells"] == 2
    assert english_only["english_middle"]["filled_cells"] == 1
    assert english_only["english_middle"]["complete_classes"] == 0
    assert english_only["english_middle"]["percent"] == 50.0

    async with TestSession() as db:
        german_score = await db.scalar(
            select(m.ColumnDefinition.id).where(
                m.ColumnDefinition.semester_id == school.terms[0],
                m.ColumnDefinition.subject == "german",
                m.ColumnDefinition.value_type == "score",
            )
        )
        assert german_score is not None
        db.add(
            m.GradeValue(
                student_id=school.student,
                column_definition_id=german_score,
                score=70,
                updated_by=school.main.id,
            )
        )
        await db.commit()

    scored = {item["kind"]: item for item in (await get_dashboard(api))["readiness"]}
    # The German note does not hold up the English card, only the German karne.
    assert scored["english_middle"]["complete_classes"] == 1
    assert scored["english_middle"]["percent"] == 100.0
    assert scored["german_karne"]["expected_cells"] == 2
    assert scored["german_karne"]["percent"] == 50.0


async def test_missing_cells_name_pupil_field_and_owning_teacher(api, world) -> None:
    async with TestSession() as db:
        db.add(
            m.GradeValue(
                student_id=world.student_one,
                column_definition_id=world.main_column,
                score=70,
                updated_by=world.main.id,
            )
        )
        await db.execute(delete(m.TeachingAssignment).where(m.TeachingAssignment.role == "skills"))
        await db.commit()
    async with api(world.admin) as client:
        response = await client.get(
            f"/api/coordinator/classes/{world.cls}/missing",
            params={"semester_id": world.semester, "subject": "english"},
        )
    assert response.status_code == 200
    assert response.json() == [
        {
            "student_id": world.student_one,
            "school_number": 51001,
            "student_name": "Synthetic Student One",
            "column_id": world.skills_column,
            "field_name": "Skills score",
            "owner_role": "skills",
            "teacher_id": None,
            "teacher_name": None,
        },
        {
            "student_id": world.student_two,
            "school_number": 51002,
            "student_name": "Synthetic Student Two",
            "column_id": world.main_column,
            "field_name": "Main score",
            "owner_role": "main",
            "teacher_id": world.main.id,
            "teacher_name": "Main Teacher",
        },
        {
            "student_id": world.student_two,
            "school_number": 51002,
            "student_name": "Synthetic Student Two",
            "column_id": world.skills_column,
            "field_name": "Skills score",
            "owner_role": "skills",
            "teacher_id": None,
            "teacher_name": None,
        },
    ]
