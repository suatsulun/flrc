import base64
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import AcademicYear, Enrollment, SchoolClass, Student, User
from flrc.db.session import get_session
from flrc.modules.academics.programme import stage_for_grade
from flrc.modules.administration.names import search_key
from flrc.modules.administration.roster_service import (
    is_duplicate_school_number,
    school_number_taken,
)
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin/students", tags=["admin-students"])


class StudentOut(BaseModel):
    id: int
    school_number: int | None
    full_name: str
    year_id: int
    class_id: int


class StudentPage(BaseModel):
    items: list[StudentOut]
    next_cursor: str | None


class StudentCreate(BaseModel):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    year_id: int
    class_id: int


class StudentPatch(BaseModel):
    school_number: int | None = Field(default=None, gt=0)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)


def encode_cursor(name: str, student_id: int) -> str:
    raw = json.dumps([name, student_id], ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[str, int]:
    try:
        padded = token + "=" * (-len(token) % 4)
        name, student_id = json.loads(base64.urlsafe_b64decode(padded))
        return str(name), int(student_id)
    except Exception as exc:
        raise HTTPException(400, {"code": "bad_cursor"}) from exc


@router.get("")
async def list_students(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    q: str = "",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    year_id: int | None = None,
) -> StudentPage:
    del user
    if year_id is None:
        year = await db.scalar(
            select(AcademicYear)
            .order_by(
                (AcademicYear.status == "active").desc(),
                AcademicYear.label.desc(),
            )
            .limit(1)
        )
        if year is None:
            return StudentPage(items=[], next_cursor=None)
        year_id = year.id
    statement = (
        select(Student, Enrollment)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.year_id == year_id)
    )
    needle = search_key(q)
    if needle:
        predicates = [Student.search_name.contains(needle)]
        if needle.isdigit():
            predicates.append(Enrollment.school_number == int(needle))
        statement = statement.where(or_(*predicates))
    if cursor:
        last_name, last_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                Student.search_name > last_name,
                and_(Student.search_name == last_name, Student.id > last_id),
            )
        )
    rows = list(
        (
            await db.execute(statement.order_by(Student.search_name, Student.id).limit(limit + 1))
        ).all()
    )
    visible = rows[:limit]
    return StudentPage(
        items=[
            StudentOut(
                id=student.id,
                school_number=enrollment.school_number,
                full_name=student.full_name,
                year_id=enrollment.year_id,
                class_id=enrollment.class_id,
            )
            for student, enrollment in visible
        ],
        next_cursor=(
            encode_cursor(visible[-1][0].search_name, visible[-1][0].id)
            if len(rows) > limit and visible
            else None
        ),
    )


async def _commit_numbered(db: AsyncSession) -> None:
    """Commit, reporting a concurrent per-stage number clash as a conflict."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
        raise


@router.post("", status_code=201)
async def create_student(
    body: StudentCreate,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StudentOut:
    del user
    school_class = await db.get(SchoolClass, body.class_id)
    if school_class is None or school_class.year_id != body.year_id:
        raise HTTPException(422, {"code": "invalid_class"})
    year = await db.get(AcademicYear, body.year_id)
    if year is None or year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    if await school_number_taken(
        db,
        year_id=body.year_id,
        stage=stage_for_grade(school_class.grade_level),
        school_number=body.school_number,
    ):
        raise HTTPException(409, {"code": "duplicate_school_number"})
    full_name = body.full_name.strip()
    student = Student(
        full_name=full_name,
        search_name=search_key(full_name),
    )
    db.add(student)
    await db.flush()
    db.add(
        Enrollment(
            student_id=student.id,
            year_id=body.year_id,
            class_id=body.class_id,
            school_number=body.school_number,
        )
    )
    await _commit_numbered(db)
    return StudentOut(
        id=student.id,
        school_number=body.school_number,
        full_name=student.full_name,
        year_id=body.year_id,
        class_id=body.class_id,
    )


@router.patch("/{student_id}")
async def patch_student(
    student_id: int,
    body: StudentPatch,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    year_id: int,
) -> StudentOut:
    del user
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(404, {"code": "unknown_student"})
    enrollment = await db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.year_id == year_id,
        )
    )
    if enrollment is None:
        raise HTTPException(404, {"code": "unknown_enrollment"})
    year = await db.get(AcademicYear, year_id)
    if year is None or year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    if body.school_number is not None and body.school_number != enrollment.school_number:
        if await school_number_taken(
            db,
            year_id=year_id,
            stage=enrollment.stage,
            school_number=body.school_number,
            except_enrollment_id=enrollment.id,
        ):
            raise HTTPException(409, {"code": "duplicate_school_number"})
        enrollment.school_number = body.school_number
    if body.full_name is not None:
        student.full_name = body.full_name.strip()
        student.search_name = search_key(student.full_name)
    await _commit_numbered(db)
    return StudentOut(
        id=student.id,
        school_number=enrollment.school_number,
        full_name=student.full_name,
        year_id=enrollment.year_id,
        class_id=enrollment.class_id,
    )
