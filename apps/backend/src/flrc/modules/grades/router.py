from datetime import datetime
from typing import Annotated, Any, Literal, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AcademicYear,
    AuditEntry,
    ColumnDefinition,
    Enrollment,
    GradeValue,
    OverrideGrant,
    SaveBatch,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.fields import VALUE_FIELD, CellValue, cell_value, pick_label
from flrc.modules.auth.dependencies import current_user, writable_semester
from flrc.modules.grades.permissions import require_subject_access

router = APIRouter(tags=["grid"])
log = structlog.get_logger()

Subject = Literal["english", "german", "french"]
Role = Literal["main", "skills", "german", "french"]


class CellOut(BaseModel):
    value: CellValue
    version: int


class GridColumnOut(BaseModel):
    id: int
    label: str
    group: str | None
    value_type: str
    owner_role: str
    owner_name: str | None
    owned_by_you: bool
    position: int


class GridRowOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str
    cells: dict[str, CellOut]


class GrantOut(BaseModel):
    role: str
    expires_at: datetime

    @field_serializer("expires_at")
    def serialize_expiry(self, value: datetime) -> str:
        return value.isoformat() + ("" if value.tzinfo else "Z")


class LastBatchOut(BaseModel):
    id: int
    created_at: datetime
    cell_count: int
    undoable: bool

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat() + ("" if value.tzinfo else "Z")


class GridMetaOut(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    subject: str
    year_id: int
    year_label: str
    semester_id: int
    semester_number: int
    semester_status: str
    year_status: str
    my_grants: list[GrantOut]
    my_last_batch: LastBatchOut | None


class GridOut(BaseModel):
    meta: GridMetaOut
    columns: list[GridColumnOut]
    rows: list[GridRowOut]


class SaveCellIn(BaseModel):
    student_id: int
    column_id: int
    value: CellValue
    expected_version: int = Field(ge=0)


class SaveRequest(BaseModel):
    subject: Subject
    force: bool = False
    confirm_outside_assignment: bool = False
    # A whole-class primary rubric can exceed 500 cells (e.g. 40 pupils × 14 rows).
    # Keep it in one audited save batch so "undo last save" reverses the entire action.
    cells: list[SaveCellIn] = Field(min_length=1, max_length=2000)


class AppliedOut(BaseModel):
    student_id: int
    column_id: int
    version: int


class ConflictOut(BaseModel):
    student_id: int
    student_name: str
    column_id: int
    column_label: str
    your_value: CellValue
    current_value: CellValue
    updated_by: str | None
    updated_at: datetime | None


class RejectedOut(BaseModel):
    student_id: int
    column_id: int
    code: str


class SaveResponse(BaseModel):
    applied: list[AppliedOut]
    conflicts: list[ConflictOut]
    rejected: list[RejectedOut]


class GrantBody(BaseModel):
    role: Role


def _valid_value(value_type: str, value: CellValue) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if value_type == "score":
        return isinstance(value, int) and 0 <= value <= 100
    if value_type == "scale3":
        return isinstance(value, int) and 1 <= value <= 3
    return isinstance(value, str) and len(value) <= 2000


def _value_fields(value_type: str, value: CellValue) -> dict[str, CellValue]:
    fields: dict[str, CellValue] = {"score": None, "scale": None, "text_value": None}
    fields[VALUE_FIELD[value_type]] = value
    return fields


async def _writable_class(db: AsyncSession, class_id: int, semester: Semester) -> SchoolClass:
    cls = await db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(404, {"code": "unknown_class"})
    if cls.year_id != semester.year_id:
        raise HTTPException(409, {"code": "semester_locked"})
    return cls


async def _renew_grant(
    db: AsyncSession, user_id: int, class_id: int, role: str
) -> tuple[int, datetime]:
    expires_at = func.now() + text("interval '1 hour'")
    statement = (
        pg_insert(OverrideGrant)
        .values(user_id=user_id, class_id=class_id, role=role, expires_at=expires_at)
        .on_conflict_do_update(
            index_elements=["user_id", "class_id", "role"],
            set_={"expires_at": expires_at},
        )
        .returning(OverrideGrant.id, OverrideGrant.expires_at)
    )
    grant_id, expiry = (await db.execute(statement)).one()
    return grant_id, expiry


async def _roster_ids(db: AsyncSession, class_id: int, subject: str, year_id: int) -> set[int]:
    query = (
        select(Student.id)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == class_id)
    )
    if subject in ("german", "french"):
        query = query.join(StudentLanguage, StudentLanguage.student_id == Student.id).where(
            StudentLanguage.year_id == year_id,
            StudentLanguage.language == subject,
        )
    return set((await db.scalars(query)).all())


