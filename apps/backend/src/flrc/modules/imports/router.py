import hmac
import re
from collections import Counter
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.core.rate_limit import import_preview_rate_limit, import_rate_limit
from flrc.db.models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Student,
    StudentLanguage,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import (
    MAX_GRADE,
    MIN_GRADE,
    SECTION_MAX_LENGTH,
    class_label,
)
from flrc.modules.academics.programme import PLACEMENT_GRADES
from flrc.modules.administration.names import search_key
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.imports.parser import ImportPlan, InvalidWorkbook, RowModel, parse_workbook
from flrc.modules.imports.review import (
    ImportAction,
    ImportClassMove,
    ImportLanguage,
    ImportPreview,
    ImportRosterEdits,
    PreviewRow,
    apply_roster_edits,
    parse_class_moves,
    parse_roster_edits,
    preview_page,
    review_sha256,
)

router = APIRouter(prefix="/admin/import", tags=["admin-import"])
log = structlog.get_logger()
MAX_XLSX_BYTES = 10 * 1024 * 1024


async def read_limited_xlsx(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(415, {"code": "xlsx_required"})
    data = await file.read(MAX_XLSX_BYTES + 1)
    if len(data) > MAX_XLSX_BYTES:
        raise HTTPException(413, {"code": "file_too_large"})
    if not data.startswith(b"PK"):
        raise HTTPException(415, {"code": "bad_xlsx_container"})
    return data


def parse_uploaded_workbook(data: bytes) -> ImportPlan:
    try:
        return parse_workbook(data)
    except InvalidWorkbook as exc:
        raise HTTPException(422, {"code": str(exc)}) from exc


async def _year(db: AsyncSession, year_id: int, *, lock: bool = False) -> AcademicYear:
    statement = select(AcademicYear).where(AcademicYear.id == year_id)
    if lock:
        statement = statement.with_for_update()
    year = await db.scalar(statement)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    if year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    return year


async def _match_students(
    db: AsyncSession, year: AcademicYear, rows: list[RowModel]
) -> dict[int, tuple[Enrollment | None, Student | None]]:
    """Resolve identities once, with identical rules for preview and commit.

    Current school numbers take precedence. Name matches must be unique on both
    sides; workbook order must never decide which namesake inherits a history.
    Placement also requires the immediately preceding year and the next grade.
    """
    enrolled = (
        await db.execute(
            select(Enrollment, Student)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.year_id == year.id)
        )
    ).all()
    by_number = {
        enrollment.school_number: (enrollment, student)
        for enrollment, student in enrolled
        if enrollment.school_number is not None
    }
    pending: dict[str, list[tuple[Enrollment, Student]]] = {}
    for enrollment, student in enrolled:
        if enrollment.school_number is None:
            pending.setdefault(student.search_name, []).append((enrollment, student))

    awaiting: dict[tuple[int, str], list[Student]] = {}
    label = re.fullmatch(r"(\d{4})-(\d{4})", year.label)
    if label and int(label[2]) == int(label[1]) + 1:
        start = int(label[1])
        previous_label = f"{start - 1:04d}-{start:04d}"
        pupils = await db.execute(
            select(Student, SchoolClass.grade_level)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .join(AcademicYear, AcademicYear.id == Enrollment.year_id)
            .where(
                AcademicYear.label == previous_label,
                SchoolClass.grade_level.in_(PLACEMENT_GRADES),
            )
        )
        enrolled_ids = {student.id for _enrollment, student in enrolled}
        for student, grade in pupils:
            if student.id not in enrolled_ids:
                awaiting.setdefault((grade + 1, student.search_name), []).append(student)

    unnumbered = [row for row in rows if row.school_number not in by_number]
    names = Counter(search_key(row.full_name) for row in unnumbered)
    placements = Counter((row.grade_level, search_key(row.full_name)) for row in unnumbered)
    matches: dict[int, tuple[Enrollment | None, Student | None]] = {}
    for row in rows:
        match = by_number.get(row.school_number)
        if match is None:
            name = search_key(row.full_name)
            candidates = pending.get(name, [])
            if len(candidates) == 1 and names[name] == 1:
                match = candidates[0]
            else:
                key = (row.grade_level, name)
                waiting = awaiting.get(key, [])
                if not candidates and len(waiting) == 1 and placements[key] == 1:
                    match = (None, waiting[0])
        matches[row.school_number] = match or (None, None)
    return matches


