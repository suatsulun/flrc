from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from flrc.config import settings
from flrc.db.models import User
from flrc.modules.administration import users as user_routes
from flrc.modules.auth import cookies, sessions
from flrc.modules.auth.router import oauth
from tests.conftest import TestSession


@contextmanager
def school_domain() -> Iterator[None]:
    previous = settings.allowed_google_domain
    settings.allowed_google_domain = "school.example"
    try:
        yield
    finally:
        settings.allowed_google_domain = previous


def claims(**overrides: object) -> dict[str, object]:
    return {
        "sub": "google-subject-123",
        "email": "teacher@school.example",
        "email_verified": True,
        "hd": "school.example",
    } | overrides


async def test_forged_session_cookie_is_rejected_before_redis(api, monkeypatch) -> None:
    redis_lookup = AsyncMock()
    monkeypatch.setattr(sessions, "get_user_id", redis_lookup)
    forged = cookies.sign_sid("synthetic-session") + "tampered"

    async with api(None) as client:
        client.cookies.set(cookies.DEVELOPMENT_COOKIE_NAME, forged)
        response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "bad_session"
    redis_lookup.assert_not_awaited()


@pytest.mark.parametrize(
    ("userinfo", "error"),
    [
        (claims(hd="attacker.example"), "wrong_domain"),
        (claims(email="teacher@attacker.example"), "wrong_domain"),
        (claims(email_verified=False), "email_not_verified"),
        (claims(email_verified="true"), "email_not_verified"),
        (claims(sub=""), "invalid_identity"),
    ],
)
async def test_oauth_rejects_untrusted_claims_before_allowlist_lookup(
    api, monkeypatch, userinfo: dict[str, object], error: str
) -> None:
    authorize = AsyncMock(return_value={"userinfo": userinfo})
    create_session = AsyncMock()
    monkeypatch.setattr(oauth.google, "authorize_access_token", authorize)
    monkeypatch.setattr(sessions, "create_session", create_session)

    with school_domain():
        async with api(None) as client:
            response = await client.get("/api/auth/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith(f"/login?error={error}")
    create_session.assert_not_awaited()


async def test_valid_but_unregistered_school_account_is_denied(api, monkeypatch) -> None:
    monkeypatch.setattr(
        oauth.google,
        "authorize_access_token",
        AsyncMock(return_value={"userinfo": claims(email="unknown@school.example")}),
    )
    create_session = AsyncMock()
    monkeypatch.setattr(sessions, "create_session", create_session)

    with school_domain():
        async with api(None) as client:
            response = await client.get("/api/auth/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/login?error=not_registered")
    create_session.assert_not_awaited()


async def test_first_login_binds_stable_google_subject(api, monkeypatch) -> None:
    async with TestSession() as db:
        user = User(email="teacher@school.example", full_name="Synthetic Teacher")
        db.add(user)
        await db.commit()
        user_id = user.id

    monkeypatch.setattr(
        oauth.google,
        "authorize_access_token",
        AsyncMock(return_value={"userinfo": claims()}),
    )
    create_session = AsyncMock(return_value="new-session")
    monkeypatch.setattr(sessions, "create_session", create_session)

    with school_domain():
        async with api(None) as client:
            response = await client.get("/api/auth/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == settings.frontend_origin
    create_session.assert_awaited_once_with(user_id)
    assert cookies.DEVELOPMENT_COOKIE_NAME in response.cookies
    async with TestSession() as db:
        bound_subject = await db.scalar(select(User.google_subject).where(User.id == user_id))
    assert bound_subject == "google-subject-123"


async def test_reassigned_email_cannot_take_over_bound_allowlist_entry(api, monkeypatch) -> None:
    async with TestSession() as db:
        db.add(
            User(
                email="teacher@school.example",
                full_name="Synthetic Teacher",
                google_subject="original-google-subject",
            )
        )
        await db.commit()

    monkeypatch.setattr(
        oauth.google,
        "authorize_access_token",
        AsyncMock(return_value={"userinfo": claims(sub="different-google-subject")}),
    )
    create_session = AsyncMock()
    monkeypatch.setattr(sessions, "create_session", create_session)

    with school_domain():
        async with api(None) as client:
            response = await client.get("/api/auth/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/login?error=identity_mismatch")
    create_session.assert_not_awaited()


async def test_existing_session_is_rejected_if_allowlist_email_leaves_domain(
    api, monkeypatch
) -> None:
    async with TestSession() as db:
        user = User(email="teacher@attacker.example", full_name="Synthetic Teacher")
        db.add(user)
        await db.commit()
        user_id = user.id

    monkeypatch.setattr(sessions, "get_user_id", AsyncMock(return_value=user_id))
    destroy_session = AsyncMock()
    monkeypatch.setattr(sessions, "destroy_session", destroy_session)
    token = cookies.sign_sid("session-id")

    with school_domain():
        async with api(None) as client:
            client.cookies.set(cookies.DEVELOPMENT_COOKIE_NAME, token)
            response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "wrong_domain"
    destroy_session.assert_awaited_once_with("session-id")


async def test_admin_can_only_allowlist_the_configured_school_domain(api, world) -> None:
    body = {
        "full_name": "Synthetic New Teacher",
        "teaching_field": "english",
        "teaching_stage": "middle",
    }
    with school_domain():
        async with api(world.admin) as client:
            outsider = await client.post(
                "/api/admin/users",
                json=body | {"email": "outsider@attacker.example"},
            )
            school_teacher = await client.post(
                "/api/admin/users",
                json=body | {"email": "new.teacher@school.example"},
            )
            german_teacher = await client.post(
                "/api/admin/users",
                json={
                    "email": "german.teacher@school.example",
                    "full_name": "Synthetic German Teacher",
                    "teaching_field": "german",
                },
            )

    assert outsider.status_code == 422
    assert outsider.json()["detail"]["code"] == "wrong_school_domain"
    assert school_teacher.status_code == 201
    assert school_teacher.json()["email"] == "new.teacher@school.example"
    assert school_teacher.json()["teaching_stage"] == "middle"
    assert german_teacher.status_code == 201
    assert german_teacher.json()["teaching_stage"] is None


async def test_google_identity_reset_requires_deactivation(api, world, monkeypatch) -> None:
    async with TestSession() as db:
        user = User(
            email="reassigned@school.example",
            full_name="Synthetic Reassigned Teacher",
            google_subject="original-google-subject",
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    revoke = AsyncMock(return_value=1)
    monkeypatch.setattr(user_routes, "revoke_user_sessions", revoke)
    async with api(world.admin) as client:
        active_reset = await client.patch(
            f"/api/admin/users/{user_id}",
            json={"reset_google_identity": True},
        )
        deactivated_reset = await client.patch(
            f"/api/admin/users/{user_id}",
            json={"is_active": False, "reset_google_identity": True},
        )

    assert active_reset.status_code == 409
    assert active_reset.json()["detail"]["code"] == "deactivate_before_identity_reset"
    assert deactivated_reset.status_code == 200
    assert deactivated_reset.json()["is_active"] is False
    revoke.assert_awaited_once_with(user_id)
    async with TestSession() as db:
        stored = await db.get(User, user_id)
        assert stored is not None
        assert stored.google_subject is None
