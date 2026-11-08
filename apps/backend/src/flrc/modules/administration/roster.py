from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
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
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.programme import L2_START_GRADE, stage_for_grade
from flrc.modules.administration.names import search_key
from flrc.modules.administration.roster_service import (
    assign_student_language,
    is_duplicate_school_number,
    move_students,
    remove_student,
    school_number_taken,
    student_language,
)
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.changes.service import (
    ActionWrite,
    change_list,
    changed_values,
    record_action,
)

router = APIRouter(prefix="/admin", tags=["admin-roster"])


class RosterStudentOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    language: str | None


class RosterStudentWriteOut(RosterStudentOut, ActionWrite):
    pass


class RosterStudentCreate(BaseModel):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None


class RosterStudentPatch(BaseModel):
    school_number: int | None = Field(default=None, gt=0)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None


class RosterStudentRemoveResult(ActionWrite):
    student_id: int
    removed: bool


class RosterMoveOut(ActionWrite):
    changed: int
    unchanged: int


class StudentLanguageOut(ActionWrite):
    changed: int


@router.delete("/classes/{class_id}/roster/{student_id}")
async def remove_admin_roster_student(
    class_id: int,
    student_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterStudentRemoveResult:
    removed = await remove_student(db, class_id=class_id, student_id=student_id)
    student = await db.get(Student, student_id)
    school_class = await db.get(SchoolClass, class_id)
    assert student is not None and school_class is not None
    action = await record_action(
        db,
        actor=actor,
        kind="student.remove",
        params={
            "student": student.full_name,
            "class": class_label(school_class.grade_level, school_class.section),
            "number": removed["school_number"],
        },
        undo=dict(removed),
    )
    await db.commit()
    structlog.get_logger().info(
        "roster_student_removed",
        actor_id=actor.id,
        student_id=student_id,
        class_id=class_id,
        year_id=removed["year_id"],
    )
    return RosterStudentRemoveResult(student_id=student_id, removed=True, action_id=action.id)


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
) -> RosterStudentWriteOut:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    await _ensure_year_writable(db, school_class.year_id)
    if body.language and school_class.grade_level < L2_START_GRADE:
        raise HTTPException(422, {"code": "language_grade_too_low"})
    if await school_number_taken(
        db,
        year_id=school_class.year_id,
        stage=stage_for_grade(school_class.grade_level),
        school_number=body.school_number,
    ):
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
        action = await record_action(
            db,
            actor=actor,
            kind="student.add",
            params={
                "student": student.full_name,
                "class": class_label(school_class.grade_level, school_class.section),
                "number": body.school_number,
            },
            undo={"student_id": student.id, "year_id": school_class.year_id},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
        raise
    return RosterStudentWriteOut(
        student_id=student.id,
        school_number=body.school_number,
        full_name=student.full_name,
        language=body.language,
        action_id=action.id,
    )


@router.patch("/classes/{class_id}/roster/{student_id}")
async def patch_admin_roster_student(
    class_id: int,
    student_id: int,
    body: RosterStudentPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterStudentWriteOut:
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
    before: dict[str, object] = {
        "full_name": student.full_name,
        "school_number": enrollment.school_number,
        "language": await student_language(db, student_id, school_class.year_id),
    }
    if "school_number" in body.model_fields_set:
        if body.school_number is None and year and year.status != "setup":
            raise HTTPException(409, {"code": "student_number_required"})
        if body.school_number is not None and await school_number_taken(
            db,
            year_id=enrollment.year_id,
            stage=stage_for_grade(school_class.grade_level),
            school_number=body.school_number,
            except_enrollment_id=enrollment.id,
        ):
            raise HTTPException(409, {"code": "duplicate_school_number"})
        enrollment.school_number = body.school_number
    if body.full_name is not None:
        student.full_name = body.full_name.strip()
        student.search_name = search_key(student.full_name)
    if "language" in body.model_fields_set:
        if body.language and school_class.grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        await assign_student_language(
            db, student_id=student_id, year_id=school_class.year_id, language=body.language
        )
    try:
        await db.flush()
        language = await student_language(db, student_id, school_class.year_id)
        changed_before, changed_after = changed_values(
            before,
            {
                "full_name": student.full_name,
                "school_number": enrollment.school_number,
                "language": language,
            },
        )
        action = await record_action(
            db,
            actor=actor,
            kind="student.edit",
            params={
                "student": student.full_name,
                "class": class_label(school_class.grade_level, school_class.section),
                "changes": change_list(changed_before, changed_after),
            },
            undo={
                "student_id": student_id,
                "year_id": school_class.year_id,
                "before": changed_before,
                "after": changed_after,
            },
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
        raise
    return RosterStudentWriteOut(
        student_id=student.id,
        school_number=enrollment.school_number,
        full_name=student.full_name,
        language=language,
        action_id=action.id,
    )


@router.post("/roster/move")
async def move_admin_roster(
    body: MoveBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> RosterMoveOut:
    target = await db.get(SchoolClass, body.target_class_id)
    if target is None:
        raise HTTPException(404, {"code": "unknown_class"})
    await _ensure_year_writable(db, target.year_id)
    try:
        moved, unchanged = await move_students(
            db,
            student_ids=body.student_ids,
            target_class=target,
            allow_grade_change=body.allow_grade_change,
        )
    except ValueError as exc:
        raise HTTPException(409, {"code": str(exc)}) from exc
    try:
        await db.flush()
        names = dict(
            (
                await db.execute(
                    select(Student.id, Student.full_name).where(
                        Student.id.in_([student_id for student_id, _ in moved])
                    )
                )
            ).all()
        )
        sources = {
            item.id: class_label(item.grade_level, item.section)
            for item in await db.scalars(
                select(SchoolClass).where(SchoolClass.id.in_({class_id for _, class_id in moved}))
            )
        }
        action = await record_action(
            db,
            actor=actor,
            kind="student.move",
            params={
                "count": len(moved),
                "students": [names[student_id] for student_id, _ in moved],
                "from_classes": sorted(set(sources.values())),
                "to_class": class_label(target.grade_level, target.section),
            },
            undo={
                "year_id": target.year_id,
                "target_class_id": target.id,
                "moved": [
                    {
                        "student_id": student_id,
                        "from_class_id": class_id,
                        "from_class": sources[class_id],
                    }
                    for student_id, class_id in moved
                ],
            },
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
        raise
    return RosterMoveOut(changed=len(moved), unchanged=unchanged, action_id=action.id)


@router.put("/years/{year_id}/student-language")
async def set_student_language(
    year_id: int,
    body: LanguageBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> StudentLanguageOut:
    await _ensure_year_writable(db, year_id)
    student_ids = list(dict.fromkeys(body.student_ids))
    enrollments = list(
        (
            await db.execute(
                select(Enrollment, SchoolClass)
                .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
                .where(
                    Enrollment.year_id == year_id,
                    Enrollment.student_id.in_(student_ids),
                )
            )
        ).all()
    )
    if len(enrollments) != len(student_ids):
        raise HTTPException(422, {"code": "student_not_enrolled_in_year"})
    if body.language and any(item[1].grade_level < L2_START_GRADE for item in enrollments):
        raise HTTPException(422, {"code": "language_grade_too_low"})
    existing = {
        item.student_id: item
        for item in await db.scalars(
            select(StudentLanguage).where(
                StudentLanguage.year_id == year_id,
                StudentLanguage.student_id.in_(student_ids),
            )
        )
    }
    before = [
        {
            "student_id": student_id,
            "language": existing[student_id].language if student_id in existing else None,
        }
        for student_id in student_ids
    ]
    for student_id in student_ids:
        await assign_student_language(
            db, student_id=student_id, year_id=year_id, language=body.language
        )
    names = dict(
        (
            await db.execute(
                select(Student.id, Student.full_name).where(Student.id.in_(student_ids))
            )
        ).all()
    )
    action = await record_action(
        db,
        actor=actor,
        kind="student.language",
        params={
            "count": len(student_ids),
            "language": body.language,
            "students": [names[student_id] for student_id in student_ids],
        },
        undo={"year_id": year_id, "language": body.language, "before": before},
    )
    await db.commit()
    return StudentLanguageOut(changed=len(student_ids), action_id=action.id)