def _raw_conflict(
    *,
    student_id: int,
    column_id: int,
    labels: dict[str, str],
    your_value: CellValue,
    current_value: CellValue,
    updated_by_id: int | None,
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "student_id": student_id,
        "column_id": column_id,
        "labels": labels,
        "your_value": your_value,
        "current_value": current_value,
        "updated_by_id": updated_by_id,
        "updated_at": updated_at,
    }


async def _hydrate_conflicts(
    db: AsyncSession, raw_conflicts: list[dict[str, Any]]
) -> list[ConflictOut]:
    author_ids = {c["updated_by_id"] for c in raw_conflicts if c["updated_by_id"]}
    student_ids = {c["student_id"] for c in raw_conflicts}
    authors: dict[int, str] = {}
    if author_ids:
        author_rows = (
            await db.execute(select(User.id, User.full_name).where(User.id.in_(author_ids)))
        ).all()
        authors = {row.id: row.full_name for row in author_rows}
    student_names: dict[int, str] = {}
    if student_ids:
        student_rows = (
            await db.execute(
                select(Student.id, Student.full_name).where(Student.id.in_(student_ids))
            )
        ).all()
        student_names = {row.id: row.full_name for row in student_rows}
    return [
        ConflictOut(
            student_id=c["student_id"],
            student_name=student_names.get(c["student_id"], "?"),
            column_id=c["column_id"],
            column_label=pick_label(c["labels"], "tr"),
            your_value=c["your_value"],
            current_value=c["current_value"],
            updated_by=authors.get(c["updated_by_id"]),
            updated_at=c["updated_at"],
        )
        for c in raw_conflicts
    ]


