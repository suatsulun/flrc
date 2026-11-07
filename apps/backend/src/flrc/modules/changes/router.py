from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from flrc.db.models import AdminAction, User
from flrc.db.session import get_session
from flrc.modules.administration.roster_service import is_duplicate_school_number
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.auth.sessions import revoke_user_sessions
from flrc.modules.changes.service import (
    ActionKind,
    ActionStatus,
    UndoBlocked,
    action_status,
    utcnow,
)
from flrc.modules.changes.undo import HANDLERS, UndoContext, lock_action_accounts

router = APIRouter(prefix="/admin/actions", tags=["admin-actions"])


class AdminActionOut(BaseModel):
    id: int
    kind: ActionKind
    actor: str | None
    created_at: datetime
    expires_at: datetime
    status: ActionStatus
    undone_at: datetime | None
    undone_by: str | None
    # Display values resolved when the change was made (names, classes, counts).
    params: dict[str, Any]


class AdminActionPage(BaseModel):
    items: list[AdminActionOut]
    next_cursor: int | None


actor_user = aliased(User)
undoer_user = aliased(User)


def _out(action: AdminAction, actor: str | None, undone_by: str | None) -> AdminActionOut:
    return AdminActionOut(
        id=action.id,
        kind=cast(ActionKind, action.kind),
        actor=actor,
        created_at=action.created_at,
        expires_at=action.expires_at,
        status=action_status(action, utcnow()),
        undone_at=action.undone_at,
        undone_by=undone_by,
        params=cast(dict[str, Any], action.summary.get("params", {})),
    )


def _blocked(reason: str, params: dict[str, object]) -> HTTPException:
    return HTTPException(409, {"code": "undo_blocked", "reason": reason, "params": params})


@router.get("")
async def list_admin_actions(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    cursor: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> AdminActionPage:
    """Recent undoable admin changes, newest first; rows past expiry show as expired
    until the nightly purge removes them."""
    del user
    query = (
        select(AdminAction, actor_user.full_name, undoer_user.full_name)
        .outerjoin(actor_user, actor_user.id == AdminAction.actor_id)
        .outerjoin(undoer_user, undoer_user.id == AdminAction.undone_by)
        .order_by(AdminAction.id.desc())
    )
    if cursor is not None:
        query = query.where(AdminAction.id < cursor)
    rows = (await db.execute(query.limit(limit + 1))).all()
    items = [_out(action, actor, undone_by) for action, actor, undone_by in rows[:limit]]
    return AdminActionPage(
        items=items,
        next_cursor=items[-1].id if len(rows) > limit and items else None,
    )


@router.post("/{action_id}/undo")
async def undo_admin_action(
    action_id: int,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AdminActionOut:
    """Restore the state before an action in one transaction, or change nothing."""
    named = (
        await db.execute(
            select(AdminAction.kind, AdminAction.undo_data).where(AdminAction.id == action_id)
        )
    ).first()
    if named is None:
        raise HTTPException(404, {"code": "unknown_action"})
    # Accounts before the action row: the order every account write and a permanent
    # deletion use (ADR-080), so neither can deadlock with this undo.
    await lock_action_accounts(db, named.kind, named.undo_data)
    action = await db.scalar(
        select(AdminAction)
        .where(AdminAction.id == action_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if action is None:
        raise HTTPException(404, {"code": "unknown_action"})
    if action.undone_at is not None:
        raise HTTPException(409, {"code": "action_already_undone"})
    now = utcnow()
    if action.expires_at <= now:
        raise HTTPException(410, {"code": "action_expired"})
    context = UndoContext(db=db, action=action, actor=actor)
    try:
        await HANDLERS[action.kind](context)
        action.undone_at = now
        action.undone_by = actor.id
        await db.flush()
    except UndoBlocked as exc:
        await db.rollback()
        raise _blocked(exc.reason, exc.params) from exc
    except HTTPException as exc:
        # The original endpoints' rules (archived year, locked term, last admin, ...)
        # refuse an undo with their own codes.
        await db.rollback()
        detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        if "code" not in detail:
            raise
        raise _blocked(
            str(detail["code"]), {key: value for key, value in detail.items() if key != "code"}
        ) from exc
    except IntegrityError as exc:
        # A concurrent write took a school number the checks above saw free.
        await db.rollback()
        if is_duplicate_school_number(exc):
            raise _blocked("school_number_taken", {}) from exc
        raise
    await db.commit()
    for user_id in context.revoke_user_ids:
        await revoke_user_sessions(user_id)
    author = await db.scalar(select(User.full_name).where(User.id == action.actor_id))
    return _out(action, author, actor.full_name)
