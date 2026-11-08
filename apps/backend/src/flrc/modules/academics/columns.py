from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    AuditEntry,
    ColumnDefinition,
    GradeValue,
    Semester,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import MAX_GRADE, MIN_GRADE
from flrc.modules.academics.fields import SUBJECT_LOCALE, field_name
from flrc.modules.academics.programme import (
    allows_column_type,
    has_teacher_comments,
    prints_turkish,
    uses_scale_only,
)
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.changes.service import (
    ActionWrite,
    change_list,
    changed_values,
    record_action,
    with_action,
)

router = APIRouter(prefix="/columns", tags=["columns"])

Subject = Literal["english", "german", "french"]
Role = Literal["main", "skills", "german", "french"]
ValueType = Literal["score", "scale3", "text"]
Text = Annotated[str, StringConstraints(strip_whitespace=True)]
FieldName = Annotated[Text, StringConstraints(min_length=1)]


class LabelSet(BaseModel):
    """Stored wording per language; the printed cards pair Turkish with the subject's language."""

    tr: str = ""
    en: str = ""
    de: str = ""
    fr: str = ""


class ColumnCreate(BaseModel):
    grade_level: int = Field(ge=MIN_GRADE, le=MAX_GRADE)
    subject: Subject
    value_type: ValueType
    owner_role: Role
    # A field has one name in the apps, written in its subject's language.
    name: FieldName
    group: Text | None = None
    # Printed cards may also need Turkish wording (see prints_turkish).
    turkish_name: Text | None = None
    turkish_group: Text | None = None
    counts_in_average: bool = False


class ColumnPatch(BaseModel):
    counts_in_average: bool | None = None
    value_type: ValueType | None = None
    owner_role: Role | None = None
    # The field's name in its subject's language (ADR-076); other wording stays as created.
    name: FieldName | None = None


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

    # Pydantic documents this decorator pair; mypy does not model it.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def name(self) -> str:
        return field_name(self.labels.model_dump(), self.subject)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def group(self) -> str | None:
        if self.group_labels is None:
            return None
        return field_name(self.group_labels.model_dump(), self.subject)


class ColumnWriteOut(ColumnOut, ActionWrite):
    pass


class DeleteResult(ActionWrite):
    deleted: bool
    disabled: bool


class ReorderOut(ActionWrite):
    ok: bool


class CopyOut(ActionWrite):
    copied: int


