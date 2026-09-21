from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    ColumnDefinition,
    Enrollment,
    SchoolClass,
    Semester,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.auth.dependencies import (
    current_user,
    require_admin,
    require_coordinator_or_admin,
    writable_year,
)
from flrc.modules.grades.permissions import SUBJECT_ROLES

router = APIRouter(tags=["assignments"])

Role = Literal["main", "skills", "german", "french"]
Subject = Literal["english", "german", "french"]


class ClassOut(BaseModel):
    id: int
    grade_level: int
    section: str
    name: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool
    teaching_field: str
    teaching_stage: str | None


class AssignmentSlotOut(BaseModel):
    role: str
    user_id: int | None
    user_name: str | None


class AssignBody(BaseModel):
    user_id: int


class MyAssignmentOut(BaseModel):
    class_id: int
    class_name: str
    role: str
    subject: str


class ClassSubjectOut(BaseModel):
    subject: Subject
    student_count: int
    column_count: int
    owner_roles: list[str]
    my_roles: list[str]
    can_write: bool


class ClassCatalogOut(BaseModel):
    id: int
    name: str
    grade_level: int
    section: str
    subjects: list[ClassSubjectOut]


class AcademicSemesterOut(BaseModel):
    id: int
    number: int
    status: str


class AcademicYearOut(BaseModel):
    id: int
    label: str
    status: str
    semesters: list[AcademicSemesterOut]