async def compare_plan(
    db: AsyncSession,
    year_id: int,
    plan: ImportPlan,
    *,
    moves: list[ImportClassMove] | None = None,
    edits: ImportRosterEdits | None = None,
    offset: int = 0,
    limit: int = 100,
    q: str = "",
    grade_level: int | None = None,
    section: str | None = None,
    language: ImportLanguage | None = None,
    action: ImportAction | None = None,
) -> ImportPreview:
    year = await _year(db, year_id)
    classes = {
        (item.grade_level, item.section): item
        for item in (await db.scalars(select(SchoolClass).where(SchoolClass.year_id == year_id)))
    }
    available_classes = set(classes) | {(row.grade_level, row.section) for row in plan.rows}
    original_classes = {row.school_number: (row.grade_level, row.section) for row in plan.rows}
    moves = moves or []
    edits = edits or ImportRosterEdits()
    plan = apply_roster_edits(plan, moves, edits, available_classes)
    original_classes.update(
        {row.school_number: (row.grade_level, row.section) for row in edits.additions}
    )
    added_numbers = {row.school_number for row in edits.additions}
    language_edits = {row.school_number for row in edits.language_changes}
    matches = await _match_students(db, year, plan.rows)
    for addition in edits.additions:
        _enrollment, existing = matches.get(addition.school_number, (None, None))
        if existing and search_key(existing.full_name) != search_key(addition.full_name):
            raise HTTPException(409, {"code": "duplicate_school_number"})
    languages = {
        item.student_id: item
        for item in await db.scalars(
            select(StudentLanguage).where(StudentLanguage.year_id == year_id)
        )
    }
    counts = {
        "new_students": 0,
        "assigned_numbers": 0,
        "placed_students": 0,
        "renamed_students": 0,
        "new_classes": 0,
        "new_enrollments": 0,
        "moved_students": 0,
        "language_changes": 0,
        "unchanged": 0,
    }
    preview_rows: list[PreviewRow] = []
    seen_new_classes: set[tuple[int, str]] = set()
    for row in plan.rows:
        actions: list[str] = []
        class_key = (row.grade_level, row.section)
        if class_key not in classes and class_key not in seen_new_classes:
            counts["new_classes"] += 1
            seen_new_classes.add(class_key)
            actions.append("new_class")
        enrollment, student = matches[row.school_number]
        if student is not None:
            if enrollment is None:
                counts["placed_students"] += 1
                actions.append("placed")
            elif enrollment.school_number is None:
                counts["assigned_numbers"] += 1
                actions.append("assign_number")
        if student is None:
            counts["new_students"] += 1
            counts["new_enrollments"] += 1
            actions.extend(["new_student", "new_enrollment"])
            if row.language_present and row.language:
                counts["language_changes"] += 1
                actions.append("language_change")
        else:
            if search_key(student.full_name) != search_key(row.full_name):
                counts["renamed_students"] += 1
                actions.append("rename")
            target = classes.get(class_key)
            if enrollment is None:
                counts["new_enrollments"] += 1
                actions.append("new_enrollment")
            elif target is None or enrollment.class_id != target.id:
                counts["moved_students"] += 1
                actions.append("move")
            student_language = languages.get(student.id)
            if (
                row.language_present
                and (student_language.language if student_language else None) != row.language
            ):
                counts["language_changes"] += 1
                actions.append("language_change")
        if not actions:
            counts["unchanged"] += 1
            actions.append("unchanged")
        original = original_classes.get(row.school_number, (row.grade_level, row.section))
        if original != (row.grade_level, row.section):
            actions.append("class_changed")
        if row.school_number in added_numbers:
            actions.append("manual_added")
        if row.school_number in language_edits:
            actions.append("language_edited")
        preview_rows.append(
            PreviewRow(
                row=row,
                actions=actions,
                original_grade_level=original[0],
                original_section=original[1],
                original_class=class_label(*original),
            )
        )
    return preview_page(
        year_id=year_id,
        plan=plan,
        rows=preview_rows,
        counts=counts,
        classes=available_classes,
        moves=moves,
        edits=edits,
        offset=offset,
        limit=limit,
        q=q,
        grade_level=grade_level,
        section=section,
        language=language,
        action=action,
    )


