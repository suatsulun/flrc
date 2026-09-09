from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import AcademicYear, Semester, User
from flrc.db.session import get_session
from flrc.modules.auth import cookies, sessions
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": code})


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "forbidden"})


async def current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    token = request.cookies.get(cookies.cookie_name())
    if not token:
        raise _unauthorized("not_authenticated")
    sid = cookies.unsign_sid(token)
    if sid is None:
        raise _unauthorized("bad_session")
    user_id = await sessions.get_user_id(sid)
    if user_id is None:
        raise _unauthorized("session_expired")
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        await sessions.destroy_session(sid)
        raise _unauthorized("not_registered")
    if allowed_google_domain() and not email_is_in_school_domain(user.email):
        await sessions.destroy_session(sid)
        raise _unauthorized("wrong_domain")
    return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise _forbidden()
    return user


async def require_coordinator_or_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not (user.is_admin or user.is_coordinator):
        raise _forbidden()
    return user


async def writable_semester(db: Annotated[AsyncSession, Depends(get_session)]) -> Semester:
    result = await db.execute(
        select(Semester)
        .join(AcademicYear, AcademicYear.id == Semester.year_id)
        .where(AcademicYear.status == "active", Semester.status == "open")
    )
    semester = result.scalar_one_or_none()
    if semester is None:
        raise HTTPException(status_code=409, detail={"code": "semester_locked"})
    return semester


async def writable_year(db: Annotated[AsyncSession, Depends(get_session)]) -> AcademicYear:
    result = await db.execute(
        select(AcademicYear).where(AcademicYear.status == "active").order_by(AcademicYear.id.desc())
    )
    year = result.scalars().first()
    if year is None:
        raise HTTPException(status_code=409, detail={"code": "year_not_writable"})
    return year
