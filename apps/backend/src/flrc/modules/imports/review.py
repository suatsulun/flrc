"""Validated roster edits and paging for the stateless workbook review."""

import hashlib
import json
from collections import Counter
from typing import Annotated, Literal, Self

from fastapi import HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from flrc.modules.academics.class_names import (
    MAX_GRADE,
    MIN_GRADE,
    SECTION_MAX_LENGTH,
    normalize_section,
)
from flrc.modules.academics.programme import L2_START_GRADE, stage_for_grade
from flrc.modules.administration.names import search_key
from flrc.modules.imports.parser import ImportIssue, ImportPlan, RowModel

ImportAction = Literal[
    "new_student",
    "placed",
    "rename",
    "move",
    "class_changed",
    "language_change",
    "unchanged",
    "manual_added",
    "language_edited",
]
ImportLanguage = Literal["german", "french", "none"]


class ImportClassTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade_level: int = Field(ge=MIN_GRADE, le=MAX_GRADE)
    section: str = Field(min_length=1, max_length=SECTION_MAX_LENGTH)

    @model_validator(mode="after")
    def canonical_section(self) -> Self:
        self.section = normalize_section(self.grade_level, self.section)
        if not self.section:
            raise ValueError("invalid_section")
        return self


class ImportClassMove(ImportClassTarget):
    row_key: str = Field(pattern=r"^(primary|middle):[1-9][0-9]*$")


class ImportStudentAdd(ImportClassTarget):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    language: Literal["german", "french"] | None = None

    @property
    def row_key(self) -> str:
        return f"{stage_for_grade(self.grade_level)}:{self.school_number}"

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("invalid_name")
        return value


class ImportLanguageChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_key: str = Field(pattern=r"^(primary|middle):[1-9][0-9]*$")
    language: Literal["german", "french"] | None


class ImportRosterEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    additions: list[ImportStudentAdd] = Field(default_factory=list, max_length=5000)
    removed_row_keys: list[Annotated[str, Field(pattern=r"^(primary|middle):[1-9][0-9]*$")]] = (
        Field(default_factory=list, max_length=10000)
    )
    language_changes: list[ImportLanguageChange] = Field(default_factory=list, max_length=10000)


class PreviewRow(BaseModel):
    row: RowModel
    actions: list[str]
    original_grade_level: int
    original_section: str
    # The display label of the original class, for messages.
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
    rows = {row.row_key: row for row in plan.rows}
    for addition in edits.additions:
        if addition.row_key in rows:
            raise HTTPException(409, {"code": "duplicate_school_number"})
        if (addition.grade_level, addition.section) not in classes:
            raise HTTPException(422, {"code": "invalid_import_class"})
        if addition.language and addition.grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        rows[addition.row_key] = RowModel(
            **addition.model_dump(),
            row_key=addition.row_key,
            language_present=True,
            sheet="",
            row_number=0,
        )
    plan = apply_class_moves(plan.model_copy(update={"rows": list(rows.values())}), moves, classes)
    rows = {row.row_key: row for row in plan.rows}
    seen: set[str] = set()
    for change in edits.language_changes:
        if change.row_key in seen or change.row_key not in rows:
            raise HTTPException(422, {"code": "invalid_import_student"})
        seen.add(change.row_key)
        if change.language and rows[change.row_key].grade_level < L2_START_GRADE:
            raise HTTPException(422, {"code": "language_grade_too_low"})
        rows[change.row_key] = rows[change.row_key].model_copy(
            update={"language": change.language, "language_present": True}
        )
    removed = set(edits.removed_row_keys)
    if len(removed) != len(edits.removed_row_keys) or not removed.issubset(rows):
        raise HTTPException(422, {"code": "invalid_import_student"})
    remaining = [row for key, row in rows.items() if key not in removed]
    # Class overrides use model_copy, so recheck the final placement after language edits.
    if any(row.language and row.grade_level < L2_START_GRADE for row in remaining):
        raise HTTPException(422, {"code": "language_grade_too_low"})
    destinations = [(stage_for_grade(row.grade_level), row.school_number) for row in remaining]
    if len(set(destinations)) != len(destinations):
        raise HTTPException(409, {"code": "duplicate_school_number"})
    return plan.model_copy(update={"rows": remaining})


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
    rows = {row.row_key: row for row in plan.rows}
    seen: set[str] = set()
    for move in moves:
        if move.row_key in seen or move.row_key not in rows:
            raise HTTPException(422, {"code": "invalid_import_student"})
        if (move.grade_level, move.section) not in classes:
            raise HTTPException(422, {"code": "invalid_import_class"})
        seen.add(move.row_key)
        # Source identity remains stable even when placement crosses the stage boundary.
        rows[move.row_key] = rows[move.row_key].model_copy(
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
        "class_moves": [
            move.model_dump() for move in sorted(moves, key=lambda x: row_order(x.row_key))
        ],
    }
    if edits and edits != ImportRosterEdits():
        payload["roster_edits"] = {
            "additions": [
                row.model_dump()
                for row in sorted(edits.additions, key=lambda x: row_order(x.row_key))
            ],
            "removed_row_keys": sorted(edits.removed_row_keys, key=row_order),
            "language_changes": [
                row.model_dump()
                for row in sorted(edits.language_changes, key=lambda x: row_order(x.row_key))
            ],
        }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def row_order(row_key: str) -> tuple[str, int]:
    stage, number = row_key.split(":", 1)
    return stage, int(number)


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
        and (section is None or search_key(item.row.section) == search_key(section))
        and (language is None or (item.row.language or "none") == language)
        and (action is None or action in item.actions)
    ]
    # Stable order across pages, independent of workbook sheet order and class edits.
    filtered.sort(key=lambda item: row_order(item.row.row_key))
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
