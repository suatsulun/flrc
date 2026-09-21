import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
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
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "3c7f1a9d2b64"
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
