from typing import Annotated

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.config import settings
from flrc.core.rate_limit import auth_rate_limit
from flrc.db.models import User
from flrc.db.session import get_session
from flrc.modules.administration.names import normalize_email
from flrc.modules.auth import cookies, demo, sessions
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_origin}/login?error={code}")


def _identity_error(claims: dict[str, object], subject: str) -> str | None:
    if claims.get("email_verified") is not True:
        return "email_not_verified"
    if not subject or len(subject) > 255:
        return "invalid_identity"
    return None


def _session_response(sid: str) -> RedirectResponse:
    response = RedirectResponse(settings.frontend_origin)
    cookies.set_session_cookie(response, sid)
    return response


@router.get("/login", dependencies=[Depends(auth_rate_limit("login"))])
async def login(request: Request):
    redirect_uri = f"{settings.frontend_origin}/api/auth/callback"
    if demo.enabled():
        # Any Google account may enter the public demo, so no hosted-domain hint.
        return await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        hd=settings.allowed_google_domain,
        prompt="select_account",
    )


@router.get("/callback", dependencies=[Depends(auth_rate_limit("callback"))])
async def auth_callback(request: Request, db: Annotated[AsyncSession, Depends(get_session)]):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return _login_error("google_error")

    claims = token.get("userinfo") or {}
    email = normalize_email(str(claims.get("email", "")))
    subject = str(claims.get("sub", "")).strip()
    hosted_domain = str(claims.get("hd", "")).casefold().strip().rstrip(".")

    if demo.enabled():
        if (error := _identity_error(claims, subject)) is not None:
            return _login_error(error)
        try:
            _, sid = await demo.login_visitor(db, subject)
        except demo.VisitorLimitReached:
            return _login_error("demo_full")
        return _session_response(sid)

    if hosted_domain != allowed_google_domain() or not email_is_in_school_domain(email):
        return _login_error("wrong_domain")
    if (error := _identity_error(claims, subject)) is not None:
        return _login_error(error)

    result = await db.execute(select(User).where(User.email == email).with_for_update())
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return _login_error("not_registered")
    if user.google_subject is not None and user.google_subject != subject:
        return _login_error("identity_mismatch")
    subject_owner = await db.scalar(
        select(User.id).where(User.google_subject == subject, User.id != user.id)
    )
    if subject_owner is not None:
        return _login_error("identity_mismatch")
    if user.google_subject is None:
        user.google_subject = subject
        await db.commit()

    sid = await sessions.create_session(user.id)
    return _session_response(sid)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    token = request.cookies.get(cookies.cookie_name())
    if token and (sid := cookies.unsign_sid(token)):
        user_id = await sessions.destroy_session(sid)
        if user_id is not None and demo.enabled():
            await demo.release_visitor(db, user_id)
    cookies.clear_session_cookie(response)
