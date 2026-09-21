from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import DemoVisitor, SchoolClass, TeachingAssignment, User
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.auth import demo
from flrc.modules.auth.dependencies import current_user
from flrc.modules.demo import schedule

router = APIRouter(tags=["me"])


class AssignmentOut(BaseModel):
    class_id: int
    class_name: str
    role: str


class DemoSessionOut(BaseModel):
    """Present only for a temporary public-demo administrator (ADR-051)."""

    expires_at: datetime
    next_reset_at: datetime


class MeOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_admin: bool
    is_coordinator: bool
    assignments: list[AssignmentOut]
    demo: DemoSessionOut | None = None


@router.get("/me")
async def me(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> MeOut:
    rows = (
        await db.execute(
            select(
                TeachingAssignment.class_id,
                SchoolClass.grade_level,
                SchoolClass.section,
                TeachingAssignment.role,
            )
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(TeachingAssignment.user_id == user.id)
        )
    ).all()
    demo_session = None
    if demo.enabled():
        visitor = await db.get(DemoVisitor, user.id)
        if visitor is not None:
            demo_session = DemoSessionOut(
                expires_at=visitor.expires_at.replace(tzinfo=UTC),
                next_reset_at=schedule.next_reset_at(),
            )
    return MeOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_admin=user.is_admin,
        is_coordinator=user.is_coordinator,
        demo=demo_session,
        assignments=[
            AssignmentOut(
                class_id=r.class_id,
                class_name=class_label(r.grade_level, r.section),
                role=r.role,
            )
            for r in rows
        ],
    )
