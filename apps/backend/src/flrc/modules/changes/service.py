"""Recording undoable administrative writes (ADR-075).

Every undoable admin write adds one ``AdminAction`` in the same transaction as
the write itself, so a change is never stored without the means to undo it.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from flrc.db.models import AdminAction, User

ADMIN_ACTION_TTL = timedelta(days=7)

# Stable identifiers; the admin app translates them, so never rename one.
ActionKind = Literal[
    "student.add",
    "student.remove",
    "student.move",
    "student.edit",
    "student.language",
    "class.create",
    "class.edit",
    "class.delete",
    "field.create",
    "field.delete",
    "field.edit",
    "field.reorder",
    "field.copy",
    "user.create",
    "user.edit",
    "signature.upload",
    "signature.delete",
    "assignments.replace",
]
ActionStatus = Literal["available", "undone", "expired"]


class ActionWrite(BaseModel):
    """Mixed into write responses: the recorded action that undoes this write."""

    action_id: int


class UndoBlocked(Exception):
    """The current data no longer allows restoring the previous state."""

    def __init__(self, reason: str, **params: object) -> None:
        super().__init__(reason)
        self.reason = reason
        self.params = params


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def record_action(
    db: AsyncSession,
    *,
    actor: User,
    kind: ActionKind,
    params: dict[str, object],
    undo: dict[str, object],
    blob: bytes | None = None,
) -> AdminAction:
    """Add the action to the caller's transaction; the caller commits with its write."""
    now = utcnow()
    action = AdminAction(
        actor_id=actor.id,
        kind=kind,
        summary={"params": params},
        undo_data=undo,
        blob=blob,
        created_at=now,
        expires_at=now + ADMIN_ACTION_TTL,
    )
    db.add(action)
    await db.flush()
    return action


def changed_values(
    before: dict[str, object], after: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Keep only the attributes an edit actually changed, as ``(before, after)``."""
    keys = [key for key in after if before.get(key) != after[key]]
    return {key: before.get(key) for key in keys}, {key: after[key] for key in keys}


def change_list(before: dict[str, object], after: dict[str, object]) -> list[dict[str, object]]:
    """Display parameters of an edit: one ``{field, from, to}`` entry per changed attribute."""
    return [{"field": key, "from": before.get(key), "to": value} for key, value in after.items()]


def with_action[T: BaseModel](model: type[T], out: BaseModel, action: AdminAction) -> T:
    """Extend a read model with the action that undoes the write."""
    return model.model_validate({**out.model_dump(), "action_id": action.id})


def action_status(action: AdminAction, now: datetime) -> ActionStatus:
    if action.undone_at is not None:
        return "undone"
    if action.expires_at <= now:
        return "expired"
    return "available"


def purge_expired_actions(db: Session, now: datetime | None = None) -> int:
    """Delete expired actions with their snapshots and kept images; the caller commits."""
    result = db.execute(delete(AdminAction).where(AdminAction.expires_at <= (now or utcnow())))
    return int(getattr(result, "rowcount", 0) or 0)
