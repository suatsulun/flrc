"""One lock order for teacher accounts (ADR-080).

A transaction that changes or records anything about an account locks the account row
first, before years, classes, teaching assignments and admin actions. A permanent deletion
holds the row exclusively while it erases the account, so an assignment writer, a year
rollover or an undo that reaches the same account waits for it, then sees the deletion and
refuses, and no action naming the account can be recorded after its scrub.

Administrator writes that change accounts or roles, cannot be undone, or touch teaching
assignments (account create and edit, the signature routes, deletion, both assignment
writers, undo and year close) lock the administrator's own row too, in the same id order,
and check it again with ``lock_for_admin``. Other administrator writes (classes, rosters,
fields, imports) rely on the request's authorization like any request already under way:
an administrator removed meanwhile finishes at most that one request.
"""

from collections.abc import Iterable
from typing import TypeGuard

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import User


async def lock_accounts(
    db: AsyncSession, user_ids: Iterable[int], *, exclusive: bool = False
) -> dict[int, User]:
    """Lock the accounts in id order and return their current rows.

    Readers that only rely on an account staying as it is take a shared lock; writers of the
    account row itself take an exclusive one.
    """
    ids = sorted(set(user_ids))
    if not ids:
        return {}
    rows = await db.scalars(
        select(User)
        .where(User.id.in_(ids))
        .order_by(User.id)
        .with_for_update(read=not exclusive)
        .execution_options(populate_existing=True)
    )
    return {user.id: user for user in rows}


async def lock_for_admin(
    db: AsyncSession,
    actor: User,
    *,
    shared: Iterable[int] = (),
    exclusive: int | None = None,
) -> dict[int, User]:
    """Lock the acting administrator with the accounts a write names, in one id order.

    The administrator and the ``shared`` accounts are locked shared; ``exclusive``, the
    account whose row the write changes, exclusively. The administrator is then checked
    again: one deactivated, deleted or no longer an administrator while the request waited
    is refused as authentication would refuse it (401 ``not_registered``, 403 ``forbidden``).
    """
    ids = {*shared, actor.id}
    if exclusive is None:
        accounts = await lock_accounts(db, ids)
    else:
        accounts = {}
        for user_id in sorted(ids | {exclusive}):
            accounts |= await lock_accounts(db, [user_id], exclusive=user_id == exclusive)
    current = accounts.get(actor.id)
    if not assignable(current):
        raise HTTPException(401, {"code": "not_registered"})
    if not current.is_admin:
        raise HTTPException(403, {"code": "forbidden"})
    return accounts


def assignable(user: User | None) -> TypeGuard[User]:
    """Whether a teaching slot may be given to the account."""
    return user is not None and user.is_active and user.deleted_at is None
