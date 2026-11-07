from collections.abc import Mapping
from typing import Annotated, Literal, Self, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from flrc.db.models import (
    AcademicYear,
    AdminAction,
    Enrollment,
    OverrideGrant,
    SaveBatch,
    SchoolClass,
    Student,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import (
    MAX_GRADE,
    MIN_GRADE,
    SECTION_MAX_LENGTH,
    class_label,
    normalize_section,
)
from flrc.modules.academics.programme import stage_for_grade
from flrc.modules.administration.account_locks import assignable, lock_for_admin
from flrc.modules.administration.roster_service import (
    NumberHolder,
    is_duplicate_school_number,
)
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.changes.service import ActionWrite, record_action, with_action

router = APIRouter(prefix="/admin", tags=["admin-classes"])
Role = Literal["main", "skills", "german", "french"]


def _field_for_role(role: str) -> str:
    return "english" if role in ("main", "skills") else role


def _class_name(school_class: SchoolClass) -> str:
    return class_label(school_class.grade_level, school_class.section)


def assignment_mismatch(
    teaching_field: str, teaching_stage: str | None, grade_level: int, role: str
) -> Literal["teacher_field_mismatch", "teacher_stage_mismatch"] | None:
    """Why a teacher may not hold a class role: wrong subject, or English at the wrong stage."""
    if teaching_field != _field_for_role(role):
        return "teacher_field_mismatch"
    if teaching_field == "english" and teaching_stage != stage_for_grade(grade_level):
        return "teacher_stage_mismatch"
    return None


class AdminClassOut(BaseModel):
    id: int
    year_id: int
    grade_level: int
    section: str
    name: str
    student_count: int


class AdminClassWriteOut(AdminClassOut, ActionWrite):
    pass


class ClassDeleteOut(ActionWrite):
    deleted: bool


class ClassCreate(BaseModel):
    year_id: int
    grade_level: int = Field(ge=MIN_GRADE, le=MAX_GRADE)
    section: str = Field(min_length=1, max_length=SECTION_MAX_LENGTH)

    @model_validator(mode="after")
    def canonical_section(self) -> Self:
        self.section = normalize_section(self.grade_level, self.section)
        if not self.section:
            raise ValueError("invalid_section")
        return self


class ClassPatch(BaseModel):
    grade_level: int | None = Field(default=None, ge=MIN_GRADE, le=MAX_GRADE)
    section: str | None = Field(default=None, min_length=1, max_length=SECTION_MAX_LENGTH)


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


class AssignmentMatrixWriteOut(ActionWrite):
    slots: list[MatrixSlotOut]


async def writable_class_year(db: AsyncSession, year_id: int) -> AcademicYear:
    """Lock a year for a class or assignment write; archived years are read-only."""
    year = await db.scalar(select(AcademicYear).where(AcademicYear.id == year_id).with_for_update())
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    if year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    return year


async def lock_class(db: AsyncSession, class_id: int) -> tuple[SchoolClass, AcademicYear]:
    """Lock a class's writable year, then the class itself, and read the class fresh.

    Always year first, the order every class and roster write uses, so a recorded
    previous state cannot change before the commit.
    """
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await writable_class_year(db, school_class.year_id)
    locked = await db.get(SchoolClass, class_id, with_for_update=True, populate_existing=True)
    if locked is None:
        raise HTTPException(404, {"code": "unknown_class"})
    return locked, year


async def class_in_use(db: AsyncSession, class_id: int) -> bool:
    """Whether a class holds pupils, saved grades, assignments or grants and so must stay."""
    for model in (Enrollment, SaveBatch, TeachingAssignment, OverrideGrant):
        found = await db.scalar(select(model.id).where(model.class_id == class_id).limit(1))
        if found is not None:
            return True
    return False


async def class_conflict(
    db: AsyncSession, *, year_id: int, grade_level: int, section: str, class_id: int | None
) -> SchoolClass | None:
    """Another class of the year with the same grade and section."""
    statement = select(SchoolClass).where(
        SchoolClass.year_id == year_id,
        SchoolClass.grade_level == grade_level,
        SchoolClass.section == section,
    )
    if class_id is not None:
        statement = statement.where(SchoolClass.id != class_id)
    return await db.scalar(statement)


async def stage_number_clash(
    db: AsyncSession, school_class: SchoolClass, grade_level: int
) -> NumberHolder | None:
    """A pupil of the other stage holding a number this class would carry into it."""
    if stage_for_grade(grade_level) == stage_for_grade(school_class.grade_level):
        return None
    other = aliased(Enrollment)
    holder_class = aliased(SchoolClass)
    row = (
        await db.execute(
            select(Enrollment.school_number, Student.full_name, holder_class)
            .join(
                other,
                (other.year_id == Enrollment.year_id)
                & (other.school_number == Enrollment.school_number)
                & (other.class_id != school_class.id),
            )
            .join(Student, Student.id == other.student_id)
            .join(holder_class, holder_class.id == other.class_id)
            .where(
                Enrollment.class_id == school_class.id,
                other.stage == stage_for_grade(grade_level),
            )
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    number, student, holder = row
    # The join matched equal numbers, so this one is never empty.
    assert number is not None
    return NumberHolder(
        {
            "number": number,
            "student": student,
            "class": class_label(holder.grade_level, holder.section),
        }
    )


async def _class_out(db: AsyncSession, school_class: SchoolClass) -> AdminClassOut:
    count = await db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.class_id == school_class.id)
    )
    return AdminClassOut(
        id=school_class.id,
        year_id=school_class.year_id,
        grade_level=school_class.grade_level,
        section=school_class.section,
        name=class_label(school_class.grade_level, school_class.section),
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
            name=class_label(item.grade_level, item.section),
            student_count=counts.get(item.id, 0),
        )
        for item in classes
    ]


