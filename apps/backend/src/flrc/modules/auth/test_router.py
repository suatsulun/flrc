import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.config import settings
from flrc.db.models import User
from flrc.db.session import get_session
from flrc.modules.auth import cookies, sessions

router = APIRouter(prefix="/test", tags=["test-only"])


class E2ESessionBody(BaseModel):
    email: str


@router.post("/session")
async def create_test_session(
    body: E2ESessionBody,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    x_e2e_secret: Annotated[str, Header()] = "",
) -> dict[str, bool]:
    if settings.env != "test" or not settings.e2e_auth_secret:
        raise HTTPException(404)
    if not secrets.compare_digest(x_e2e_secret, settings.e2e_auth_secret):
        raise HTTPException(404)
    user = await db.scalar(select(User).where(User.email == body.email, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(404)
    sid = await sessions.create_session(user.id)
    cookies.set_session_cookie(response, sid)
    return {"ok": True}