@router.get("/academic-years")
async def list_academic_years(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[AcademicYearOut]:
    statement = select(AcademicYear).order_by(AcademicYear.label.desc())
    if not (user.is_admin or user.is_coordinator):
        # A teacher sees the years they actually teach in, plus the active one.
        # Keeping the active year visible costs nothing — its label is on every
        # screen already — and without it a teacher who has not been assigned
        # yet lands on a page with no year to render at all.
        assigned_years = (
            select(SchoolClass.year_id)
            .join(TeachingAssignment, TeachingAssignment.class_id == SchoolClass.id)
            .where(TeachingAssignment.user_id == user.id)
        )
        statement = statement.where(
            or_(
                AcademicYear.status == "active",
                AcademicYear.id.in_(assigned_years),
            )
        )
    years = list(await db.scalars(statement))
    if not years:
        return []
    terms = list(
        await db.scalars(
            select(Semester)
            .where(Semester.year_id.in_([item.id for item in years]))
            .order_by(Semester.year_id, Semester.number)
        )
    )
    by_year: dict[int, list[Semester]] = {}
    for term in terms:
        by_year.setdefault(term.year_id, []).append(term)
    return [
        AcademicYearOut(
            id=year.id,
            label=year.label,
            status=year.status,
            semesters=[
                AcademicSemesterOut(id=term.id, number=term.number, status=term.status)
                for term in by_year.get(year.id, [])
            ],
        )
        for year in years
    ]


@router.get("/class-catalog")
async def list_class_catalog(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    year_id: int | None = None,
    semester: int | None = None,
) -> list[ClassCatalogOut]:
    """Return a year's class/subject tabs, including read-only archives."""
    if year_id is not None:
        year = await db.get(AcademicYear, year_id)
    else:
        year = (
            await db.execute(
                select(AcademicYear)
                .order_by(
                    (AcademicYear.status == "active").desc(),
                    AcademicYear.label.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if year is None:
        return []
    elevated = user.is_admin or user.is_coordinator
    if not elevated:
        assigned = await db.scalar(
            select(TeachingAssignment.id)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(
                TeachingAssignment.user_id == user.id,
                SchoolClass.year_id == year.id,
            )
            .limit(1)
        )
        if assigned is None:
            # An empty catalog rather than a 403: the rows below are already
            # filtered to this teacher's own classes, so a distinct error would
            # only turn the endpoint into an oracle for which year ids exist.
            return []

    semesters = list(
        await db.scalars(
            select(Semester).where(Semester.year_id == year.id).order_by(Semester.number)
        )
    )
    if not semesters:
        return []
    selected_term = (
        next((item for item in semesters if item.number == semester), None)
        if semester is not None
        else next((item for item in semesters if item.status == "open"), semesters[-1])
    )
    if selected_term is None:
        raise HTTPException(404, {"code": "unknown_semester"})

    classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == year.id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    if not classes:
        return []
    class_ids = [item.id for item in classes]

    column_rows = (
        await db.execute(
            select(
                ColumnDefinition.grade_level,
                ColumnDefinition.subject,
                ColumnDefinition.owner_role,
                func.count(ColumnDefinition.id).label("column_count"),
            )
            .where(
                ColumnDefinition.semester_id == selected_term.id,
                ColumnDefinition.is_active.is_(True),
            )
            .group_by(
                ColumnDefinition.grade_level,
                ColumnDefinition.subject,
                ColumnDefinition.owner_role,
            )
        )
    ).all()
    column_counts: dict[tuple[int, str], int] = {}
    owner_roles: dict[tuple[int, str], set[str]] = {}
    for column_row in column_rows:
        key = (column_row.grade_level, column_row.subject)
        column_counts[key] = column_counts.get(key, 0) + column_row.column_count
        owner_roles.setdefault(key, set()).add(column_row.owner_role)

    assignment_rows = (
        await db.execute(
            select(TeachingAssignment.class_id, TeachingAssignment.role).where(
                TeachingAssignment.class_id.in_(class_ids),
                TeachingAssignment.user_id == user.id,
            )
        )
    ).all()
    assigned_roles: dict[int, set[str]] = {}
    for assignment_row in assignment_rows:
        assigned_roles.setdefault(assignment_row.class_id, set()).add(assignment_row.role)

    english_counts = {
        count_row.class_id: count_row.student_count
        for count_row in (
            await db.execute(
                select(
                    Enrollment.class_id, func.count(Enrollment.student_id).label("student_count")
                )
                .where(Enrollment.class_id.in_(class_ids))
                .group_by(Enrollment.class_id)
            )
        ).all()
    }
    language_counts = {
        (language_row.class_id, language_row.language): language_row.student_count
        for language_row in (
            await db.execute(
                select(
                    Enrollment.class_id,
                    StudentLanguage.language,
                    func.count(Enrollment.student_id).label("student_count"),
                )
                .join(StudentLanguage, StudentLanguage.student_id == Enrollment.student_id)
                .where(
                    Enrollment.class_id.in_(class_ids),
                    StudentLanguage.year_id == year.id,
                )
                .group_by(Enrollment.class_id, StudentLanguage.language)
            )
        ).all()
    }

    subject_order: tuple[Subject, ...] = ("english", "german", "french")
    catalog: list[ClassCatalogOut] = []
    for school_class in classes:
        class_roles = assigned_roles.get(school_class.id, set())
        subjects: list[ClassSubjectOut] = []
        for subject in subject_order:
            key = (school_class.grade_level, subject)
            if key not in column_counts:
                continue
            relevant_roles = sorted(owner_roles[key])
            my_roles = sorted(class_roles.intersection(relevant_roles))
            if not elevated and not class_roles.intersection(SUBJECT_ROLES[subject]):
                continue
            subjects.append(
                ClassSubjectOut(
                    subject=subject,
                    student_count=(
                        english_counts.get(school_class.id, 0)
                        if subject == "english"
                        else language_counts.get((school_class.id, subject), 0)
                    ),
                    column_count=column_counts[key],
                    owner_roles=relevant_roles,
                    my_roles=my_roles,
                    can_write=(
                        bool(my_roles)
                        and year.status == "active"
                        and selected_term.status == "open"
                    ),
                )
            )
        if not subjects and not elevated:
            continue
        catalog.append(
            ClassCatalogOut(
                id=school_class.id,
                name=class_label(school_class.grade_level, school_class.section),
                grade_level=school_class.grade_level,
                section=school_class.section,
                subjects=subjects,
            )
        )
    return catalog


@router.get("/my-assignments")
async def list_my_assignments(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[MyAssignmentOut]:
    result = await db.execute(
        select(TeachingAssignment.role, SchoolClass)
        .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
        .join(AcademicYear, AcademicYear.id == SchoolClass.year_id)
        .where(
            TeachingAssignment.user_id == user.id,
            AcademicYear.status == "active",
        )
        .order_by(SchoolClass.grade_level, SchoolClass.section, TeachingAssignment.role)
    )
    return [
        MyAssignmentOut(
            class_id=school_class.id,
            class_name=class_label(school_class.grade_level, school_class.section),
            role=role,
            subject=role if role in ("german", "french") else "english",
        )
        for role, school_class in result.all()
    ]


@router.get("/classes")
async def list_classes(
    _: Annotated[User, Depends(require_coordinator_or_admin)],
    year: Annotated[AcademicYear, Depends(writable_year)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ClassOut]:
    result = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.year_id == year.id)
        .order_by(SchoolClass.grade_level, SchoolClass.section)
    )
    return [
        ClassOut(
            id=c.id,
            grade_level=c.grade_level,
            section=c.section,
            name=class_label(c.grade_level, c.section),
        )
        for c in result.scalars()
    ]


@router.get("/users")
async def list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.full_name))
    return [UserOut.model_validate(u, from_attributes=True) for u in result.scalars()]


@router.get("/classes/{class_id}/assignments")
async def get_assignments(
    class_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[AssignmentSlotOut]:
    result = await db.execute(
        select(TeachingAssignment.role, User.id, User.full_name)
        .join(User, User.id == TeachingAssignment.user_id)
        .where(TeachingAssignment.class_id == class_id)
    )
    found = {r.role: r for r in result.all()}
    return [
        AssignmentSlotOut(
            role=role,
            user_id=found[role].id if role in found else None,
            user_name=found[role].full_name if role in found else None,
        )
        for role in ("main", "skills", "german", "french")
    ]


@router.put("/classes/{class_id}/assignments/{role}")
async def upsert_assignment(
    class_id: int,
    role: Role,
    body: AssignBody,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    teacher = await db.get(User, body.user_id)
    if teacher is None or not teacher.is_active:
        raise HTTPException(422, {"code": "unknown_user"})
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await db.get(AcademicYear, school_class.year_id)
    if year is None or year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    expected_field = "english" if role in ("main", "skills") else role
    if teacher.teaching_field != expected_field:
        raise HTTPException(422, {"code": "teacher_field_mismatch"})
    if expected_field == "english":
        expected_stage = "primary" if school_class.grade_level <= 4 else "middle"
        if teacher.teaching_stage != expected_stage:
            raise HTTPException(422, {"code": "teacher_stage_mismatch"})
    stmt = (
        pg_insert(TeachingAssignment)
        .values(class_id=class_id, role=role, user_id=body.user_id)
        .on_conflict_do_update(index_elements=["class_id", "role"], set_={"user_id": body.user_id})
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}