@router.post("/classes", status_code=201)
async def create_admin_class(
    body: ClassCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AdminClassWriteOut:
    await writable_class_year(db, body.year_id)
    if await class_conflict(
        db,
        year_id=body.year_id,
        grade_level=body.grade_level,
        section=body.section,
        class_id=None,
    ):
        raise HTTPException(409, {"code": "duplicate_class"})
    school_class = SchoolClass(
        year_id=body.year_id, grade_level=body.grade_level, section=body.section
    )
    db.add(school_class)
    await db.flush()
    action = await record_action(
        db,
        actor=actor,
        kind="class.create",
        params={"class": class_label(school_class.grade_level, school_class.section)},
        undo={"class_id": school_class.id},
    )
    await db.commit()
    await db.refresh(school_class)
    return with_action(AdminClassWriteOut, await _class_out(db, school_class), action)


@router.patch("/classes/{class_id}")
async def patch_admin_class(
    class_id: int,
    body: ClassPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AdminClassWriteOut:
    school_class, _ = await lock_class(db, class_id)
    grade = body.grade_level if body.grade_level is not None else school_class.grade_level
    section = normalize_section(
        grade, body.section if body.section is not None else school_class.section
    )
    if not section:
        raise HTTPException(422, {"code": "invalid_section"})
    if await class_conflict(
        db,
        year_id=school_class.year_id,
        grade_level=grade,
        section=section,
        class_id=class_id,
    ):
        raise HTTPException(409, {"code": "duplicate_class"})
    # Its pupils follow the class into the other school stage with their
    # numbers, so the edit is refused if one is already taken there.
    if await stage_number_clash(db, school_class, grade) is not None:
        raise HTTPException(409, {"code": "duplicate_school_number"})
    previous_class = class_label(school_class.grade_level, school_class.section)
    before = {"grade_level": school_class.grade_level, "section": school_class.section}
    school_class.grade_level, school_class.section = grade, section
    try:
        await db.flush()
        action = await record_action(
            db,
            actor=actor,
            kind="class.edit",
            params={
                "class": class_label(grade, section),
                "previous_class": previous_class,
            },
            undo={
                "class_id": class_id,
                "before": before,
                "after": {"grade_level": grade, "section": section},
            },
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise HTTPException(409, {"code": "duplicate_school_number"}) from exc
        raise
    return with_action(AdminClassWriteOut, await _class_out(db, school_class), action)


@router.delete("/classes/{class_id}")
async def delete_admin_class(
    class_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ClassDeleteOut:
    school_class, year = await lock_class(db, class_id)
    if year.status != "setup":
        raise HTTPException(409, {"code": "class_delete_setup_only"})
    if await class_in_use(db, class_id):
        raise HTTPException(409, {"code": "class_in_use"})
    snapshot = {
        "id": school_class.id,
        "year_id": school_class.year_id,
        "grade_level": school_class.grade_level,
        "section": school_class.section,
    }
    await db.delete(school_class)
    action = await record_action(
        db,
        actor=actor,
        kind="class.delete",
        params={"class": class_label(school_class.grade_level, school_class.section)},
        undo={"class": snapshot},
    )
    await db.commit()
    return ClassDeleteOut(deleted=True, action_id=action.id)


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


class SlotChange(TypedDict):
    class_id: int
    role: str
    before: int | None
    after: int | None


async def apply_assignment_slots(
    db: AsyncSession, slots: dict[tuple[int, str], int | None]
) -> tuple[list[SlotChange], dict[int, str]]:
    """Write validated ``(class_id, role) -> user_id`` slots; ``None`` clears one.

    Returns the slots whose teacher actually changed, and the names of the teachers
    who held the touched slots before.
    """
    rows = await db.execute(
        select(TeachingAssignment, User.full_name)
        .join(User, User.id == TeachingAssignment.user_id)
        .where(TeachingAssignment.class_id.in_({class_id for class_id, _ in slots}))
        .order_by(TeachingAssignment.id)
        .with_for_update(of=TeachingAssignment)
        .execution_options(populate_existing=True)
    )
    assignments: dict[tuple[int, str], TeachingAssignment] = {}
    holders: dict[int, str] = {}
    for assignment, name in rows:
        assignments[(assignment.class_id, assignment.role)] = assignment
        holders[assignment.user_id] = name
    changed: list[SlotChange] = []
    for (class_id, role), user_id in slots.items():
        existing = assignments.get((class_id, role))
        before = existing.user_id if existing else None
        if before == user_id:
            continue
        changed.append(SlotChange(class_id=class_id, role=role, before=before, after=user_id))
        if user_id is None:
            if existing:
                await db.delete(existing)
        elif existing:
            existing.user_id = user_id
        else:
            db.add(TeachingAssignment(class_id=class_id, role=role, user_id=user_id))
    await db.flush()
    return changed, holders


async def record_assignment_change(
    db: AsyncSession,
    *,
    actor: User,
    year_id: int,
    changed: list[SlotChange],
    classes: Mapping[int, SchoolClass],
    names: Mapping[int, str],
) -> AdminAction:
    """Record assignment changes; ``classes`` and ``names`` cover every changed slot."""
    return await record_action(
        db,
        actor=actor,
        kind="assignments.replace",
        params={
            "count": len(changed),
            "changes": [
                {
                    "class": _class_name(classes[item["class_id"]]),
                    "role": item["role"],
                    "from_teacher": names.get(item["before"]) if item["before"] else None,
                    "to_teacher": names.get(item["after"]) if item["after"] else None,
                }
                for item in changed
            ],
        },
        undo={"year_id": year_id, "slots": [dict(item) for item in changed]},
    )


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
) -> AssignmentMatrixWriteOut:
    user_ids = {change.user_id for change in body.changes if change.user_id is not None}
    # The acting administrator and the destination accounts first, in id order (ADR-080): a
    # concurrent deactivation or deletion of any of them is waited for and seen. The actor is
    # locked even for a clear-only change, or its recorded action could wait behind a deletion
    # of the actor that waits for the actor's own slot.
    users = await lock_for_admin(db, actor, shared=user_ids)
    await writable_class_year(db, year_id)
    class_ids = {change.class_id for change in body.changes}
    classes = {
        item.id: item
        for item in (await db.scalars(select(SchoolClass).where(SchoolClass.id.in_(class_ids))))
    }
    if any(item.year_id != year_id for item in classes.values()) or len(classes) != len(class_ids):
        raise HTTPException(422, {"code": "invalid_class"})
    if not all(assignable(users.get(user_id)) for user_id in user_ids):
        raise HTTPException(422, {"code": "invalid_user"})
    # Validate every input before reducing repeated slots to their final value.
    slots: dict[tuple[int, str], int | None] = {}
    for change in body.changes:
        if change.user_id is not None:
            user = users[change.user_id]
            problem = assignment_mismatch(
                user.teaching_field,
                user.teaching_stage,
                classes[change.class_id].grade_level,
                change.role,
            )
            if problem is not None:
                raise HTTPException(
                    422, {"code": problem, "class_id": change.class_id, "role": change.role}
                )
        slots[(change.class_id, change.role)] = change.user_id
    changed, holders = await apply_assignment_slots(db, slots)
    action = await record_assignment_change(
        db,
        actor=actor,
        year_id=year_id,
        changed=changed,
        classes=classes,
        names=holders | {item.id: item.full_name for item in users.values()},
    )
    await db.commit()
    return AssignmentMatrixWriteOut(slots=await _matrix(db, year_id), action_id=action.id)
