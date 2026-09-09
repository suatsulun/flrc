import os
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from flrc.db import models as m
from flrc.db.models import User
from flrc.db.session import get_session
from flrc.main import create_app
from flrc.modules.auth.dependencies import current_user

TEST_URL = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test"
TEST_URL_SYNC = TEST_URL.replace("+asyncpg", "+psycopg")

WIPE_ORDER = (
    m.JobRun,
    m.AuditEntry,
    m.SaveBatch,
    m.OverrideGrant,
    m.GradeValue,
    m.ColumnDefinition,
    m.TeachingAssignment,
    m.StudentLanguage,
    m.Enrollment,
    m.Student,
    m.SchoolClass,
    m.Semester,
    m.AcademicYear,
    m.DemoVisitor,
    m.User,
)

test_engine = create_async_engine(TEST_URL, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

USERS = {
    "teacher": User(
        id=1, email="t@x", full_name="T", is_admin=False, is_coordinator=False, is_active=True
    ),
    "admin": User(
        id=2, email="a@x", full_name="A", is_admin=True, is_coordinator=False, is_active=True
    ),
    "coordinator": User(
        id=3, email="c@x", full_name="C", is_admin=False, is_coordinator=True, is_active=True
    ),
}


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def _clean(_migrated: None) -> None:
    del _migrated
    with Session(create_engine(TEST_URL_SYNC)) as db:
        for table in WIPE_ORDER:
            db.execute(delete(table))
        db.commit()


async def _test_session() -> AsyncIterator[AsyncSession]:
    async with TestSession() as session:
        yield session


@pytest.fixture
def client_as():
    def make(role: str | None) -> AsyncClient:
        app = create_app()
        if role is not None:
            user = USERS[role]
            app.dependency_overrides[current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return make


@pytest.fixture
def api():
    def make(user: m.User | None) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_session] = _test_session
        if user is not None:
            app.dependency_overrides[current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return make


@pytest.fixture
async def world():
    async with TestSession() as db:
        year = m.AcademicYear(label="Synthetic year", status="active")
        db.add(year)
        await db.flush()
        semester = m.Semester(year_id=year.id, number=1, status="open")
        school_class = m.SchoolClass(year_id=year.id, grade_level=5, section="A")
        db.add_all([semester, school_class])
        await db.flush()

        main_teacher = m.User(
            email="main@example.test", full_name="Main Teacher", teaching_stage="middle"
        )
        skills_teacher = m.User(
            email="skills@example.test", full_name="Skills Teacher", teaching_stage="middle"
        )
        admin = m.User(
            email="admin@example.test",
            full_name="Synthetic Admin",
            is_admin=True,
            teaching_stage="middle",
        )
        db.add_all([main_teacher, skills_teacher, admin])
        await db.flush()
        db.add_all(
            [
                m.TeachingAssignment(
                    class_id=school_class.id, role="main", user_id=main_teacher.id
                ),
                m.TeachingAssignment(
                    class_id=school_class.id, role="skills", user_id=skills_teacher.id
                ),
            ]
        )

        main_column = m.ColumnDefinition(
            semester_id=semester.id,
            grade_level=5,
            subject="english",
            value_type="score",
            owner_role="main",
            labels={"tr": "Main score", "en": "Main score", "de": "", "fr": ""},
            position=1,
        )
        skills_column = m.ColumnDefinition(
            semester_id=semester.id,
            grade_level=5,
            subject="english",
            value_type="score",
            owner_role="skills",
            labels={"tr": "Skills score", "en": "Skills score", "de": "", "fr": ""},
            position=2,
        )
        student_one = m.Student(
            full_name="Synthetic Student One",
            search_name="synthetic student one",
        )
        student_two = m.Student(
            full_name="Synthetic Student Two",
            search_name="synthetic student two",
        )
        db.add_all([main_column, skills_column, student_one, student_two])
        await db.flush()
        db.add_all(
            [
                m.Enrollment(
                    student_id=student_one.id,
                    class_id=school_class.id,
                    year_id=year.id,
                    school_number=51001,
                ),
                m.Enrollment(
                    student_id=student_two.id,
                    class_id=school_class.id,
                    year_id=year.id,
                    school_number=51002,
                ),
            ]
        )
        await db.commit()
        return SimpleNamespace(
            cls=school_class.id,
            year=year.id,
            semester=semester.id,
            main=main_teacher,
            skills=skills_teacher,
            admin=admin,
            main_column=main_column.id,
            skills_column=skills_column.id,
            student_one=student_one.id,
            student_two=student_two.id,
        )


def cell(
    student_id: int,
    column_id: int,
    value: int | str | None,
    expected: int = 0,
) -> dict[str, int | str | None]:
    return {
        "student_id": student_id,
        "column_id": column_id,
        "value": value,
        "expected_version": expected,
    }


async def save_grid(
    api,
    user: m.User,
    class_id: int,
    cells: list[dict[str, int | str | None]],
    *,
    force: bool = False,
):
    async with api(user) as client:
        return await client.post(
            f"/api/classes/{class_id}/grid/save",
            json={"subject": "english", "force": force, "cells": cells},
        )