@router.post("/dry-run", dependencies=[Depends(import_preview_rate_limit)])
async def dry_run_import(
    file: UploadFile,
    year_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    class_moves: Annotated[str, Form(max_length=1_000_000)] = "[]",
    roster_edits: Annotated[str, Form(max_length=2_000_000)] = "{}",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    q: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[int | None, Query(ge=MIN_GRADE, le=MAX_GRADE)] = None,
    section: Annotated[str | None, Query(max_length=SECTION_MAX_LENGTH)] = None,
    language: ImportLanguage | None = None,
    action: ImportAction | None = None,
) -> ImportPreview:
    data = await read_limited_xlsx(file)
    return await compare_plan(
        db,
        year_id,
        parse_uploaded_workbook(data),
        moves=parse_class_moves(class_moves),
        edits=parse_roster_edits(roster_edits),
        offset=offset,
        limit=limit,
        q=q,
        grade_level=grade_level,
        section=section,
        language=language,
        action=action,
    )


@router.post("/commit", dependencies=[Depends(import_rate_limit)])
async def commit_import(
    file: UploadFile,
    year_id: int,
    expected_sha256: str,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    class_moves: Annotated[str, Form(max_length=1_000_000)] = "[]",
    roster_edits: Annotated[str, Form(max_length=2_000_000)] = "{}",
    expected_review_sha256: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
) -> ImportPreview:
    data = await read_limited_xlsx(file)
    plan = parse_uploaded_workbook(data)
    if plan.has_errors:
        raise HTTPException(
            422, {"code": "import_has_errors", "issues": [i.model_dump() for i in plan.issues]}
        )
    if not hmac.compare_digest(plan.sha256, expected_sha256):
        raise HTTPException(409, {"code": "import_hash_mismatch"})
    moves = parse_class_moves(class_moves)
    edits = parse_roster_edits(roster_edits)
    if (
        moves or edits != ImportRosterEdits() or expected_review_sha256 is not None
    ) and not hmac.compare_digest(
        review_sha256(year_id, plan, moves, edits), expected_review_sha256 or ""
    ):
        raise HTTPException(409, {"code": "import_review_mismatch"})
    year = await _year(db, year_id, lock=True)
    preview = await compare_plan(db, year_id, plan, moves=moves, edits=edits)
    plan = apply_roster_edits(
        plan, moves, edits, {(item.grade_level, item.section) for item in preview.classes}
    )
    classes = {
        (item.grade_level, item.section): item
        for item in (await db.scalars(select(SchoolClass).where(SchoolClass.year_id == year_id)))
    }
    # The year lock serializes imports; matching stays bounded, never per row.
    matches = await _match_students(db, year, plan.rows)
    languages = {
        item.student_id: item
        for item in await db.scalars(
            select(StudentLanguage).where(StudentLanguage.year_id == year_id)
        )
    }
    for row in plan.rows:
        class_key = (row.grade_level, row.section)
        school_class = classes.get(class_key)
        if school_class is None:
            school_class = SchoolClass(
                year_id=year_id, grade_level=row.grade_level, section=row.section
            )
            db.add(school_class)
            await db.flush()
            classes[class_key] = school_class
        enrollment, student = matches[row.school_number]
        if student is None:
            student = Student(
                full_name=row.full_name,
                search_name=search_key(row.full_name),
            )
            db.add(student)
            await db.flush()
        elif search_key(student.full_name) != search_key(row.full_name):
            student.full_name = row.full_name
            student.search_name = search_key(row.full_name)
        if enrollment is None:
            db.add(
                Enrollment(
                    student_id=student.id,
                    year_id=year_id,
                    class_id=school_class.id,
                    school_number=row.school_number,
                )
            )
        else:
            enrollment.class_id = school_class.id
            enrollment.school_number = row.school_number
        if row.language_present:
            language = languages.get(student.id)
            if row.language is None and language is not None:
                await db.delete(language)
            elif row.language is not None:
                await db.execute(
                    pg_insert(StudentLanguage)
                    .values(student_id=student.id, year_id=year_id, language=row.language)
                    .on_conflict_do_update(
                        index_elements=["student_id", "year_id"],
                        set_={"language": row.language},
                    )
                )
    await db.commit()
    log.info("import_committed", actor_id=actor.id, year_id=year_id, counts=preview.counts)
    return preview