@router.get("/classes/{class_id}/grid")
async def get_grid(
    class_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    subject: Subject,
    locale: str = "tr",
    semester: int | None = None,
) -> GridOut:
    cls = await db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await db.get(AcademicYear, cls.year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    await require_subject_access(db, user, class_id, subject, allow_coordinator=True)

    semesters = list(await db.scalars(select(Semester).where(Semester.year_id == year.id)))
    if not semesters:
        raise HTTPException(409, {"code": "semester_missing"})
    current = (
        next((item for item in semesters if item.number == semester), None)
        if semester is not None
        else next((item for item in semesters if item.status == "open"), None)
    )
    current = current or (
        max(semesters, key=lambda item: item.number) if semester is None else None
    )
    if current is None:
        raise HTTPException(404, {"code": "unknown_semester"})

    columns = list(
        await db.scalars(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == current.id,
                ColumnDefinition.grade_level == cls.grade_level,
                ColumnDefinition.subject == subject,
                ColumnDefinition.is_active.is_(True),
            )
            .order_by(ColumnDefinition.position)
        )
    )
    owners = {
        row.role: row
        for row in (
            await db.execute(
                select(
                    TeachingAssignment.role,
                    User.id.label("user_id"),
                    User.full_name,
                )
                .join(User, User.id == TeachingAssignment.user_id)
                .where(TeachingAssignment.class_id == class_id)
            )
        ).all()
    }
    grants = list(
        await db.scalars(
            select(OverrideGrant).where(
                OverrideGrant.user_id == user.id,
                OverrideGrant.class_id == class_id,
                OverrideGrant.expires_at > func.now(),
            )
        )
    )

    roster_query = (
        select(Student, Enrollment.school_number)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == class_id)
        .order_by(Enrollment.school_number.asc().nulls_last(), Student.search_name)
    )
    if subject in ("german", "french"):
        roster_query = roster_query.join(
            StudentLanguage, StudentLanguage.student_id == Student.id
        ).where(
            StudentLanguage.year_id == year.id,
            StudentLanguage.language == subject,
        )
    roster_rows = list((await db.execute(roster_query)).all())
    students = [student for student, _school_number in roster_rows]

    column_ids = [column.id for column in columns]
    student_ids = [student.id for student in students]
    values = (
        list(
            await db.scalars(
                select(GradeValue).where(
                    GradeValue.column_definition_id.in_(column_ids),
                    GradeValue.student_id.in_(student_ids),
                )
            )
        )
        if column_ids and student_ids
        else []
    )
    by_type = {column.id: column.value_type for column in columns}
    cell_map = {(grade.student_id, grade.column_definition_id): grade for grade in values}

    batch_row = (
        await db.execute(
            select(SaveBatch)
            .where(SaveBatch.user_id == user.id, SaveBatch.class_id == class_id)
            .order_by(SaveBatch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_batch = None
    if batch_row is not None:
        cell_count = (
            await db.execute(
                select(func.count())
                .select_from(AuditEntry)
                .where(AuditEntry.batch_id == batch_row.id)
            )
        ).scalar_one()
        last_batch = LastBatchOut(
            id=batch_row.id,
            created_at=batch_row.created_at,
            cell_count=cell_count,
            undoable=not batch_row.undone and current.status == "open",
        )

    return GridOut(
        meta=GridMetaOut(
            class_id=class_id,
            class_name=class_label(cls.grade_level, cls.section),
            grade_level=cls.grade_level,
            subject=subject,
            year_id=year.id,
            year_label=year.label,
            semester_id=current.id,
            semester_number=current.number,
            semester_status=current.status,
            year_status=year.status,
            my_grants=[GrantOut(role=grant.role, expires_at=grant.expires_at) for grant in grants],
            my_last_batch=last_batch,
        ),
        columns=[
            GridColumnOut(
                id=column.id,
                label=pick_label(column.labels, locale),
                group=pick_label(column.group_labels, locale) if column.group_labels else None,
                value_type=column.value_type,
                owner_role=column.owner_role,
                owner_name=(
                    owners[column.owner_role].full_name if column.owner_role in owners else None
                ),
                # Active grants permit a save, but ownership remains visible so
                # every out-of-role save receives an explicit warning.
                owned_by_you=(
                    column.owner_role in owners and owners[column.owner_role].user_id == user.id
                ),
                position=column.position,
            )
            for column in columns
        ],
        rows=[
            GridRowOut(
                student_id=student.id,
                school_number=school_number,
                full_name=student.full_name,
                cells={
                    str(column_id): CellOut(
                        value=cell_value(cell_map[(student.id, column_id)], by_type[column_id]),
                        version=cell_map[(student.id, column_id)].version,
                    )
                    for column_id in column_ids
                    if (student.id, column_id) in cell_map
                },
            )
            for student, school_number in roster_rows
        ],
    )


@router.post("/classes/{class_id}/grid/save")
async def save_grid(
    class_id: int,
    body: SaveRequest,
    user: Annotated[User, Depends(current_user)],
    semester: Annotated[Semester, Depends(writable_semester)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SaveResponse:
    cls = await _writable_class(db, class_id, semester)
    await require_subject_access(db, user, class_id, body.subject, allow_coordinator=False)

    columns = {
        column.id: column
        for column in (
            await db.scalars(
                select(ColumnDefinition).where(
                    ColumnDefinition.semester_id == semester.id,
                    ColumnDefinition.grade_level == cls.grade_level,
                    ColumnDefinition.subject == body.subject,
                    ColumnDefinition.is_active.is_(True),
                )
            )
        )
    }
    roster = await _roster_ids(db, class_id, body.subject, cls.year_id)
    assignments = {
        assignment.role: assignment.user_id
        for assignment in (
            await db.scalars(
                select(TeachingAssignment).where(TeachingAssignment.class_id == class_id)
            )
        )
    }
    grants = {
        grant.role: grant.id
        for grant in (
            await db.scalars(
                select(OverrideGrant).where(
                    OverrideGrant.user_id == user.id,
                    OverrideGrant.class_id == class_id,
                    OverrideGrant.expires_at > func.now(),
                )
            )
        )
    }

    if not user.is_admin and body.confirm_outside_assignment:
        roles = {
            columns[cell.column_id].owner_role
            for cell in body.cells
            if cell.column_id in columns
            and assignments.get(columns[cell.column_id].owner_role) != user.id
        }
        for role in roles:
            grants[role], _ = await _renew_grant(db, user.id, class_id, role)

    applied: list[AppliedOut] = []
    rejected: list[RejectedOut] = []
    raw_conflicts: list[dict[str, Any]] = []
    audit_rows: list[AuditEntry] = []

    for cell in body.cells:
        column = columns.get(cell.column_id)
        code = None
        if column is None:
            code = "unknown_column"
        elif cell.student_id not in roster:
            code = "unknown_student"
        elif not _valid_value(column.value_type, cell.value):
            code = "invalid_value"
        elif (
            not user.is_admin
            and assignments.get(column.owner_role) != user.id
            and column.owner_role not in grants
            and not body.confirm_outside_assignment
        ):
            code = "outside_assignment_confirmation_required"
        if code:
            rejected.append(
                RejectedOut(student_id=cell.student_id, column_id=cell.column_id, code=code)
            )
            continue
        assert column is not None
        is_owner = user.is_admin or assignments.get(column.owner_role) == user.id
        grant_id = None if is_owner else grants.get(column.owner_role)
        fields = _value_fields(column.value_type, cell.value)
        current = (
            await db.execute(
                select(GradeValue)
                .where(
                    GradeValue.student_id == cell.student_id,
                    GradeValue.column_definition_id == cell.column_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if current is None:
            if cell.expected_version == 0 or body.force:
                statement = (
                    pg_insert(GradeValue)
                    .values(
                        student_id=cell.student_id,
                        column_definition_id=cell.column_id,
                        version=1,
                        updated_by=user.id,
                        **fields,
                    )
                    .on_conflict_do_nothing(index_elements=["student_id", "column_definition_id"])
                    .returning(GradeValue.id)
                )
                inserted = (await db.execute(statement)).first()
                if inserted:
                    applied.append(
                        AppliedOut(
                            student_id=cell.student_id,
                            column_id=cell.column_id,
                            version=1,
                        )
                    )
                    audit_rows.append(
                        AuditEntry(
                            actor_id=user.id,
                            student_id=cell.student_id,
                            column_definition_id=cell.column_id,
                            old_existed=False,
                            old_score=None,
                            old_scale=None,
                            old_text=None,
                            new_score=fields["score"],
                            new_scale=fields["scale"],
                            new_text=fields["text_value"],
                            forced=body.force and cell.expected_version != 0,
                            via_grant_id=grant_id,
                        )
                    )
                    continue
                current = (
                    await db.execute(
                        select(GradeValue)
                        .where(
                            GradeValue.student_id == cell.student_id,
                            GradeValue.column_definition_id == cell.column_id,
                        )
                        .with_for_update()
                    )
                ).scalar_one()
            else:
                raw_conflicts.append(
                    _raw_conflict(
                        student_id=cell.student_id,
                        column_id=cell.column_id,
                        labels=column.labels,
                        your_value=cell.value,
                        current_value=None,
                        updated_by_id=None,
                        updated_at=None,
                    )
                )
                continue

        if body.force or current.version == cell.expected_version:
            audit_rows.append(
                AuditEntry(
                    actor_id=user.id,
                    student_id=cell.student_id,
                    column_definition_id=cell.column_id,
                    old_existed=True,
                    old_score=current.score,
                    old_scale=current.scale,
                    old_text=current.text_value,
                    new_score=fields["score"],
                    new_scale=fields["scale"],
                    new_text=fields["text_value"],
                    forced=body.force and current.version != cell.expected_version,
                    via_grant_id=grant_id,
                )
            )
            current.score = fields["score"] if isinstance(fields["score"], int) else None
            current.scale = fields["scale"] if isinstance(fields["scale"], int) else None
            current.text_value = (
                fields["text_value"] if isinstance(fields["text_value"], str) else None
            )
            current.version += 1
            current.updated_by = user.id
            applied.append(
                AppliedOut(
                    student_id=cell.student_id,
                    column_id=cell.column_id,
                    version=current.version,
                )
            )
        else:
            raw_conflicts.append(
                _raw_conflict(
                    student_id=cell.student_id,
                    column_id=cell.column_id,
                    labels=column.labels,
                    your_value=cell.value,
                    current_value=cell_value(current, column.value_type),
                    updated_by_id=current.updated_by,
                    updated_at=current.updated_at,
                )
            )

    if applied:
        batch = SaveBatch(user_id=user.id, class_id=class_id)
        db.add(batch)
        await db.flush()
        for audit in audit_rows:
            audit.batch_id = batch.id
            db.add(audit)
    await db.commit()
    log.info(
        "grade_batch_saved",
        actor_id=user.id,
        class_id=class_id,
        batch_id=batch.id if applied else None,
        applied_count=len(applied),
        conflict_count=len(raw_conflicts),
        rejected_count=len(rejected),
    )
    if raw_conflicts:
        log.info("conflict_detected", actor_id=user.id, class_id=class_id, count=len(raw_conflicts))

    return SaveResponse(
        applied=applied,
        conflicts=await _hydrate_conflicts(db, raw_conflicts),
        rejected=rejected,
    )


@router.post("/classes/{class_id}/grants")
async def request_grant(
    class_id: int,
    body: GrantBody,
    user: Annotated[User, Depends(current_user)],
    semester: Annotated[Semester, Depends(writable_semester)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> GrantOut:
    await _writable_class(db, class_id, semester)
    subject = cast(Subject, "english" if body.role in ("main", "skills") else body.role)
    await require_subject_access(db, user, class_id, subject, allow_coordinator=False)
    assignment = (
        await db.execute(
            select(TeachingAssignment).where(
                TeachingAssignment.class_id == class_id,
                TeachingAssignment.role == body.role,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(409, {"code": "role_unassigned"})
    _, expires_at = await _renew_grant(db, user.id, class_id, body.role)
    await db.commit()
    log.info("grant_created", actor_id=user.id, class_id=class_id, role=body.role)
    return GrantOut(role=body.role, expires_at=expires_at)


def _entry_new(entry: AuditEntry) -> tuple[int | None, int | None, str | None]:
    return entry.new_score, entry.new_scale, entry.new_text


def _entry_old(entry: AuditEntry) -> tuple[int | None, int | None, str | None]:
    return entry.old_score, entry.old_scale, entry.old_text


def _grade_tuple(grade: GradeValue) -> tuple[int | None, int | None, str | None]:
    return grade.score, grade.scale, grade.text_value


def _first_value(values: tuple[int | None, int | None, str | None]) -> CellValue:
    return next((value for value in values if value is not None), None)


@router.post("/classes/{class_id}/grid/undo")
async def undo_grid(
    class_id: int,
    user: Annotated[User, Depends(current_user)],
    semester: Annotated[Semester, Depends(writable_semester)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SaveResponse:
    cls = await _writable_class(db, class_id, semester)
    batch = (
        await db.execute(
            select(SaveBatch)
            .where(SaveBatch.user_id == user.id, SaveBatch.class_id == class_id)
            .order_by(SaveBatch.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if batch is None or batch.undone:
        raise HTTPException(409, {"code": "nothing_to_undo"})
    entries = list(await db.scalars(select(AuditEntry).where(AuditEntry.batch_id == batch.id)))
    columns = {
        column.id: column
        for column in (
            await db.scalars(
                select(ColumnDefinition).where(
                    ColumnDefinition.id.in_({entry.column_definition_id for entry in entries})
                )
            )
        )
    }
    if any(
        column.semester_id != semester.id
        or column.grade_level != cls.grade_level
        or not column.is_active
        for column in columns.values()
    ):
        raise HTTPException(409, {"code": "nothing_to_undo"})
    rosters: dict[str, set[int]] = {}
    for subject in {column.subject for column in columns.values()}:
        await require_subject_access(
            db, user, class_id, cast(Subject, subject), allow_coordinator=False
        )
        rosters[subject] = await _roster_ids(db, class_id, subject, cls.year_id)
    if any(
        entry.student_id not in rosters[columns[entry.column_definition_id].subject]
        for entry in entries
    ):
        raise HTTPException(409, {"code": "nothing_to_undo"})
    applied: list[AppliedOut] = []
    raw_conflicts: list[dict[str, Any]] = []
    new_audit: list[AuditEntry] = []

    for entry in entries:
        current = (
            await db.execute(
                select(GradeValue)
                .where(
                    GradeValue.student_id == entry.student_id,
                    GradeValue.column_definition_id == entry.column_definition_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        untouched = current is not None and _grade_tuple(current) == _entry_new(entry)
        if not untouched:
            raw_conflicts.append(
                _raw_conflict(
                    student_id=entry.student_id,
                    column_id=entry.column_definition_id,
                    labels=columns[entry.column_definition_id].labels,
                    your_value=_first_value(_entry_old(entry)),
                    current_value=_first_value(_grade_tuple(current)) if current else None,
                    updated_by_id=current.updated_by if current else None,
                    updated_at=current.updated_at if current else None,
                )
            )
            continue

        assert current is not None

        new_audit.append(
            AuditEntry(
                actor_id=user.id,
                student_id=entry.student_id,
                column_definition_id=entry.column_definition_id,
                old_existed=True,
                old_score=entry.new_score,
                old_scale=entry.new_scale,
                old_text=entry.new_text,
                new_score=entry.old_score,
                new_scale=entry.old_scale,
                new_text=entry.old_text,
                forced=False,
                via_grant_id=None,
            )
        )
        if entry.old_existed:
            current.score, current.scale, current.text_value = _entry_old(entry)
            current.version += 1
            current.updated_by = user.id
            version = current.version
        else:
            await db.delete(current)
            version = 0
        applied.append(
            AppliedOut(
                student_id=entry.student_id,
                column_id=entry.column_definition_id,
                version=version,
            )
        )

    batch.undone = True
    if applied:
        undo_batch = SaveBatch(user_id=user.id, class_id=class_id, is_undo=True)
        db.add(undo_batch)
        await db.flush()
        for audit in new_audit:
            audit.batch_id = undo_batch.id
            db.add(audit)
    await db.commit()
    log.info(
        "undo_applied",
        actor_id=user.id,
        class_id=class_id,
        applied_count=len(applied),
        conflict_count=len(raw_conflicts),
    )
    return SaveResponse(
        applied=applied,
        conflicts=await _hydrate_conflicts(db, raw_conflicts),
        rejected=[],
    )
