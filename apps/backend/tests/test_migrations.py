import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

TEST_URL = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test"


def test_migrations_apply_from_zero() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
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
