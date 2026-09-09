"""Validated roster edits and paging for the stateless workbook review."""

import hashlib
import json
from collections import Counter
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from flrc.modules.academics.programme import L2_START_GRADE
from flrc.modules.administration.names import search_key
from flrc.modules.imports.parser import ImportIssue, ImportPlan, RowModel

ImportAction = Literal[
    "new_student",
    "rename",
    "move",
    "class_changed",
    "language_change",
    "unchanged",
    "manual_added",
    "language_edited",
]
ImportLanguage = Literal["german", "french", "none"]


class ImportClassMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_number: int = Field(gt=0)
    grade_level: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=8)

    @field_validator("section")
    @classmethod
    def uppercase_section(cls, value: str) -> str:
        return value.upper()


class ImportStudentAdd(ImportClassMove):
    full_name: str = Field(min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("invalid_name")
        return value


class ImportLanguageChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_number: int = Field(gt=0)
    language: Literal["german", "french"] | None


class ImportRosterEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    additions: list[ImportStudentAdd] = Field(default_factory=list, max_length=5000)
    removed_school_numbers: list[int] = Field(default_factory=list, max_length=10000)
    language_changes: list[ImportLanguageChange] = Field(default_factory=list, max_length=10000)


class PreviewRow(BaseModel):
    row: RowModel
    actions: list[str]
    original_class: str


class PreviewClass(BaseModel):
    grade_level: int
    section: str
    count: int


class ImportPreview(BaseModel):
    sha256: str
    review_sha256: str
    counts: dict[str, int]
    issues: list[ImportIssue]
    rows: list[PreviewRow]
    total_rows: int
    filtered_rows: int
    next_offset: int | None
    classes: list[PreviewClass]
    class_moves: list[ImportClassMove]
    roster_edits: ImportRosterEdits = Field(default_factory=ImportRosterEdits)


def parse_roster_edits(value: str) -> ImportRosterEdits:
    try:
        return ImportRosterEdits.model_validate_json(value)
    except ValidationError as exc:
        raise HTTPException(422, {"code": "invalid_import_roster_edits"}) from exc


def apply_roster_edits(
    plan: ImportPlan,
    moves: list[ImportClassMove],
    edits: ImportRosterEdits,
    classes: set[tuple[int, str]],
) -> ImportPlan:
    rows = {row.school_number: row for row in plan.rows}
    for addition in edits.additions:
        if addition.school_number in rows:
            raise HTTPException(422, {"code": "duplicate_school_number"})
        if (addition.grade_level, addition.section) not in classes:
            raise HTTPException(422, {"code": "invalid_import_class"})
        if addition.language and addition.grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        rows[addition.school_number] = RowModel(
            **addition.model_dump(), language_present=True, sheet="", row_number=0
        )
    plan = apply_class_moves(plan.model_copy(update={"rows": list(rows.values())}), moves, classes)
    rows = {row.school_number: row for row in plan.rows}
    seen: set[int] = set()
    for change in edits.language_changes:
        if change.school_number in seen or change.school_number not in rows:
            raise HTTPException(422, {"code": "invalid_import_student"})
        seen.add(change.school_number)
        if change.language and rows[change.school_number].grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        rows[change.school_number] = rows[change.school_number].model_copy(
            update={"language": change.language, "language_present": True}
        )
    removed = set(edits.removed_school_numbers)
    if len(removed) != len(edits.removed_school_numbers) or not removed.issubset(rows):
        raise HTTPException(422, {"code": "invalid_import_student"})
    return plan.model_copy(
        update={"rows": [row for number, row in rows.items() if number not in removed]}
    )


def parse_class_moves(value: str) -> list[ImportClassMove]:
    try:
        return TypeAdapter(list[ImportClassMove]).validate_json(value)
    except ValidationError as exc:
        # Do not echo request contents (which may contain student data).
        raise HTTPException(422, {"code": "invalid_import_class_moves"}) from exc


def apply_class_moves(
    plan: ImportPlan,
    moves: list[ImportClassMove],
    classes: set[tuple[int, str]],
) -> ImportPlan:
    rows = {row.school_number: row for row in plan.rows}
    seen: set[int] = set()
    for move in moves:
        if move.school_number in seen or move.school_number not in rows:
            raise HTTPException(422, {"code": "invalid_import_student"})
        if (move.grade_level, move.section) not in classes:
            raise HTTPException(422, {"code": "invalid_import_class"})
        seen.add(move.school_number)
        # This override changes only placement; other edits have their own typed validation.
        rows[move.school_number] = rows[move.school_number].model_copy(
            update={"grade_level": move.grade_level, "section": move.section}
        )
    return plan.model_copy(update={"rows": list(rows.values())})


def review_sha256(
    year_id: int,
    plan: ImportPlan,
    moves: list[ImportClassMove],
    edits: ImportRosterEdits | None = None,
) -> str:
    payload: dict[str, object] = {
        "year_id": year_id,
        "file_sha256": plan.sha256,
        "class_moves": [move.model_dump() for move in sorted(moves, key=lambda x: x.school_number)],
    }
    if edits and edits != ImportRosterEdits():
        payload["roster_edits"] = {
            "additions": [
                row.model_dump() for row in sorted(edits.additions, key=lambda x: x.school_number)
            ],
            "removed_school_numbers": sorted(edits.removed_school_numbers),
            "language_changes": [
                row.model_dump()
                for row in sorted(edits.language_changes, key=lambda x: x.school_number)
            ],
        }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def preview_page(
    *,
    year_id: int,
    plan: ImportPlan,
    rows: list[PreviewRow],
    counts: dict[str, int],
    classes: set[tuple[int, str]],
    moves: list[ImportClassMove],
    edits: ImportRosterEdits | None = None,
    offset: int = 0,
    limit: int = 100,
    q: str = "",
    grade_level: int | None = None,
    section: str | None = None,
    language: ImportLanguage | None = None,
    action: ImportAction | None = None,
) -> ImportPreview:
    needle = search_key(q.strip())
    class_counts = Counter((item.row.grade_level, item.row.section) for item in rows)
    filtered = [
        item
        for item in rows
        if (
            not needle
            or needle in search_key(item.row.full_name)
            or needle in str(item.row.school_number)
        )
        and (grade_level is None or item.row.grade_level == grade_level)
        and (section is None or item.row.section == section.upper())
        and (language is None or (item.row.language or "none") == language)
        and (action is None or action in item.actions)
    ]
    # Stable order across pages, independent of workbook sheet order and class edits.
    filtered.sort(key=lambda item: item.row.school_number)
    next_offset = offset + limit if offset + limit < len(filtered) else None
    return ImportPreview(
        sha256=plan.sha256,
        review_sha256=review_sha256(year_id, plan, moves, edits),
        counts=counts,
        issues=plan.issues,
        rows=filtered[offset : offset + limit],
        total_rows=len(rows),
        filtered_rows=len(filtered),
        next_offset=next_offset,
        classes=[
            PreviewClass(grade_level=grade, section=section, count=class_counts[(grade, section)])
            for grade, section in sorted(classes)
        ],
        class_moves=moves,
        roster_edits=edits or ImportRosterEdits(),
    )
