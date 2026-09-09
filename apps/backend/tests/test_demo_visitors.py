import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from flrc.config import settings
from flrc.core import rate_limit
from flrc.core.redis import client
from flrc.db.models import DemoVisitor, User
from flrc.main import create_app
from flrc.modules.auth import cookies, demo, sessions
from flrc.modules.auth.router import oauth
from tests.conftest import TestSession
from tests.test_security_launch import school_settings

DEMO_DOMAIN = "example-school.k12.tr"
OPS_TOKEN = "ops-token-Q7w2Vn8Rp4Lm3Kt6Yz9Xc1Hs5Bf0Jd"  # gitleaks:allow
# Public login is only allowed together with the nightly reset (ADR-052).
DEMO_VALUES: dict[str, object] = {
    "env": "demo",
    "demo_public_login": True,
    "allowed_google_domain": DEMO_DOMAIN,
    "session_ttl_seconds": 24 * 60 * 60,
    "neon_api_key": "synthetic-neon-key",
    "neon_project_id": "synthetic-project",
    "neon_demo_branch_id": "br-demo",
    "neon_golden_branch_id": "br-golden",
    "ops_token": OPS_TOKEN,
}
RAW_SUBJECT = "google-subject-visitor-1"
# Everything Google tells us about the person and nothing of it may be stored.
PERSONAL_CLAIMS = ("real.person@gmail.example", "Real Person", RAW_SUBJECT, "photos.example")


@contextmanager
def demo_settings(**overrides: object) -> Iterator[None]:
    values = DEMO_VALUES | overrides
    previous = {name: getattr(settings, name) for name in values}
    for name, value in values.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)


