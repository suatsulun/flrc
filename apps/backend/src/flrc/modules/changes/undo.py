"""Restoring the state before an administrative action (ADR-075).

Each handler checks that the data still looks the way the action left it and
that the previous state is valid today, using the same rules as the original
endpoints. A handler raises ``UndoBlocked`` (or a reused rule's
``HTTPException``) before or instead of writing anything it cannot finish; the
caller rolls the whole transaction back, so an undo never applies partially.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    AdminAction,
    AuditEntry,
    ColumnDefinition,
    DemoVisitor,
    Enrollment,
    GradeValue,
    JobRun,
    OverrideGrant,
    ReportIdentityAudit,
    SaveBatch,
    SchoolClass,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.columns import (
    apply_column_patch,
    column_has_grades,
    column_has_history,
    column_state,
    editable_semester,
    reorder_scope_ids,
)
from flrc.modules.academics.fields import field_name
from flrc.modules.academics.programme import L2_START_GRADE, stage_for_grade
from flrc.modules.administration.classes import (
    apply_assignment_slots,
    assignment_mismatch,
    class_conflict,
    class_in_use,
    lock_class,
    stage_number_clash,
    writable_class_year,
)
from flrc.modules.administration.names import search_key
from flrc.modules.administration.report_identity import audit_identity, identity_snapshot
from flrc.modules.administration.roster_service import (
    assign_student_language,
    delete_enrollment,
    lock_enrollments,
    move_students,
    school_number_holder,
    student_language,
)
from flrc.modules.administration.users import (
    account_state,
    ensure_admin_remains,
    ensure_assignments_fit,
    lock_account_for_edit,
)
from flrc.modules.auth import demo
from flrc.modules.changes.service import ActionKind, UndoBlocked


@dataclass
class UndoContext:
    db: AsyncSession
    action: AdminAction
    actor: User
    # Accounts the undo deactivated; their sessions are revoked after the commit.
    revoke_user_ids: list[int] = field(default_factory=list)

    @property
    def data(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.action.undo_data)

    @property
    def params(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.action.summary.get("params", {}))


Handler = Callable[[UndoContext], Awaitable[None]]
HANDLERS: dict[str, Handler] = {}


def handles(*kinds: ActionKind) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        for kind in kinds:
            HANDLERS[kind] = handler
        return handler

    return register


def _class_name(school_class: SchoolClass) -> str:
    return class_label(school_class.grade_level, school_class.section)


async def _enrollment(db: AsyncSession, student_id: int, year_id: int) -> Enrollment | None:
    locked = await lock_enrollments(db, year_id=year_id, student_ids=[student_id])
    return locked[0] if locked else None


async def _student_is_referenced(db: AsyncSession, student_id: int) -> bool:
    for statement in (
        select(Enrollment.id).where(Enrollment.student_id == student_id),
        select(StudentLanguage.id).where(StudentLanguage.student_id == student_id),
        select(GradeValue.id).where(GradeValue.student_id == student_id),
        select(AuditEntry.id).where(AuditEntry.student_id == student_id),
    ):
        if await db.scalar(statement.limit(1)) is not None:
            return True
    return False


# Students -------------------------------------------------------------------


@handles("student.add")
async def _undo_student_add(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    await writable_class_year(db, data["year_id"])
    enrollment = await _enrollment(db, data["student_id"], data["year_id"])
    if enrollment is None:
        raise UndoBlocked("target_missing", student=ctx.params.get("student"))
    # Ordinary removal: grades and audit rows stay with the person. A pupil who
    # never got any is deleted, as before the action.
    await delete_enrollment(db, enrollment)
    if not await _student_is_referenced(db, data["student_id"]):
        student = await db.get(Student, data["student_id"])
        if student is not None:
            await db.delete(student)


@handles("student.remove")
async def _undo_student_remove(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    year = await writable_class_year(db, data["year_id"])
    student = await db.get(Student, data["student_id"])
    if student is None:
        raise UndoBlocked("target_missing", student=ctx.params.get("student"))
    school_class = await db.get(SchoolClass, data["class_id"])
    if school_class is None or school_class.year_id != year.id:
        raise UndoBlocked("target_missing", **{"class": ctx.params.get("class")})
    existing = await _enrollment(db, student.id, year.id)
    if existing is not None:
        current = await db.get(SchoolClass, existing.class_id)
        raise UndoBlocked(
            "enrollment_exists",
            student=student.full_name,
            **{"class": _class_name(current) if current else None},
        )
    number = data["school_number"]
    if number is None and year.status != "setup":
        raise UndoBlocked("student_number_required", student=student.full_name)
    if number is not None:
        holder = await school_number_holder(
            db,
            year_id=year.id,
            stage=stage_for_grade(school_class.grade_level),
            school_number=number,
        )
        if holder is not None:
            raise UndoBlocked("school_number_taken", **holder)
    language = data["language"]
    if language is not None and school_class.grade_level < L2_START_GRADE:
        raise UndoBlocked(
            "language_grade_too_low",
            student=student.full_name,
            **{"class": _class_name(school_class)},
        )
    db.add(
        Enrollment(
            student_id=student.id,
            year_id=year.id,
            class_id=school_class.id,
            school_number=number,
        )
    )
    await db.flush()
    await assign_student_language(db, student_id=student.id, year_id=year.id, language=language)


@handles("student.move")
async def _undo_student_move(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    await writable_class_year(db, data["year_id"])
    moved: list[dict[str, Any]] = data["moved"]
    if not moved:
        return
    student_ids = [item["student_id"] for item in moved]
    enrollments = {
        item.student_id: item
        for item in await lock_enrollments(db, year_id=data["year_id"], student_ids=student_ids)
    }
    names = dict(
        (
            await db.execute(
                select(Student.id, Student.full_name).where(Student.id.in_(student_ids))
            )
        ).all()
    )
    sources = {
        item.id: item
        for item in await db.scalars(
            select(SchoolClass).where(SchoolClass.id.in_({item["from_class_id"] for item in moved}))
        )
    }
    for item in moved:
        enrollment = enrollments.get(item["student_id"])
        name = names.get(item["student_id"])
        if enrollment is None:
            raise UndoBlocked("target_missing", student=name)
        if enrollment.class_id != data["target_class_id"]:
            current = await db.get(SchoolClass, enrollment.class_id)
            raise UndoBlocked(
                "changed_since",
                student=name,
                **{"class": _class_name(current) if current else None},
            )
        source = sources.get(item["from_class_id"])
        if source is None or source.year_id != data["year_id"]:
            raise UndoBlocked("target_missing", **{"class": item.get("from_class")})
        stage = stage_for_grade(source.grade_level)
        if enrollment.stage != stage and enrollment.school_number is not None:
            holder = await school_number_holder(
                db,
                year_id=data["year_id"],
                stage=stage,
                school_number=enrollment.school_number,
                except_enrollment_ids=[entry.id for entry in enrollments.values()],
            )
            if holder is not None:
                raise UndoBlocked("school_number_taken", **holder)
    groups: dict[int, list[int]] = {}
    for item in moved:
        groups.setdefault(item["from_class_id"], []).append(item["student_id"])
    for class_id, ids in groups.items():
        try:
            await move_students(
                db, student_ids=ids, target_class=sources[class_id], allow_grade_change=True
            )
        except ValueError as exc:
            raise UndoBlocked(str(exc)) from exc
        await db.flush()


@handles("student.edit")
async def _undo_student_edit(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    year = await writable_class_year(db, data["year_id"])
    student = await db.get(
        Student, data["student_id"], with_for_update=True, populate_existing=True
    )
    enrollment = await _enrollment(db, data["student_id"], year.id)
    if student is None or enrollment is None:
        raise UndoBlocked("target_missing", student=ctx.params.get("student"))
    school_class = await db.get(SchoolClass, enrollment.class_id)
    assert school_class is not None
    before: dict[str, Any] = data["before"]
    current = {
        "full_name": student.full_name,
        "school_number": enrollment.school_number,
        "language": await student_language(db, student.id, year.id),
    }
    if any(current[key] != value for key, value in data["after"].items()):
        raise UndoBlocked(
            "changed_since", student=student.full_name, **{"class": _class_name(school_class)}
        )
    if "school_number" in before:
        number = before["school_number"]
        if number is None and year.status != "setup":
            raise UndoBlocked("student_number_required", student=student.full_name)
        if number is not None:
            holder = await school_number_holder(
                db,
                year_id=year.id,
                stage=enrollment.stage,
                school_number=number,
                except_enrollment_ids=[enrollment.id],
            )
            if holder is not None:
                raise UndoBlocked("school_number_taken", **holder)
    if before.get("language") is not None and school_class.grade_level < L2_START_GRADE:
        raise UndoBlocked(
            "language_grade_too_low",
            student=student.full_name,
            **{"class": _class_name(school_class)},
        )
    if "school_number" in before:
        enrollment.school_number = before["school_number"]
    if "full_name" in before:
        student.full_name = before["full_name"]
        student.search_name = search_key(student.full_name)
    if "language" in before:
        await assign_student_language(
            db, student_id=student.id, year_id=year.id, language=before["language"]
        )


@handles("student.language")
async def _undo_student_language(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    year = await writable_class_year(db, data["year_id"])
    before: list[dict[str, Any]] = data["before"]
    student_ids = [item["student_id"] for item in before]
    # The same enrollment locks ordinary language writes take, held until the commit:
    # the check below and the restore see one state.
    enrollments = {
        item.student_id: item
        for item in await lock_enrollments(db, year_id=year.id, student_ids=student_ids)
    }
    names = dict(
        (
            await db.execute(
                select(Student.id, Student.full_name).where(Student.id.in_(student_ids))
            )
        ).all()
    )
    current = dict(
        (
            await db.execute(
                select(StudentLanguage.student_id, StudentLanguage.language).where(
                    StudentLanguage.year_id == year.id,
                    StudentLanguage.student_id.in_(student_ids),
                )
            )
        ).all()
    )
    grades = dict(
        (
            await db.execute(
                select(SchoolClass.id, SchoolClass.grade_level).where(
                    SchoolClass.id.in_({item.class_id for item in enrollments.values()})
                )
            )
        ).all()
    )
    for item in before:
        name = names.get(item["student_id"])
        enrollment = enrollments.get(item["student_id"])
        if enrollment is None:
            raise UndoBlocked("target_missing", student=name)
        if current.get(item["student_id"]) != data["language"]:
            raise UndoBlocked("changed_since", student=name)
        if item["language"] is not None and grades[enrollment.class_id] < L2_START_GRADE:
            raise UndoBlocked("language_grade_too_low", student=name)
    for item in before:
        await assign_student_language(
            db, student_id=item["student_id"], year_id=year.id, language=item["language"]
        )


# Classes --------------------------------------------------------------------


async def _locked_class(ctx: UndoContext, class_id: int) -> SchoolClass:
    if await ctx.db.get(SchoolClass, class_id) is None:
        raise UndoBlocked("target_missing", **{"class": ctx.params.get("class")})
    school_class, _ = await lock_class(ctx.db, class_id)
    return school_class


@handles("class.create")
async def _undo_class_create(ctx: UndoContext) -> None:
    db = ctx.db
    school_class = await _locked_class(ctx, ctx.data["class_id"])
    if await class_in_use(db, school_class.id):
        raise UndoBlocked("class_in_use", **{"class": _class_name(school_class)})
    await db.delete(school_class)


@handles("class.edit")
async def _undo_class_edit(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    school_class = await _locked_class(ctx, data["class_id"])
    after, before = data["after"], data["before"]
    if (school_class.grade_level, school_class.section) != (
        after["grade_level"],
        after["section"],
    ):
        raise UndoBlocked("changed_since", **{"class": _class_name(school_class)})
    if await class_conflict(
        db,
        year_id=school_class.year_id,
        grade_level=before["grade_level"],
        section=before["section"],
        class_id=school_class.id,
    ):
        raise UndoBlocked(
            "duplicate_class", **{"class": class_label(before["grade_level"], before["section"])}
        )
    holder = await stage_number_clash(db, school_class, before["grade_level"])
    if holder is not None:
        raise UndoBlocked("school_number_taken", **holder)
    school_class.grade_level, school_class.section = before["grade_level"], before["section"]
    await db.flush()


@handles("class.delete")
async def _undo_class_delete(ctx: UndoContext) -> None:
    db = ctx.db
    snapshot: dict[str, Any] = ctx.data["class"]
    await writable_class_year(db, snapshot["year_id"])
    label = class_label(snapshot["grade_level"], snapshot["section"])
    if await class_conflict(
        db,
        year_id=snapshot["year_id"],
        grade_level=snapshot["grade_level"],
        section=snapshot["section"],
        class_id=None,
    ):
        raise UndoBlocked("duplicate_class", **{"class": label})
    # The same id, so every later action that refers to the class still finds it.
    db.add(SchoolClass(**snapshot))
    await db.flush()


# Fields ---------------------------------------------------------------------


async def _column(ctx: UndoContext, column_id: int) -> ColumnDefinition:
    column = await ctx.db.get(
        ColumnDefinition, column_id, with_for_update=True, populate_existing=True
    )
    if column is None:
        raise UndoBlocked("target_missing", field=ctx.params.get("field"))
    await editable_semester(ctx.db, column.semester_id)
    return column


async def _ensure_unused(db: AsyncSession, column: ColumnDefinition) -> None:
    """Refuse removing an added field that holds grades or grade history; history stays."""
    name = field_name(column.labels, column.subject)
    if await column_has_grades(db, column.id):
        raise UndoBlocked("field_has_grades", field=name)
    if await column_has_history(db, column.id):
        raise UndoBlocked("field_has_history", field=name)


@handles("field.create")
async def _undo_field_create(ctx: UndoContext) -> None:
    column = await _column(ctx, ctx.data["column_id"])
    await _ensure_unused(ctx.db, column)
    await ctx.db.delete(column)


@handles("field.delete")
async def _undo_field_delete(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    if data["disabled"]:
        column = await _column(ctx, data["column_id"])
        if column.is_active:
            raise UndoBlocked("changed_since", field=field_name(column.labels, column.subject))
        column.is_active = data["was_active"]
        return
    snapshot: dict[str, Any] = data["column"]
    await editable_semester(db, snapshot["semester_id"])
    scope = (
        ColumnDefinition.semester_id == snapshot["semester_id"],
        ColumnDefinition.grade_level == snapshot["grade_level"],
        ColumnDefinition.subject == snapshot["subject"],
    )
    # Fields added since may hold its place; they move one step back so it returns there.
    taken = await db.scalar(
        select(ColumnDefinition.id).where(*scope, ColumnDefinition.position == snapshot["position"])
    )
    if taken is not None:
        await db.execute(
            update(ColumnDefinition)
            .where(*scope, ColumnDefinition.position >= snapshot["position"])
            .values(position=ColumnDefinition.position + 1)
        )
    db.add(ColumnDefinition(**snapshot))
    await db.flush()


@handles("field.edit")
async def _undo_field_edit(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    column = await _column(ctx, data["column_id"])
    name = field_name(column.labels, column.subject)
    current = column_state(column)
    if any(current[key] != value for key, value in data["after"].items()):
        raise UndoBlocked("changed_since", field=name)
    before: dict[str, Any] = data["before"]
    if "value_type" in before and await column_has_grades(db, column.id):
        raise UndoBlocked("field_has_grades", field=name)
    await apply_column_patch(db, column, before)


@handles("field.reorder")
async def _undo_field_reorder(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    await editable_semester(db, data["semester_id"])
    after = {int(column_id): position for column_id, position in data["after"]}
    params = {"grade_level": data["grade_level"], "subject": data["subject"]}
    scope = await reorder_scope_ids(db, data["semester_id"], data["grade_level"], data["subject"])
    if scope != set(after):
        raise UndoBlocked("order_changed", **params)
    columns = {
        item.id: item
        for item in await db.scalars(
            select(ColumnDefinition)
            .where(ColumnDefinition.id.in_(after))
            .order_by(ColumnDefinition.id)
            # Positions only, as in the reorder itself: no wait on grade saves' key-share locks.
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    }
    # A field deleted after the scope was read is missing from the locked rows.
    if columns.keys() != after.keys() or any(
        columns[column_id].position != position for column_id, position in after.items()
    ):
        raise UndoBlocked("order_changed", **params)
    for column_id, position in data["before"]:
        columns[int(column_id)].position = position


@handles("field.copy")
async def _undo_field_copy(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    await editable_semester(db, data["semester_id"])
    column_ids: list[int] = data["column_ids"]
    columns = list(
        await db.scalars(
            select(ColumnDefinition)
            .where(ColumnDefinition.id.in_(column_ids))
            .order_by(ColumnDefinition.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(columns) != len(column_ids):
        raise UndoBlocked("changed_since", count=len(column_ids))
    for column in columns:
        await _ensure_unused(db, column)
    for column in columns:
        await db.delete(column)


# Accounts -------------------------------------------------------------------


async def _user(ctx: UndoContext, user_id: int) -> User:
    user = await lock_account_for_edit(ctx.db, user_id, ctx.actor)
    if user is None:
        raise UndoBlocked("target_missing", user=ctx.params.get("user"))
    if user.id != ctx.actor.id and await demo.is_visitor(ctx.db, user.id):
        raise UndoBlocked("visitor_protected", user=user.full_name)
    return user


async def _user_in_use(db: AsyncSession, user: User) -> bool:
    """Whether removing the account would lose sign-ins, work, history or assignments."""
    if user.google_subject is not None or user.signature_digest or user.report_name:
        return True
    for statement in (
        select(TeachingAssignment.id).where(TeachingAssignment.user_id == user.id),
        select(GradeValue.id).where(GradeValue.updated_by == user.id),
        select(AuditEntry.id).where(AuditEntry.actor_id == user.id),
        select(SaveBatch.id).where(SaveBatch.user_id == user.id),
        select(OverrideGrant.id).where(OverrideGrant.user_id == user.id),
        select(JobRun.id).where(JobRun.requested_by == user.id),
        select(ReportIdentityAudit.id).where(
            (ReportIdentityAudit.user_id == user.id) | (ReportIdentityAudit.actor_id == user.id)
        ),
        select(AdminAction.id).where(
            (AdminAction.actor_id == user.id) | (AdminAction.undone_by == user.id)
        ),
        select(DemoVisitor.user_id).where(DemoVisitor.user_id == user.id),
    ):
        if await db.scalar(statement.limit(1)) is not None:
            return True
    return False


@handles("user.create")
async def _undo_user_create(ctx: UndoContext) -> None:
    user = await _user(ctx, ctx.data["user_id"])
    if await _user_in_use(ctx.db, user):
        raise UndoBlocked("user_in_use", user=user.full_name)
    await ctx.db.delete(user)


@handles("user.edit")
async def _undo_user_edit(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    target = await _user(ctx, data["user_id"])
    current = account_state(target)
    if any(current[key] != value for key, value in data["after"].items()):
        raise UndoBlocked("changed_since", user=target.full_name)
    before: dict[str, Any] = data["before"]
    restored = {**current, **before}
    if not restored["is_active"] and target.id == ctx.actor.id:
        raise UndoBlocked("cannot_deactivate_self", user=target.full_name)
    await ensure_admin_remains(
        db, target, is_admin=bool(restored["is_admin"]), is_active=bool(restored["is_active"])
    )
    if "teaching_field" in before or "teaching_stage" in before:
        await ensure_assignments_fit(
            db, target.id, str(restored["teaching_field"]), restored["teaching_stage"]
        )
    subject = before.get("google_subject")
    if subject is not None and await db.scalar(
        select(User.id).where(User.google_subject == subject, User.id != target.id)
    ):
        raise UndoBlocked("google_identity_taken", user=target.full_name)
    before_identity = identity_snapshot(target)
    for name, value in before.items():
        setattr(target, name, value)
    audit_identity(db, target, ctx.actor, before_identity)
    if current["is_active"] and not target.is_active:
        ctx.revoke_user_ids.append(target.id)


@handles("signature.upload", "signature.delete")
async def _undo_signature(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    target = await _user(ctx, data["user_id"])
    if target.signature_digest != data["after_digest"]:
        raise UndoBlocked("changed_since", user=target.full_name)
    kept = await db.scalar(select(AdminAction.blob).where(AdminAction.id == ctx.action.id))
    before_identity = identity_snapshot(target)
    target.signature_png = kept
    target.signature_digest = data["before_digest"]
    audit_identity(db, target, ctx.actor, before_identity)


# Assignments ----------------------------------------------------------------


@handles("assignments.replace")
async def _undo_assignments(ctx: UndoContext) -> None:
    db, data = ctx.db, ctx.data
    await writable_class_year(db, data["year_id"])
    slots: list[dict[str, Any]] = data["slots"]
    class_ids = {item["class_id"] for item in slots}
    classes = {
        item.id: item
        for item in await db.scalars(select(SchoolClass).where(SchoolClass.id.in_(class_ids)))
    }
    current = {
        (item.class_id, item.role): item.user_id
        for item in await db.scalars(
            select(TeachingAssignment)
            .where(TeachingAssignment.class_id.in_(class_ids))
            .with_for_update()
        )
    }
    teachers = {
        item.id: item
        for item in await db.scalars(
            select(User).where(
                User.id.in_({item["before"] for item in slots if item["before"] is not None})
            )
        )
    }
    for item in slots:
        school_class = classes.get(item["class_id"])
        if school_class is None:
            raise UndoBlocked("target_missing", role=item["role"])
        where = {"class": _class_name(school_class), "role": item["role"]}
        if current.get((item["class_id"], item["role"])) != item["after"]:
            raise UndoBlocked("changed_since", **where)
        if item["before"] is None:
            continue
        teacher = teachers.get(item["before"])
        if teacher is None:
            raise UndoBlocked("target_missing", **where)
        if not teacher.is_active:
            raise UndoBlocked("teacher_inactive", teacher=teacher.full_name, **where)
        problem = assignment_mismatch(
            teacher.teaching_field, teacher.teaching_stage, school_class.grade_level, item["role"]
        )
        if problem is not None:
            raise UndoBlocked(problem, teacher=teacher.full_name, **where)
    await apply_assignment_slots(
        db, {(item["class_id"], item["role"]): item["before"] for item in slots}
    )
