import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

TEST_URL = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test"


def test_migrations_apply_from_zero() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.mark.parametrize("prep_table", ["school_classes", "column_definitions"])
def test_prep_downgrade_refuses_data_loss(prep_table: str) -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    engine = create_engine(TEST_URL.replace("+asyncpg", "+psycopg"))
    try:
        with engine.begin() as db:
            year_id = db.scalar(
                text(
                    "INSERT INTO academic_years (label, status) "
                    "VALUES ('Synthetic prep migration', 'setup') RETURNING id"
                )
            )
            if prep_table == "school_classes":
                db.execute(
                    text(
                        "INSERT INTO school_classes (year_id, grade_level, section) "
                        "VALUES (:year, 0, 'Bulut')"
                    ),
                    {"year": year_id},
                )
            else:
                semester_id = db.scalar(
                    text(
                        "INSERT INTO semesters (year_id, number, status) "
                        "VALUES (:year, 1, 'locked') RETURNING id"
                    ),
                    {"year": year_id},
                )
                db.execute(
                    text(
                        "INSERT INTO column_definitions "
                        "(semester_id, grade_level, subject, value_type, owner_role, labels, "
                        "position, counts_in_average, is_active) "
                        "VALUES (:semester, 0, 'english', 'scale3', 'main', '{}', 1, FALSE, TRUE)"
                    ),
                    {"semester": semester_id},
                )
        with pytest.raises(IntegrityError):
            command.downgrade(cfg, "82a91f4c6d30")
        with engine.begin() as db:
            # One transaction covers every downgrade step, so nothing was applied.
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "9b3e5d7f1c20"
            # Both names are test-owned constants, never workbook/user input.
            assert db.scalar(text(f"SELECT count(*) FROM {prep_table} WHERE grade_level = 0")) == 1
            db.execute(text(f"DELETE FROM {prep_table} WHERE grade_level = 0"))
        command.downgrade(cfg, "82a91f4c6d30")
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")


def test_upgrade_preserves_existing_user_and_adds_login_identity() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "a4f93b7c2d10")
    engine = create_engine(TEST_URL.replace("+asyncpg", "+psycopg"))
    try:
        with engine.begin() as db:
            user_id = db.scalar(
                text("""
                INSERT INTO users
                    (email, full_name, is_admin, is_coordinator, is_active, teaching_field)
                VALUES
                    ('demo@school.example', 'Synthetic Demo Admin', TRUE, FALSE, TRUE, 'english')
                RETURNING id
            """)
            )
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")
        with engine.connect() as db:
            user = db.execute(
                text("""
                SELECT id, email, google_subject, teaching_stage, is_admin, is_active FROM users
            """)
            ).one()
            assert tuple(user) == (user_id, "demo@school.example", None, "middle", True, True)
            indexes = inspect(db).get_indexes("users")
            assert any(
                index["unique"] and index["column_names"] == ["google_subject"] for index in indexes
            )
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")


def test_stage_scoped_numbers_backfill_derive_stage_and_guard_downgrade() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "3c7f1a9d2b64")
    engine = create_engine(TEST_URL.replace("+asyncpg", "+psycopg"))

    def enroll(db: Connection, year: int, student: int, class_id: int, number: int) -> None:
        db.execute(
            text(
                "INSERT INTO enrollments (student_id, year_id, class_id, school_number) "
                "VALUES (:student, :year, :class, :number)"
            ),
            {"student": student, "year": year, "class": class_id, "number": number},
        )

    def stage_of(db: Connection, student: int) -> str | None:
        return db.scalar(
            text("SELECT stage FROM enrollments WHERE student_id = :student"),
            {"student": student},
        )

    try:
        with engine.begin() as db:
            year_id = db.scalar(
                text(
                    "INSERT INTO academic_years (label, status) "
                    "VALUES ('Synthetic stage migration', 'setup') RETURNING id"
                )
            )
            primary, middle = (
                db.scalar(
                    text(
                        "INSERT INTO school_classes (year_id, grade_level, section) "
                        "VALUES (:year, :grade, 'A') RETURNING id"
                    ),
                    {"year": year_id, "grade": grade},
                )
                for grade in (4, 5)
            )
            students = [
                db.scalar(
                    text(
                        "INSERT INTO students (full_name, search_name) "
                        "VALUES (:name, :name) RETURNING id"
                    ),
                    {"name": f"synthetic stage pupil {index}"},
                )
                for index in range(4)
            ]
            enroll(db, year_id, students[0], primary, 7)
            enroll(db, year_id, students[1], middle, 8)
        command.upgrade(cfg, "head")

        with engine.begin() as db:
            assert stage_of(db, students[0]) == "primary"
            assert stage_of(db, students[1]) == "middle"
            # A primary pupil may reuse a middle-school number, and an
            # explicit stage is replaced by the one derived from the class.
            db.execute(
                text(
                    "INSERT INTO enrollments (student_id, year_id, class_id, school_number, stage) "
                    "VALUES (:student, :year, :class, 8, 'middle')"
                ),
                {"student": students[2], "year": year_id, "class": primary},
            )
            assert stage_of(db, students[2]) == "primary"
            db.execute(
                text("UPDATE enrollments SET stage = 'middle' WHERE student_id = :student"),
                {"student": students[0]},
            )
            assert stage_of(db, students[0]) == "primary"
        with pytest.raises(IntegrityError), engine.begin() as db:
            enroll(db, year_id, students[3], middle, 8)
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(
                text("UPDATE enrollments SET class_id = :middle WHERE student_id = :student"),
                {"middle": middle, "student": students[2]},
            )
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(
                text("UPDATE school_classes SET grade_level = 6 WHERE id = :class"),
                {"class": primary},
            )
        with engine.begin() as db:
            assert (
                db.scalar(
                    text("SELECT grade_level FROM school_classes WHERE id = :class"),
                    {"class": primary},
                )
                == 4
            )
            assert stage_of(db, students[2]) == "primary"
            # Free number 8 in the middle school, then the whole class crosses
            # the boundary and back with its pupils.
            db.execute(
                text("UPDATE enrollments SET school_number = 9 WHERE student_id = :student"),
                {"student": students[1]},
            )
            db.execute(
                text("UPDATE school_classes SET grade_level = 6 WHERE id = :class"),
                {"class": primary},
            )
            assert stage_of(db, students[0]) == stage_of(db, students[2]) == "middle"
            db.execute(
                text("UPDATE school_classes SET grade_level = 3 WHERE id = :class"),
                {"class": primary},
            )
            assert stage_of(db, students[0]) == stage_of(db, students[2]) == "primary"
            db.execute(
                text("UPDATE enrollments SET school_number = 8 WHERE student_id = :student"),
                {"student": students[1]},
            )

        with pytest.raises(IntegrityError):
            command.downgrade(cfg, "3c7f1a9d2b64")
        with engine.begin() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "9b3e5d7f1c20"
            assert db.scalar(text("SELECT count(*) FROM enrollments")) == 3
            db.execute(
                text("DELETE FROM enrollments WHERE student_id = :student"),
                {"student": students[2]},
            )
        command.downgrade(cfg, "3c7f1a9d2b64")
        with engine.connect() as db:
            constraints = {
                item["name"] for item in inspect(db).get_unique_constraints("enrollments")
            }
            assert "uq_enrollments_year_id_school_number" in constraints
            assert "uq_enrollments_year_id_stage_school_number" not in constraints
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