def gmail_claims(sub: str = RAW_SUBJECT) -> dict[str, object]:
    # A personal account: verified, but with no hosted-domain claim at all.
    return {
        "sub": sub,
        "email": "real.person@gmail.example",
        "email_verified": True,
        "name": "Real Person",
        "picture": "https://photos.example/real-person.jpg",
    }


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _quiet_redis(monkeypatch) -> None:
    # Keep the shared Redis free of per-run OAuth counters and visitor tallies.
    monkeypatch.setattr(rate_limit, "enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(demo, "_new_visitors_today", AsyncMock(return_value=1))


@pytest.fixture
def google(monkeypatch):
    def authorize(claims: dict[str, object]) -> None:
        monkeypatch.setattr(
            oauth.google, "authorize_access_token", AsyncMock(return_value={"userinfo": claims})
        )

    return authorize


@pytest.fixture
def session_store(monkeypatch):
    store = SimpleNamespace(
        create=AsyncMock(return_value="visitor-session"),
        live=AsyncMock(return_value=0),
        revoke=AsyncMock(return_value=0),
        destroy=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(sessions, "create_session", store.create)
    monkeypatch.setattr(sessions, "live_session_count", store.live)
    monkeypatch.setattr(sessions, "revoke_user_sessions", store.revoke)
    monkeypatch.setattr(sessions, "destroy_session", store.destroy)
    return store


async def login(client):
    return await client.get("/api/auth/callback", follow_redirects=False)


async def logout(client, user_id: int):
    client.cookies.set(cookies.DEVELOPMENT_COOKIE_NAME, cookies.sign_sid(f"device-{user_id}"))
    return await client.post("/api/auth/logout", headers={"origin": settings.frontend_origin})


async def visitor_rows() -> list[tuple[User, DemoVisitor]]:
    async with TestSession() as db:
        result = await db.execute(
            select(User, DemoVisitor)
            .join(DemoVisitor, DemoVisitor.user_id == User.id)
            .order_by(User.id)
        )
        return [(row[0], row[1]) for row in result.all()]


async def test_flag_off_keeps_the_school_gate(api, google, session_store) -> None:
    google(gmail_claims())
    with demo_settings(demo_public_login=False):
        async with api(None) as client:
            response = await login(client)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/login?error=wrong_domain")
    session_store.create.assert_not_awaited()
    async with TestSession() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    "claims",
    [gmail_claims(), gmail_claims() | {"hd": "other-company.example"}],
    ids=["personal-gmail", "foreign-workspace"],
)
async def test_visitor_login_creates_a_pseudonymous_temporary_admin(
    api, google, session_store, claims: dict[str, object]
) -> None:
    google(claims)
    with demo_settings():
        async with api(None) as client:
            response = await login(client)

    assert response.status_code == 307
    assert response.headers["location"] == settings.frontend_origin
    assert "flrc_session=" in response.headers["set-cookie"]
    [(user, visitor)] = await visitor_rows()
    assert (user.is_admin, user.is_coordinator, user.is_active) == (True, True, True)
    assert re.fullmatch(rf"visitor-[a-z0-9]{{5}}@{re.escape(DEMO_DOMAIN)}", user.email)
    assert user.full_name.startswith("Demo Admin ")
    assert user.google_subject is None
    assert visitor.subject_hash == demo.subject_hash(RAW_SUBJECT)
    assert visitor.scrubbed_at is None
    lifetime = visitor.expires_at - now()
    assert timedelta(hours=23, minutes=59) < lifetime <= timedelta(hours=24)
    for stored in (user.email, user.full_name, visitor.subject_hash):
        for personal in PERSONAL_CLAIMS:
            assert personal not in stored
    session_store.create.assert_awaited_once()
    assert session_store.create.await_args.args == (user.id,)
    assert 0 < session_store.create.await_args.kwargs["ttl"] <= 24 * 60 * 60


async def test_repeat_login_reuses_the_live_account(api, google, session_store) -> None:
    google(gmail_claims())
    with demo_settings():
        async with api(None) as client:
            await login(client)
            session_store.live.return_value = 1
            await login(client)
            google(gmail_claims(sub="google-subject-visitor-2"))
            await login(client)

    rows = await visitor_rows()
    assert len(rows) == 2
    assert [visitor.scrubbed_at for _, visitor in rows] == [None, None]
    first_id = rows[0][0].id
    assert [call.args for call in session_store.create.await_args_list] == [
        (first_id,),
        (first_id,),
        (rows[1][0].id,),
    ]
    session_store.revoke.assert_not_awaited()


async def test_login_after_all_sessions_ended_starts_a_fresh_account(
    api, google, session_store
) -> None:
    google(gmail_claims())
    with demo_settings():
        async with api(None) as client:
            await login(client)
            session_store.live.return_value = 0
            await login(client)

    (old_user, old_visitor), (new_user, new_visitor) = await visitor_rows()
    assert old_visitor.subject_hash is None
    assert old_visitor.scrubbed_at is not None
    assert old_user.is_active is False
    assert old_user.email == f"deleted-visitor-{old_user.id}@{DEMO_DOMAIN}"
    assert old_user.full_name == "Deleted visitor"
    assert new_visitor.subject_hash == demo.subject_hash(RAW_SUBJECT)
    assert new_user.is_active is True
    session_store.revoke.assert_awaited_once_with(old_user.id)


async def test_session_ttl_is_capped_by_the_visitor_expiry(api, google, session_store) -> None:
    google(gmail_claims())
    with demo_settings():
        async with api(None) as client:
            await login(client)
            async with TestSession() as db:
                visitor = await db.scalar(select(DemoVisitor))
                assert visitor is not None
                visitor.expires_at = now() + timedelta(hours=1)
                await db.commit()
            session_store.live.return_value = 1
            await login(client)

    ttl = session_store.create.await_args.kwargs["ttl"]
    assert 3500 < ttl <= 3600


async def test_logout_scrubs_only_after_the_last_session_ends(api, google, session_store) -> None:
    google(gmail_claims())
    with demo_settings():
        async with api(None) as client:
            await login(client)
            [(user, _)] = await visitor_rows()
            session_store.destroy.return_value = user.id
            session_store.live.return_value = 1
            first = await logout(client, user.id)
            [(_, still_linked)] = await visitor_rows()
            session_store.live.return_value = 0
            second = await logout(client, user.id)

    assert (first.status_code, second.status_code) == (204, 204)
    assert still_linked.subject_hash == demo.subject_hash(RAW_SUBJECT)
    assert still_linked.scrubbed_at is None
    [(gone, scrubbed)] = await visitor_rows()
    assert scrubbed.subject_hash is None
    assert scrubbed.scrubbed_at is not None
    assert gone.is_active is False
    assert session_store.destroy.await_count == 2


async def test_daily_visitor_cap_refuses_new_accounts(
    api, google, session_store, monkeypatch
) -> None:
    google(gmail_claims())
    monkeypatch.setattr(
        demo,
        "_new_visitors_today",
        AsyncMock(return_value=settings.demo_visitor_limit_per_day + 1),
    )
    with demo_settings():
        async with api(None) as client:
            response = await login(client)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/login?error=demo_full")
    session_store.create.assert_not_awaited()
    assert await visitor_rows() == []


async def test_visitors_cannot_manage_other_visitor_accounts(
    api, google, session_store, world
) -> None:
    google(gmail_claims(sub="visitor-a"))
    headers = {"origin": settings.frontend_origin}
    with demo_settings():
        async with api(None) as client:
            await login(client)
            google(gmail_claims(sub="visitor-b"))
            await login(client)
        (visitor_a, _), (visitor_b, _) = await visitor_rows()
        async with api(visitor_a) as client:
            other = await client.patch(
                f"/api/admin/users/{visitor_b.id}", json={"full_name": "Renamed"}, headers=headers
            )
            seeded = await client.patch(
                f"/api/admin/users/{world.main.id}",
                json={"full_name": "Renamed Teacher"},
                headers=headers,
            )
            me = await client.patch(
                f"/api/admin/users/{visitor_a.id}",
                json={"full_name": "My Demo Name"},
                headers=headers,
            )

    assert other.status_code == 403
    assert other.json()["detail"]["code"] == "visitor_protected"
    assert seeded.status_code == 200
    assert me.status_code == 200
    async with TestSession() as db:
        assert await db.scalar(select(User.full_name).where(User.id == visitor_b.id)) != "Renamed"


async def test_live_session_count_prunes_expired_ids() -> None:
    user_id = 424242
    await sessions.revoke_user_sessions(user_id)
    first = await sessions.create_session(user_id, ttl=60)
    second = await sessions.create_session(user_id, ttl=60)
    assert await sessions.live_session_count(user_id) == 2

    await client().delete(f"session:{second}")  # the same as a TTL expiry
    assert await sessions.live_session_count(user_id) == 1
    assert await client().smembers(f"user_sessions:{user_id}") == {first}
    assert await sessions.destroy_session(first) == user_id
    assert await sessions.live_session_count(user_id) == 0


def test_public_login_is_refused_outside_the_demo() -> None:
    with demo_settings(env="dev"):
        with pytest.raises(RuntimeError, match="DEMO_PUBLIC_LOGIN"):
            create_app()
    with school_settings(demo_public_login=True):
        with pytest.raises(RuntimeError, match="DEMO_PUBLIC_LOGIN"):
            create_app()
    with demo_settings(allowed_google_domain=""):
        with pytest.raises(RuntimeError, match="ALLOWED_GOOGLE_DOMAIN"):
            create_app()
    with demo_settings(session_ttl_seconds=48 * 60 * 60):
        with pytest.raises(RuntimeError, match="SESSION_TTL_SECONDS"):
            create_app()
