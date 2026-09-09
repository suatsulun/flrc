import csv
import io
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.core.rate_limit import export_rate_limit
from flrc.core.spreadsheets import safe_spreadsheet_cell
from flrc.db.models import AuditEntry, ColumnDefinition, SaveBatch, Student, User
from flrc.db.session import get_session
from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/audit", tags=["audit"])
PAGE_SIZE = 50


def _rendered(score: int | None, scale: int | None, text: str | None) -> str | None:
    for candidate in (score, scale, text):
        if candidate is not None:
            return str(candidate)
    return None


class AuditItemOut(BaseModel):
    id: int
    created_at: datetime
    class_id: int
    actor: str
    student: str
    column_label: str
    old_value: str | None
    new_value: str | None
    old_existed: bool
    forced: bool
    via_grant: bool


class AuditPageOut(BaseModel):
    items: list[AuditItemOut]
    next_cursor: int | None


def _base_query(
    class_id: int | None,
    actor_id: int | None,
    student_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[Any]:
    query = (
        select(
            AuditEntry,
            SaveBatch.class_id,
            User.full_name.label("actor"),
            Student.full_name.label("student"),
            ColumnDefinition.labels,
        )
        .join(SaveBatch, SaveBatch.id == AuditEntry.batch_id)
        .join(User, User.id == AuditEntry.actor_id)
        .join(Student, Student.id == AuditEntry.student_id)
        .join(ColumnDefinition, ColumnDefinition.id == AuditEntry.column_definition_id)
        .order_by(AuditEntry.id.desc())
    )
    if class_id is not None:
        query = query.where(SaveBatch.class_id == class_id)
    if actor_id is not None:
        query = query.where(AuditEntry.actor_id == actor_id)
    if student_id is not None:
        query = query.where(AuditEntry.student_id == student_id)
    if date_from is not None:
        query = query.where(AuditEntry.created_at >= date_from)
    if date_to is not None:
        query = query.where(AuditEntry.created_at <= date_to)
    return query


def _to_item(row: Any) -> AuditItemOut:
    entry: AuditEntry = row.AuditEntry
    return AuditItemOut(
        id=entry.id,
        created_at=entry.created_at,
        class_id=row.class_id,
        actor=row.actor,
        student=row.student,
        column_label=row.labels.get("tr", "?"),
        old_value=_rendered(entry.old_score, entry.old_scale, entry.old_text),
        new_value=_rendered(entry.new_score, entry.new_scale, entry.new_text),
        old_existed=entry.old_existed,
        forced=entry.forced,
        via_grant=entry.via_grant_id is not None,
    )


@router.get("")
async def list_audit(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    class_id: int | None = None,
    actor_id: int | None = None,
    student_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: int | None = None,
) -> AuditPageOut:
    del user
    query = _base_query(class_id, actor_id, student_id, date_from, date_to)
    if cursor is not None:
        query = query.where(AuditEntry.id < cursor)
    rows = (await db.execute(query.limit(PAGE_SIZE + 1))).all()
    has_more = len(rows) > PAGE_SIZE
    items = [_to_item(row) for row in rows[:PAGE_SIZE]]
    return AuditPageOut(
        items=items,
        next_cursor=items[-1].id if has_more and items else None,
    )


@router.get("/export.csv", dependencies=[Depends(export_rate_limit)])
async def export_audit_csv(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    class_id: int | None = None,
    actor_id: int | None = None,
    student_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> StreamingResponse:
    del user
    rows = (await db.execute(_base_query(class_id, actor_id, student_id, date_from, date_to))).all()

    def stream() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "when",
                "class_id",
                "actor",
                "student",
                "column",
                "old",
                "new",
                "was_empty",
                "forced",
                "via_grant",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for row in rows:
            item = _to_item(row)
            writer.writerow(
                [
                    safe_spreadsheet_cell(value)
                    for value in [
                        item.id,
                        item.created_at.isoformat(),
                        item.class_id,
                        item.actor,
                        item.student,
                        item.column_label,
                        item.old_value if item.old_existed else "∅",
                        item.new_value or "",
                        not item.old_existed,
                        item.forced,
                        item.via_grant,
                    ]
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="flrc-audit.csv"'},
    )
