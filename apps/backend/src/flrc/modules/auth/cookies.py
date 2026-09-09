from fastapi import Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from flrc.config import settings

DEVELOPMENT_COOKIE_NAME = "flrc_session"
SCHOOL_COOKIE_NAME = "__Host-flrc_session"

_signer = URLSafeTimedSerializer(settings.session_secret, salt="flrc-session")


def cookie_name() -> str:
    return SCHOOL_COOKIE_NAME if settings.env == "school" else DEVELOPMENT_COOKIE_NAME


def sign_sid(sid: str) -> str:
    return _signer.dumps(sid)


def unsign_sid(token: str) -> str | None:
    try:
        return _signer.loads(token, max_age=settings.session_ttl_seconds)
    except BadSignature:
        return None


def set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        cookie_name(),
        sign_sid(sid),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.env not in {"dev", "test"},
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        cookie_name(),
        path="/",
        secure=settings.env not in {"dev", "test"},
        httponly=True,
        samesite="lax",
    )
