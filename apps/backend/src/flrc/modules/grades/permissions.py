from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import TeachingAssignment, User

Subject = Literal["english", "german", "french"]

SUBJECT_ROLES: dict[Subject, tuple[str, ...]] = {
    "english": ("main", "skills"),
    "german": ("german",),
    "french": ("french",),
}


async def has_subject_assignment(
    db: AsyncSession,
    user: User,
    class_id: int,
    subject: Subject,
) -> bool:
    """Return whether a teacher is assigned to this exact class and subject."""
    assignment_id = await db.scalar(
        select(TeachingAssignment.id)
        .where(
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.user_id == user.id,
            TeachingAssignment.role.in_(SUBJECT_ROLES[subject]),
        )
        .limit(1)
    )
    return assignment_id is not None


async def require_subject_access(
    db: AsyncSession,
    user: User,
    class_id: int,
    subject: Subject,
    *,
    allow_coordinator: bool,
) -> None:
    if user.is_admin or (allow_coordinator and user.is_coordinator):
        return
    if not await has_subject_assignment(db, user, class_id, subject):
        raise HTTPException(403, {"code": "class_subject_forbidden"})
