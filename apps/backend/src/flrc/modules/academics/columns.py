from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import AcademicYear, ColumnDefinition, GradeValue, Semester, User
from flrc.db.session import get_session
from flrc.modules.academics.programme import allows_column_type, uses_scale_only
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/columns", tags=["columns"])

Subject = Literal["english", "german", "french"]
Role = Literal["main", "skills", "german", "french"]
ValueType = Literal["score", "scale3", "text"]


class LabelSet(BaseModel):
    tr: str = Field(min_length=1)
    en: str = ""
    de: str = ""
    fr: str = ""


class ColumnCreate(BaseModel):
    grade_level: int = Field(ge=1, le=8)
    subject: Subject
    value_type: ValueType
    owner_role: Role
    labels: LabelSet
    group_labels: LabelSet | None = None
    counts_in_average: bool = False


class ColumnPatch(BaseModel):
    labels: LabelSet | None = None
    group_labels: LabelSet | None = None
    counts_in_average: bool | None = None
    value_type: ValueType | None = None
    owner_role: Role | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade_level: int
    subject: str
    value_type: str
    owner_role: str
    labels: LabelSet
    group_labels: LabelSet | None
    counts_in_average: bool
    position: int
    is_active: bool


class DeleteResult(BaseModel):
    deleted: bool
    disabled: bool


