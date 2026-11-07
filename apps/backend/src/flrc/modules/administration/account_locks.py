"""One lock order for teacher accounts (ADR-080).

A transaction that changes or records anything about an account locks the account row
first, before admin actions and teaching assignments. A permanent deletion holds the row
exclusively while it erases the account, so an assignment writer, a year rollover or an
undo that reaches the same account waits for it, then sees the deletion and refuses, and
no action naming the account can be recorded after its scrub.
"""

from collections.abc import Iterable
from typing import TypeGuard

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


def assignable(user: User | None) -> TypeGuard[User]:
    """Whether a teaching slot may be given to the account."""
    return user is not None and user.is_active and user.deleted_at is None
