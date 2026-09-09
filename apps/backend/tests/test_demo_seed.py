import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from flrc import cli
from flrc.config import settings
from flrc.db import models as m

TEST_URL = "postgresql+psycopg://flrc:flrc@localhost:5432/flrc_test"
runner = CliRunner()


@pytest.fixture
def demo_db(monkeypatch):
    engine = create_engine(TEST_URL)
    monkeypatch.setattr(cli, "sync_engine", lambda: engine)
    monkeypatch.setattr(settings, "env", "demo")
    monkeypatch.setattr(settings, "allowed_google_domain", "school.example")
    yield engine
    engine.dispose()


def add_admin(engine, **overrides) -> int:
    values = {
        "email": "presenter@school.example",
        "full_name": "Synthetic Presenter",
        "google_subject": "synthetic-google-subject",
        "is_admin": True,
        "is_coordinator": True,
        "is_active": True,
        "teaching_field": "english",
        "teaching_stage": "middle",
    }
    with Session(engine) as db:
        admin = m.User(**(values | overrides))
        db.add(admin)
        db.commit()
        return admin.id


def test_demo_populates_full_school_and_keeps_login_and_edits(demo_db) -> None:
    admin_id = add_admin(demo_db)
    with demo_db.connect() as db:
        original_admin = db.execute(select(m.User)).one()

    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0, result.output
    assert "seeded: 4 years, 208 classes" in result.output
    with Session(demo_db) as db:
        years = list(db.scalars(select(m.AcademicYear).order_by(m.AcademicYear.label)))
        assert [year.label for year in years] == list(cli.ACADEMIC_YEARS)
        assert [year.status for year in years] == ["archived"] * 3 + ["active"]
        assert db.scalar(select(func.count()).select_from(m.User)) == 28
        assert db.scalar(select(func.count()).select_from(m.Student)) == 1804
        for year in years:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(m.SchoolClass)
                    .where(m.SchoolClass.year_id == year.id)
                )
                == 52
            )
            numbers = list(
                db.scalars(
                    select(m.Enrollment.school_number).where(m.Enrollment.year_id == year.id)
                )
            )
            assert sorted(numbers) == list(range(1, 1145))
        open_term = db.scalars(select(m.Semester).where(m.Semester.status == "open")).one()
        assert (open_term.year_id, open_term.number) == (years[-1].id, 1)
        assignments = db.execute(
            select(m.SchoolClass.grade_level, m.TeachingAssignment.role)
            .join(m.TeachingAssignment)
            .where(m.TeachingAssignment.user_id == admin_id)
        ).all()
        assert assignments
        assert all(grade >= 5 and role in {"main", "skills"} for grade, role in assignments)
        value_count = db.scalar(select(func.count()).select_from(m.GradeValue))
        assert value_count > 100_000
        comment = db.scalars(
            select(m.GradeValue).where(m.GradeValue.text_value.is_not(None)).limit(1)
        ).one()
        comment.text_value = "Synthetic demo edit"
        comment_id = comment.id
        db.commit()

    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0, result.output
    assert "academic data already exists" in result.output
    with demo_db.connect() as db:
        assert db.execute(select(m.User).where(m.User.id == admin_id)).one() == original_admin
        assert db.scalar(select(func.count()).select_from(m.GradeValue)) == value_count
        assert db.scalar(select(m.GradeValue.text_value).where(m.GradeValue.id == comment_id)) == (
            "Synthetic demo edit"
        )


@pytest.mark.parametrize("environment", ["school", "dev", "test"])
def test_demo_mode_rejects_other_environments(monkeypatch, environment) -> None:
    monkeypatch.setattr(settings, "env", environment)
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code != 0
    assert "requires ENV=demo" in result.output


@pytest.mark.parametrize("existing", ["year", "student"])
def test_demo_never_overwrites_existing_academic_data(demo_db, existing) -> None:
    add_admin(demo_db)
    with Session(demo_db) as db:
        db.add(
            m.AcademicYear(label="Existing setup", status="setup")
            if existing == "year"
            else m.Student(full_name="Existing synthetic student", search_name="existing")
        )
        db.commit()
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0
    assert "academic data already exists" in result.output
    with Session(demo_db) as db:
        assert db.scalar(select(func.count()).select_from(m.User)) == 1
        assert db.scalar(select(func.count()).select_from(m.SchoolClass)) == 0


@pytest.mark.parametrize(
    "admin_overrides",
    [{"email": "presenter@different.example"}, {"teaching_stage": "primary"}],
)
def test_demo_does_not_promote_an_unsuitable_admin(demo_db, admin_overrides) -> None:
    add_admin(demo_db, **admin_overrides)
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0
    assert "demo seed skipped" in result.output
    with Session(demo_db) as db:
        assert db.scalar(select(func.count()).select_from(m.AcademicYear)) == 0
        assert db.scalar(select(func.count()).select_from(m.User)) == 1


@pytest.mark.parametrize("existing_inactive_admin", [False, True])
def test_demo_without_an_active_admin_creates_a_synthetic_one(
    demo_db, existing_inactive_admin
) -> None:
    if existing_inactive_admin:
        add_admin(demo_db, is_active=False)
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0, result.output
    assert "created the synthetic seed administrator" in result.output
    assert "seeded: 4 years" in result.output
    with Session(demo_db) as db:
        seed_admin = db.scalars(
            select(m.User).where(m.User.is_admin.is_(True), m.User.is_active.is_(True))
        ).one()
        assert seed_admin.email == "admin@school.example"
        assert seed_admin.google_subject is None
        assert db.scalar(select(func.count()).select_from(m.User)) == 28 + int(
            existing_inactive_admin
        )


def test_demo_does_not_choose_between_admins(demo_db) -> None:
    add_admin(demo_db)
    add_admin(demo_db, email="another@school.example", google_subject=None)
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code == 0
    assert "exactly one existing active admin" in result.output
    with Session(demo_db) as db:
        assert db.scalar(select(func.count()).select_from(m.AcademicYear)) == 0


def test_failed_demo_seed_rolls_back_all_insertions(demo_db, monkeypatch) -> None:
    admin_id = add_admin(demo_db)

    def fail_value(*args):
        raise RuntimeError("synthetic seed failure")

    monkeypatch.setattr(cli, "_student_value", fail_value)
    result = runner.invoke(cli.app, ["seed", "--demo"])
    assert result.exit_code != 0
    assert str(result.exception) == "synthetic seed failure"
    with Session(demo_db) as db:
        assert db.scalar(select(func.count()).select_from(m.AcademicYear)) == 0
        assert db.scalar(select(func.count()).select_from(m.Student)) == 0
        assert list(db.scalars(select(m.User.id))) == [admin_id]