class ReorderBody(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class CopyBody(BaseModel):
    source_grade_level: int = Field(ge=1, le=8)
    source_subject: Subject
    target_grade_level: int = Field(ge=1, le=8)
    target_subject: Subject


def _check_owner_rule(subject: str, owner_role: str) -> None:
    is_l2 = subject in ("german", "french")
    if is_l2 and owner_role != subject:
        raise HTTPException(422, {"code": "owner_subject_mismatch"})
    if not is_l2 and owner_role not in ("main", "skills"):
        raise HTTPException(422, {"code": "owner_subject_mismatch"})


def _check_programme(grade: int, subject: str, value_type: str, counts_in_average: bool) -> None:
    if not allows_column_type(grade, subject, value_type) or (
        uses_scale_only(grade, subject) and counts_in_average
    ):
        raise HTTPException(422, {"code": "grade_four_l2_scale_only"})


async def _editable_semester(db: AsyncSession, semester_id: int | None) -> Semester:
    if semester_id is None:
        semester = await db.scalar(
            select(Semester)
            .join(AcademicYear, AcademicYear.id == Semester.year_id)
            .where(AcademicYear.status == "active", Semester.status == "open")
        )
    else:
        semester = await db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(409, {"code": "semester_locked"})
    year = await db.get(AcademicYear, semester.year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    if year.status == "archived" or (year.status == "active" and semester.status != "open"):
        raise HTTPException(409, {"code": "semester_locked"})
    return semester


@router.get("")
async def list_columns(
    grade_level: int,
    subject: Subject,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> list[ColumnOut]:
    if semester_id is None:
        semester = await db.scalar(
            select(Semester)
            .join(AcademicYear, AcademicYear.id == Semester.year_id)
            .where(AcademicYear.status == "active", Semester.status == "open")
        )
        if semester is None:
            raise HTTPException(409, {"code": "semester_locked"})
    else:
        semester = await db.get(Semester, semester_id)
        if semester is None:
            raise HTTPException(404, {"code": "unknown_semester"})
    result = await db.execute(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.semester_id == semester.id,
            ColumnDefinition.grade_level == grade_level,
            ColumnDefinition.subject == subject,
        )
        .order_by(ColumnDefinition.position)
    )
    return [ColumnOut.model_validate(c) for c in result.scalars()]


@router.post("", status_code=201)
async def create_column(
    body: ColumnCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> ColumnOut:
    semester = await _editable_semester(db, semester_id)
    _check_owner_rule(body.subject, body.owner_role)
    _check_programme(body.grade_level, body.subject, body.value_type, body.counts_in_average)
    max_pos = (
        await db.execute(
            select(func.coalesce(func.max(ColumnDefinition.position), 0)).where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == body.grade_level,
                ColumnDefinition.subject == body.subject,
            )
        )
    ).scalar_one()
    column = ColumnDefinition(semester_id=semester.id, position=max_pos + 1, **body.model_dump())
    db.add(column)
    await db.commit()
    await db.refresh(column)
    return ColumnOut.model_validate(column)


@router.patch("/{column_id}")
async def update_column(
    column_id: int,
    body: ColumnPatch,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> ColumnOut:
    semester = await _editable_semester(db, semester_id)
    column = await db.get(ColumnDefinition, column_id)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    updates = body.model_dump(exclude_unset=True)
    _check_owner_rule(column.subject, updates.get("owner_role", column.owner_role))
    _check_programme(
        column.grade_level,
        column.subject,
        updates.get("value_type", column.value_type),
        updates.get("counts_in_average", column.counts_in_average),
    )
    if updates.get("value_type", column.value_type) != column.value_type:
        has_data = await db.scalar(
            select(func.count())
            .select_from(GradeValue)
            .where(GradeValue.column_definition_id == column.id)
        )
        if has_data:
            raise HTTPException(409, {"code": "column_type_in_use"})
    for key, value in updates.items():
        setattr(column, key, value)
    await db.commit()
    await db.refresh(column)
    return ColumnOut.model_validate(column)


@router.delete("/{column_id}")
async def delete_column(
    column_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> DeleteResult:
    semester = await _editable_semester(db, semester_id)
    column = await db.get(ColumnDefinition, column_id)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    has_data = (
        await db.execute(
            select(func.count())
            .select_from(GradeValue)
            .where(GradeValue.column_definition_id == column_id)
        )
    ).scalar_one() > 0
    if has_data:
        column.is_active = False
        await db.commit()
        return DeleteResult(deleted=False, disabled=True)
    await db.delete(column)
    await db.commit()
    return DeleteResult(deleted=True, disabled=False)


@router.post("/reorder")
async def reorder_columns(
    body: ReorderBody,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> dict[str, bool]:
    semester = await _editable_semester(db, semester_id)
    result = await db.execute(
        select(ColumnDefinition).where(
            ColumnDefinition.id.in_(body.ordered_ids),
            ColumnDefinition.semester_id == semester.id,
        )
    )
    columns = {c.id: c for c in result.scalars()}
    scopes = {(c.grade_level, c.subject) for c in columns.values()}
    if (
        set(columns) != set(body.ordered_ids)
        or len(body.ordered_ids) != len(columns)
        or len(scopes) != 1
    ):
        raise HTTPException(422, {"code": "reorder_mismatch"})
    grade_level, subject = scopes.pop()
    scope_ids = set(
        await db.scalars(
            select(ColumnDefinition.id).where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == grade_level,
                ColumnDefinition.subject == subject,
            )
        )
    )
    if scope_ids != set(columns):
        raise HTTPException(422, {"code": "reorder_mismatch"})
    for pos, cid in enumerate(body.ordered_ids, start=1):
        columns[cid].position = pos
    await db.commit()
    return {"ok": True}


@router.post("/copy")
async def copy_columns(
    body: CopyBody,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> dict[str, int]:
    semester = await _editable_semester(db, semester_id)
    same_family = (body.source_subject == "english") == (body.target_subject == "english")
    if not same_family:
        raise HTTPException(422, {"code": "copy_family_mismatch"})
    target_count = (
        await db.execute(
            select(func.count())
            .select_from(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == body.target_grade_level,
                ColumnDefinition.subject == body.target_subject,
            )
        )
    ).scalar_one()
    if target_count > 0:
        raise HTTPException(409, {"code": "target_not_empty"})
    result = await db.execute(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.semester_id == semester.id,
            ColumnDefinition.grade_level == body.source_grade_level,
            ColumnDefinition.subject == body.source_subject,
        )
        .order_by(ColumnDefinition.position)
    )
    sources = [
        column
        for column in result.scalars()
        if allows_column_type(body.target_grade_level, body.target_subject, column.value_type)
    ]
    is_l2_target = body.target_subject in ("german", "french")
    for src in sources:
        db.add(
            ColumnDefinition(
                semester_id=semester.id,
                grade_level=body.target_grade_level,
                subject=body.target_subject,
                value_type=src.value_type,
                owner_role=body.target_subject if is_l2_target else src.owner_role,
                labels=src.labels,
                group_labels=src.group_labels,
                counts_in_average=(
                    src.counts_in_average
                    and not uses_scale_only(body.target_grade_level, body.target_subject)
                ),
                position=src.position,
            )
        )
    await db.commit()
    return {"copied": len(sources)}
