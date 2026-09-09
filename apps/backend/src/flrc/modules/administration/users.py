from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import SchoolClass, TeachingAssignment, User
from flrc.db.session import get_session
from flrc.modules.administration.names import normalize_email, search_key
from flrc.modules.auth import demo
from flrc.modules.auth.dependencies import require_admin
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain
from flrc.modules.auth.sessions import revoke_user_sessions

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
TeachingField = Literal["english", "german", "french"]
TeachingStage = Literal["primary", "middle"]


class ManagedUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    is_coordinator: bool
    is_active: bool
    teaching_field: str
    teaching_stage: str | None
    revoked_sessions: int = 0

    @classmethod
    def from_model(cls, user: User, revoked_sessions: int = 0) -> "ManagedUserOut":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_admin=user.is_admin,
            is_coordinator=user.is_coordinator,
            is_active=user.is_active,
            teaching_field=user.teaching_field,
            teaching_stage=user.teaching_stage,
            revoked_sessions=revoked_sessions,
        )


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=2, max_length=160)
    is_admin: bool = False
    is_coordinator: bool = False
    teaching_field: TeachingField = "english"
    teaching_stage: TeachingStage | None = None


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    is_admin: bool | None = None
    is_coordinator: bool | None = None
    is_active: bool | None = None
    teaching_field: TeachingField | None = None
    teaching_stage: TeachingStage | None = None
    reset_google_identity: bool = False


@router.get("")
async def list_managed_users(
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    q: str = "",
    active: bool | None = None,
) -> list[ManagedUserOut]:
    del actor
    statement = select(User)
    if q.strip():
        needle = f"%{search_key(q)}%"
        statement = statement.where(
            or_(func.lower(User.full_name).like(needle), func.lower(User.email).like(needle))
        )
    if active is not None:
        statement = statement.where(User.is_active.is_(active))
    users = list(await db.scalars(statement.order_by(User.full_name)))
    return [ManagedUserOut.from_model(user) for user in users]


@router.post("", status_code=201)
async def create_managed_user(
    body: UserCreate,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ManagedUserOut:
    del actor
    email = normalize_email(body.email)
    if allowed_google_domain() and not email_is_in_school_domain(email):
        raise HTTPException(422, {"code": "wrong_school_domain"})
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(409, {"code": "duplicate_email"})
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        is_admin=body.is_admin,
        is_coordinator=body.is_coordinator,
        teaching_field=body.teaching_field,
        teaching_stage=(body.teaching_stage or "primary")
        if body.teaching_field == "english"
        else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ManagedUserOut.from_model(user)


@router.patch("/{user_id}")
async def patch_managed_user(
    user_id: int,
    body: UserPatch,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ManagedUserOut:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, {"code": "unknown_user"})
    if target.id != actor.id and await demo.is_visitor(db, target.id):
        # Demo visitors are all administrators; none may touch another's account.
        raise HTTPException(403, {"code": "visitor_protected"})
    if body.is_active is False and target.id == actor.id:
        raise HTTPException(409, {"code": "cannot_deactivate_self"})
    removes_admin = target.is_admin and (body.is_admin is False or body.is_active is False)
    if removes_admin:
        active_admins = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        if active_admins == 1:
            raise HTTPException(409, {"code": "last_admin"})
    updates = body.model_dump(exclude_unset=True)
    reset_identity = bool(updates.pop("reset_google_identity", False))
    teaching_change = "teaching_field" in updates or "teaching_stage" in updates
    if teaching_change:
        next_field = str(updates.get("teaching_field", target.teaching_field))
        next_stage = updates.get("teaching_stage", target.teaching_stage)
        if next_field == "english":
            updates["teaching_stage"] = next_stage or "primary"
        else:
            updates["teaching_stage"] = None
        assignments = (
            await db.execute(
                select(TeachingAssignment.role, SchoolClass.grade_level)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(TeachingAssignment.user_id == target.id)
            )
        ).all()
        for role, grade_level in assignments:
            expected_field = "english" if role in ("main", "skills") else role
            expected_stage = "primary" if grade_level <= 4 else "middle"
            if next_field != expected_field or (
                next_field == "english" and updates["teaching_stage"] != expected_stage
            ):
                raise HTTPException(409, {"code": "teacher_assignments_incompatible"})
    will_be_active = bool(updates.get("is_active", target.is_active))
    if reset_identity and will_be_active:
        raise HTTPException(409, {"code": "deactivate_before_identity_reset"})

    was_active = target.is_active
    for field, value in updates.items():
        setattr(target, field, value.strip() if field == "full_name" and value else value)
    if reset_identity:
        target.google_subject = None
    await db.commit()
    revoked = 0
    if (was_active and not target.is_active) or reset_identity:
        revoked = await revoke_user_sessions(target.id)
    return ManagedUserOut.from_model(target, revoked_sessions=revoked)