class ReorderBody(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class CopyBody(BaseModel):
    source_grade_level: int = Field(ge=MIN_GRADE, le=MAX_GRADE)
    source_subject: Subject
    target_grade_level: int = Field(ge=MIN_GRADE, le=MAX_GRADE)
    target_subject: Subject


def _check_owner_rule(subject: str, owner_role: str) -> None:
    is_l2 = subject in ("german", "french")
    if is_l2 and owner_role != subject:
        raise HTTPException(422, {"code": "owner_subject_mismatch"})
    if not is_l2 and owner_role not in ("main", "skills"):
        raise HTTPException(422, {"code": "owner_subject_mismatch"})


def _check_programme(grade: int, subject: str, value_type: str, counts_in_average: bool) -> None:
    if value_type == "text" and not has_teacher_comments(grade, subject):
        raise HTTPException(422, {"code": "middle_english_no_comments"})
    if not allows_column_type(grade, subject, value_type) or (
        uses_scale_only(grade, subject) and counts_in_average
    ):
        raise HTTPException(422, {"code": "grade_four_l2_scale_only"})


def _lacks_turkish(
    grade: int,
    subject: str,
    value_type: str,
    labels: dict[str, str],
    group_labels: dict[str, str] | None,
) -> bool:
    """Whether a printed card would show this field in Turkish without its Turkish wording."""
    return prints_turkish(grade, subject, value_type) and (
        not labels.get("tr") or (group_labels is not None and not group_labels.get("tr"))
    )


async def editable_semester(db: AsyncSession, semester_id: int | None) -> Semester:
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
    return [
        ColumnOut.model_validate(c)
        for c in result.scalars()
        if c.value_type != "text" or has_teacher_comments(c.grade_level, c.subject)
    ]


def column_snapshot(column: ColumnDefinition) -> dict[str, object]:
    """Every stored attribute of a field, enough to recreate it exactly."""
    return {
        "id": column.id,
        "semester_id": column.semester_id,
        "grade_level": column.grade_level,
        "subject": column.subject,
        "value_type": column.value_type,
        "owner_role": column.owner_role,
        "labels": column.labels,
        "group_labels": column.group_labels,
        "counts_in_average": column.counts_in_average,
        "position": column.position,
        "is_active": column.is_active,
    }


def _field_params(column: ColumnDefinition) -> dict[str, object]:
    return {
        "field": field_name(column.labels, column.subject),
        "grade_level": column.grade_level,
        "subject": column.subject,
    }


async def column_has_grades(db: AsyncSession, column_id: int) -> bool:
    found = await db.scalar(
        select(GradeValue.id).where(GradeValue.column_definition_id == column_id).limit(1)
    )
    return found is not None


async def column_has_history(db: AsyncSession, column_id: int) -> bool:
    """Whether grade audit rows refer to the field, even after its grades were undone."""
    found = await db.scalar(
        select(AuditEntry.id).where(AuditEntry.column_definition_id == column_id).limit(1)
    )
    return found is not None


def column_state(column: ColumnDefinition) -> dict[str, object]:
    """The patchable attributes, with ``name`` as stored under the subject's language."""
    return {
        "counts_in_average": column.counts_in_average,
        "value_type": column.value_type,
        "owner_role": column.owner_role,
        "name": column.labels.get(SUBJECT_LOCALE[column.subject]),
    }


async def apply_column_patch(
    db: AsyncSession, column: ColumnDefinition, updates: dict[str, object]
) -> None:
    """Validate and apply patchable attributes; a ``None`` name removes the stored name."""
    owner_role = str(updates.get("owner_role", column.owner_role))
    value_type = str(updates.get("value_type", column.value_type))
    counts_in_average = bool(updates.get("counts_in_average", column.counts_in_average))
    _check_owner_rule(column.subject, owner_role)
    _check_programme(column.grade_level, column.subject, value_type, counts_in_average)
    if value_type != column.value_type:
        if await column_has_grades(db, column.id):
            raise HTTPException(409, {"code": "column_type_in_use"})
        # Only the subject-language name can be patched (ADR-076), so a field cannot become
        # one its card prints in Turkish unless it already has the Turkish wording; recreate
        # it with the wording instead.
        if _lacks_turkish(
            column.grade_level, column.subject, value_type, column.labels, column.group_labels
        ):
            raise HTTPException(422, {"code": "turkish_wording_required"})
    column.owner_role = owner_role
    column.value_type = value_type
    column.counts_in_average = counts_in_average
    if "name" in updates:
        locale = SUBJECT_LOCALE[column.subject]
        labels = {key: value for key, value in column.labels.items() if key != locale}
        if updates["name"] is not None:
            labels[locale] = str(updates["name"])
        # A new mapping, so the JSONB change is persisted.
        column.labels = labels


@router.post("", status_code=201)
async def create_column(
    body: ColumnCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> ColumnWriteOut:
    semester = await editable_semester(db, semester_id)
    _check_owner_rule(body.subject, body.owner_role)
    _check_programme(body.grade_level, body.subject, body.value_type, body.counts_in_average)
    locale = SUBJECT_LOCALE[body.subject]
    labels = {locale: body.name}
    if body.turkish_name:
        labels["tr"] = body.turkish_name
    group_labels = None
    if body.group:
        group_labels = {locale: body.group}
        if body.turkish_group:
            group_labels["tr"] = body.turkish_group
    if _lacks_turkish(body.grade_level, body.subject, body.value_type, labels, group_labels):
        raise HTTPException(422, {"code": "turkish_wording_required"})
    max_pos = (
        await db.execute(
            select(func.coalesce(func.max(ColumnDefinition.position), 0)).where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == body.grade_level,
                ColumnDefinition.subject == body.subject,
            )
        )
    ).scalar_one()
    column = ColumnDefinition(
        semester_id=semester.id,
        position=max_pos + 1,
        labels=labels,
        group_labels=group_labels,
        **body.model_dump(exclude={"name", "group", "turkish_name", "turkish_group"}),
    )
    db.add(column)
    await db.flush()
    action = await record_action(
        db,
        actor=actor,
        kind="field.create",
        params=_field_params(column),
        undo={"column_id": column.id},
    )
    await db.commit()
    await db.refresh(column)
    return with_action(ColumnWriteOut, ColumnOut.model_validate(column), action)


@router.patch("/{column_id}")
async def update_column(
    column_id: int,
    body: ColumnPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> ColumnWriteOut:
    semester = await editable_semester(db, semester_id)
    # Locked until the commit, so the recorded undo snapshot is what this write replaced.
    column = await db.get(ColumnDefinition, column_id, with_for_update=True, populate_existing=True)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    before = column_state(column)
    await apply_column_patch(db, column, body.model_dump(exclude_unset=True, exclude_none=True))
    changed_before, changed_after = changed_values(before, column_state(column))
    action = await record_action(
        db,
        actor=actor,
        kind="field.edit",
        params={**_field_params(column), "changes": change_list(changed_before, changed_after)},
        undo={"column_id": column.id, "before": changed_before, "after": changed_after},
    )
    await db.commit()
    await db.refresh(column)
    return with_action(ColumnWriteOut, ColumnOut.model_validate(column), action)


@router.delete("/{column_id}")
async def delete_column(
    column_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> DeleteResult:
    semester = await editable_semester(db, semester_id)
    # Locked until the commit, so the recorded undo snapshot is what this write replaced.
    column = await db.get(ColumnDefinition, column_id, with_for_update=True, populate_existing=True)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    # A field with grades or grade history is hidden instead, so its grades and audit
    # trail stay attached and can return.
    disabled = await column_has_grades(db, column_id) or await column_has_history(db, column_id)
    if disabled:
        undo: dict[str, object] = {
            "column_id": column.id,
            "semester_id": column.semester_id,
            "disabled": True,
            "was_active": column.is_active,
        }
        column.is_active = False
    else:
        undo = {"column": column_snapshot(column), "disabled": False}
        await db.delete(column)
    action = await record_action(
        db,
        actor=actor,
        kind="field.delete",
        params={**_field_params(column), "disabled": disabled},
        undo=undo,
    )
    await db.commit()
    return DeleteResult(deleted=not disabled, disabled=disabled, action_id=action.id)


async def reorder_scope_ids(
    db: AsyncSession, semester_id: int, grade_level: int, subject: str
) -> set[int]:
    """The fields one reorder must place: inactive ones too, minus retired middle-English
    comments (ADR-063)."""
    scope_query = select(ColumnDefinition.id).where(
        ColumnDefinition.semester_id == semester_id,
        ColumnDefinition.grade_level == grade_level,
        ColumnDefinition.subject == subject,
    )
    if not has_teacher_comments(grade_level, subject):
        scope_query = scope_query.where(ColumnDefinition.value_type != "text")
    return set(await db.scalars(scope_query))


@router.post("/reorder")
async def reorder_columns(
    body: ReorderBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> ReorderOut:
    semester = await editable_semester(db, semester_id)
    result = await db.execute(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.id.in_(body.ordered_ids),
            ColumnDefinition.semester_id == semester.id,
        )
        .order_by(ColumnDefinition.id)
        # FOR NO KEY UPDATE: only positions change, so grade saves inserting into these fields
        # (their foreign keys take KEY SHARE) neither wait for the reorder nor deadlock with it,
        # while reorders, edits and deletions of the same fields still queue behind each other.
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
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
    if await reorder_scope_ids(db, semester.id, grade_level, subject) != set(columns):
        raise HTTPException(422, {"code": "reorder_mismatch"})
    before = [[cid, columns[cid].position] for cid in body.ordered_ids]
    for pos, cid in enumerate(body.ordered_ids, start=1):
        columns[cid].position = pos
    action = await record_action(
        db,
        actor=actor,
        kind="field.reorder",
        params={"grade_level": grade_level, "subject": subject, "count": len(columns)},
        undo={
            "semester_id": semester.id,
            "grade_level": grade_level,
            "subject": subject,
            "before": before,
            "after": [[cid, pos] for pos, cid in enumerate(body.ordered_ids, start=1)],
        },
    )
    await db.commit()
    return ReorderOut(ok=True, action_id=action.id)


@router.post("/copy")
async def copy_columns(
    body: CopyBody,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> CopyOut:
    semester = await editable_semester(db, semester_id)
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
    # Copied fields keep their stored wording, so the target must be able to name and print
    # them: in its subject's language, and in Turkish where its card prints Turkish.
    target_locale = SUBJECT_LOCALE[body.target_subject]
    for src in sources:
        if body.target_subject != body.source_subject and (
            not src.labels.get(target_locale)
            or (src.group_labels is not None and not src.group_labels.get(target_locale))
        ):
            raise HTTPException(422, {"code": "copy_language_mismatch"})
        if _lacks_turkish(
            body.target_grade_level,
            body.target_subject,
            src.value_type,
            src.labels,
            src.group_labels,
        ):
            raise HTTPException(422, {"code": "turkish_wording_required"})
    is_l2_target = body.target_subject in ("german", "french")
    copies = [
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
        for src in sources
    ]
    db.add_all(copies)
    await db.flush()
    action = await record_action(
        db,
        actor=actor,
        kind="field.copy",
        params={
            "count": len(copies),
            "from_grade_level": body.source_grade_level,
            "from_subject": body.source_subject,
            "to_grade_level": body.target_grade_level,
            "to_subject": body.target_subject,
        },
        undo={"semester_id": semester.id, "column_ids": [column.id for column in copies]},
    )
    await db.commit()
    return CopyOut(copied=len(copies), action_id=action.id)
