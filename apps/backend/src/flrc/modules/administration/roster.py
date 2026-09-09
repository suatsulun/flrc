from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Student,
    StudentLanguage,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.programme import L2_START_GRADE
from flrc.modules.administration.names import search_key
from flrc.modules.administration.roster_service import move_students, remove_student
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin-roster"])


class RosterStudentOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    language: str | None


class RosterStudentCreate(BaseModel):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None


class RosterStudentPatch(BaseModel):
    school_number: int | None = Field(default=None, gt=0)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None


class RosterStudentRemoveResult(BaseModel):
    student_id: int
    removed: bool


@router.delete("/classes/{class_id}/roster/{student_id}")
async def remove_admin_roster_student(
    class_id: int,
    student_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterStudentRemoveResult:
    await remove_student(db, class_id=class_id, student_id=student_id, actor_id=actor.id)
    return RosterStudentRemoveResult(student_id=student_id, removed=True)


class MoveBody(BaseModel):
    student_ids: list[int] = Field(min_length=1, max_length=200)
    target_class_id: int
    allow_grade_change: bool = False


class LanguageBody(BaseModel):
    student_ids: list[int] = Field(min_length=1, max_length=200)
    language: Literal["german", "french"] | None


async def _ensure_year_writable(db: AsyncSession, year_id: int) -> None:
    year = await db.get(AcademicYear, year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    if year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})


@router.get("/classes/{class_id}/roster")
async def get_admin_roster(
    class_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[RosterStudentOut]:
    del actor
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    rows = (
        await db.execute(
            select(Student, Enrollment.school_number, StudentLanguage.language)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .outerjoin(
                StudentLanguage,
                (StudentLanguage.student_id == Student.id)
                & (StudentLanguage.year_id == school_class.year_id),
            )
            .where(Enrollment.class_id == class_id)
            .order_by(Enrollment.school_number.asc().nulls_last(), Student.search_name)
        )
    ).all()
    return [
        RosterStudentOut(
            student_id=student.id,
            school_number=school_number,
            full_name=student.full_name,
            language=language,
        )
        for student, school_number, language in rows
    ]


@router.post("/classes/{class_id}/roster", status_code=201)
async def add_admin_roster_student(
    class_id: int,
    body: RosterStudentCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterStudentOut:
    del actor
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    await _ensure_year_writable(db, school_class.year_id)
    if body.language and school_class.grade_level < L2_START_GRADE:
        raise HTTPException(422, {"code": "language_grade_too_low"})
    duplicate = await db.scalar(
        select(Enrollment.id).where(
            Enrollment.year_id == school_class.year_id,
            Enrollment.school_number == body.school_number,
        )
    )
    if duplicate is not None:
        raise HTTPException(409, {"code": "duplicate_school_number"})
    full_name = body.full_name.strip()
    student = Student(full_name=full_name, search_name=search_key(full_name))
    db.add(student)
    await db.flush()
    db.add(
        Enrollment(
            student_id=student.id,
            year_id=school_class.year_id,
            class_id=school_class.id,
            school_number=body.school_number,
        )
    )
    if body.language:
        db.add(
            StudentLanguage(
                student_id=student.id,
                year_id=school_class.year_id,
                language=body.language,
            )
        )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
    return RosterStudentOut(
        student_id=student.id,
        school_number=body.school_number,
        full_name=student.full_name,
        language=body.language,
    )


@router.patch("/classes/{class_id}/roster/{student_id}")
async def patch_admin_roster_student(
    class_id: int,
    student_id: int,
    body: RosterStudentPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterStudentOut:
    del actor
    row = (
        await db.execute(
            select(Enrollment, Student, SchoolClass)
            .join(Student, Student.id == Enrollment.student_id)
            .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .where(Enrollment.class_id == class_id, Enrollment.student_id == student_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, {"code": "unknown_enrollment"})
    enrollment, student, school_class = row
    year = await db.get(AcademicYear, school_class.year_id)
    await _ensure_year_writable(db, school_class.year_id)
    if "school_number" in body.model_fields_set:
        if body.school_number is None and year and year.status != "setup":
            raise HTTPException(409, {"code": "student_number_required"})
        enrollment.school_number = body.school_number
    if body.full_name is not None:
        student.full_name = body.full_name.strip()
        student.search_name = search_key(student.full_name)
    if "language" in body.model_fields_set:
        if body.language and school_class.grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        existing = await db.scalar(
            select(StudentLanguage).where(
                StudentLanguage.student_id == student_id,
                StudentLanguage.year_id == school_class.year_id,
            )
        )
        if body.language is None and existing is not None:
            await db.delete(existing)
        elif body.language is not None:
            await db.execute(
                pg_insert(StudentLanguage)
                .values(
                    student_id=student_id,
                    year_id=school_class.year_id,
                    language=body.language,
                )
                .on_conflict_do_update(
                    index_elements=["student_id", "year_id"],
                    set_={"language": body.language},
                )
            )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
    language = await db.scalar(
        select(StudentLanguage.language).where(
            StudentLanguage.student_id == student_id,
            StudentLanguage.year_id == school_class.year_id,
        )
    )
    return RosterStudentOut(
        student_id=student.id,
        school_number=enrollment.school_number,
        full_name=student.full_name,
        language=language,
    )


@router.post("/roster/move")
async def move_admin_roster(
    body: MoveBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    del actor
    target = await db.get(SchoolClass, body.target_class_id)
    if target is None:
        raise HTTPException(404, {"code": "unknown_class"})
    await _ensure_year_writable(db, target.year_id)
    try:
        changed, unchanged = await move_students(
            db,
            student_ids=body.student_ids,
            target_class=target,
            allow_grade_change=body.allow_grade_change,
        )
    except ValueError as exc:
        raise HTTPException(409, {"code": str(exc)}) from exc
    await db.commit()
    return {"changed": changed, "unchanged": unchanged}


@router.put("/years/{year_id}/student-language")
async def set_student_language(
    year_id: int,
    body: LanguageBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    del actor
    await _ensure_year_writable(db, year_id)
    enrollments = list(
        (
            await db.execute(
                select(Enrollment, SchoolClass)
                .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
                .where(
                    Enrollment.year_id == year_id,
                    Enrollment.student_id.in_(body.student_ids),
                )
            )
        ).all()
    )
    if len(enrollments) != len(set(body.student_ids)):
        raise HTTPException(422, {"code": "student_not_enrolled_in_year"})
    if body.language and any(item[1].grade_level < L2_START_GRADE for item in enrollments):
        raise HTTPException(422, {"code": "language_grade_too_low"})
    if body.language is None:
        existing = list(
            await db.scalars(
                select(StudentLanguage).where(
                    StudentLanguage.year_id == year_id,
                    StudentLanguage.student_id.in_(body.student_ids),
                )
            )
        )
        for item in existing:
            await db.delete(item)
    else:
        for student_id in body.student_ids:
            await db.execute(
                pg_insert(StudentLanguage)
                .values(student_id=student_id, year_id=year_id, language=body.language)
                .on_conflict_do_update(
                    index_elements=["student_id", "year_id"],
                    set_={"language": body.language},
                )
            )
    await db.commit()
    return {"changed": len(set(body.student_ids))}
