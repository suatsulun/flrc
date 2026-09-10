from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    Enrollment,
    SaveBatch,
    SchoolClass,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin-classes"])
Role = Literal["main", "skills", "german", "french"]


def _field_for_role(role: str) -> str:
    return "english" if role in ("main", "skills") else role


def _stage_for_class(school_class: SchoolClass) -> str:
    return "primary" if school_class.grade_level <= 4 else "middle"


class AdminClassOut(BaseModel):
    id: int
    year_id: int
    grade_level: int
    section: str
    name: str
    student_count: int


class ClassCreate(BaseModel):
    year_id: int
    grade_level: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=8)


class ClassPatch(BaseModel):
    grade_level: int | None = Field(default=None, ge=1, le=8)
    section: str | None = Field(default=None, min_length=1, max_length=8)


class AssignmentChange(BaseModel):
    class_id: int
    role: Role
    user_id: int | None


class AssignmentBulk(BaseModel):
    changes: list[AssignmentChange] = Field(max_length=500)


class MatrixSlotOut(BaseModel):
    class_id: int
    role: str
    user_id: int
    user_name: str
    user_active: bool


async def _writable_year(db: AsyncSession, year_id: int) -> AcademicYear:
    year = await db.get(AcademicYear, year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    if year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    return year


async def _class_out(db: AsyncSession, school_class: SchoolClass) -> AdminClassOut:
    count = await db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.class_id == school_class.id)
    )
    return AdminClassOut(
        id=school_class.id,
        year_id=school_class.year_id,
        grade_level=school_class.grade_level,
        section=school_class.section,
        name=f"{school_class.grade_level}/{school_class.section}",
        student_count=count or 0,
    )


@router.get("/years/{year_id}/classes")
async def list_admin_classes(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[AdminClassOut]:
    del actor
    if await db.get(AcademicYear, year_id) is None:
        raise HTTPException(404, {"code": "unknown_year"})
    classes = list(
        await db.scalars(
            select(SchoolClass)
            .where(SchoolClass.year_id == year_id)
            .order_by(SchoolClass.grade_level, SchoolClass.section)
        )
    )
    counts: dict[int, int] = {}
    if classes:
        count_rows = (
            await db.execute(
                select(Enrollment.class_id, func.count().label("student_count"))
                .where(Enrollment.class_id.in_([item.id for item in classes]))
                .group_by(Enrollment.class_id)
            )
        ).all()
        counts = {row.class_id: row.student_count for row in count_rows}
    return [
        AdminClassOut(
            id=item.id,
            year_id=item.year_id,
            grade_level=item.grade_level,
            section=item.section,
            name=f"{item.grade_level}/{item.section}",
            student_count=counts.get(item.id, 0),
        )
        for item in classes
    ]


@router.post("/classes", status_code=201)
async def create_admin_class(
    body: ClassCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AdminClassOut:
    del actor
    await _writable_year(db, body.year_id)
    section = body.section.strip().upper()
    duplicate = await db.scalar(
        select(SchoolClass.id).where(
            SchoolClass.year_id == body.year_id,
            SchoolClass.grade_level == body.grade_level,
            SchoolClass.section == section,
        )
    )
    if duplicate is not None:
        raise HTTPException(409, {"code": "duplicate_class"})
    school_class = SchoolClass(year_id=body.year_id, grade_level=body.grade_level, section=section)
    db.add(school_class)
    await db.commit()
    await db.refresh(school_class)
    return await _class_out(db, school_class)


@router.patch("/classes/{class_id}")
async def patch_admin_class(
    class_id: int,
    body: ClassPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AdminClassOut:
    del actor
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    await _writable_year(db, school_class.year_id)
    if body.grade_level is not None:
        school_class.grade_level = body.grade_level
    if body.section is not None:
        school_class.section = body.section.strip().upper()
    await db.commit()
    return await _class_out(db, school_class)


@router.delete("/classes/{class_id}")
async def delete_admin_class(
    class_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    del actor
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await _writable_year(db, school_class.year_id)
    if year.status != "setup":
        raise HTTPException(409, {"code": "class_delete_setup_only"})
    blockers = 0
    for model in (Enrollment, SaveBatch, TeachingAssignment):
        blockers += (
            await db.scalar(
                select(func.count()).select_from(model).where(model.class_id == class_id)
            )
            or 0
        )
    if blockers:
        raise HTTPException(409, {"code": "class_in_use"})
    await db.delete(school_class)
    await db.commit()
    return {"deleted": True}


async def _matrix(db: AsyncSession, year_id: int) -> list[MatrixSlotOut]:
    rows = (
        await db.execute(
            select(TeachingAssignment, User)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .join(User, User.id == TeachingAssignment.user_id)
            .where(SchoolClass.year_id == year_id)
            .order_by(TeachingAssignment.class_id, TeachingAssignment.role)
        )
    ).all()
    return [
        MatrixSlotOut(
            class_id=assignment.class_id,
            role=assignment.role,
            user_id=user.id,
            user_name=user.full_name,
            user_active=user.is_active,
        )
        for assignment, user in rows
    ]


@router.get("/years/{year_id}/assignments")
async def list_assignment_matrix(
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[MatrixSlotOut]:
    del actor
    if await db.get(AcademicYear, year_id) is None:
        raise HTTPException(404, {"code": "unknown_year"})
    return await _matrix(db, year_id)


@router.put("/years/{year_id}/assignments")
async def replace_assignment_matrix(
    year_id: int,
    body: AssignmentBulk,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[MatrixSlotOut]:
    del actor
    await _writable_year(db, year_id)
    class_ids = {change.class_id for change in body.changes}
    user_ids = {change.user_id for change in body.changes if change.user_id is not None}
    classes = {
        item.id: item
        for item in (await db.scalars(select(SchoolClass).where(SchoolClass.id.in_(class_ids))))
    }
    users = {
        item.id: item for item in (await db.scalars(select(User).where(User.id.in_(user_ids))))
    }
    if any(item.year_id != year_id for item in classes.values()) or len(classes) != len(class_ids):
        raise HTTPException(422, {"code": "invalid_class"})
    if len(users) != len(user_ids) or any(not item.is_active for item in users.values()):
        raise HTTPException(422, {"code": "invalid_user"})
    # Validate every input before reducing repeated slots to their final value.
    changes: dict[tuple[int, str], AssignmentChange] = {}
    for change in body.changes:
        if change.user_id is not None and users[change.user_id].teaching_field != _field_for_role(
            change.role
        ):
            raise HTTPException(
                422,
                {
                    "code": "teacher_field_mismatch",
                    "class_id": change.class_id,
                    "role": change.role,
                },
            )
        if (
            change.user_id is not None
            and _field_for_role(change.role) == "english"
            and users[change.user_id].teaching_stage != _stage_for_class(classes[change.class_id])
        ):
            raise HTTPException(
                422,
                {
                    "code": "teacher_stage_mismatch",
                    "class_id": change.class_id,
                    "role": change.role,
                },
            )
        changes[(change.class_id, change.role)] = change

    assignments = {
        (item.class_id, item.role): item
        for item in await db.scalars(
            select(TeachingAssignment).where(TeachingAssignment.class_id.in_(class_ids))
        )
    }
    for key, change in changes.items():
        existing = assignments.get(key)
        if change.user_id is None:
            if existing:
                await db.delete(existing)
        elif existing:
            existing.user_id = change.user_id
        else:
            db.add(
                TeachingAssignment(
                    class_id=change.class_id,
                    role=change.role,
                    user_id=change.user_id,
                )
            )
    await db.commit()
    return await _matrix(db, year_id)
