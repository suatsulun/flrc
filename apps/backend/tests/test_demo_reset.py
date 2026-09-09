import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from flrc.core.redis import client
from flrc.main import create_app
from flrc.modules.demo import neon, reset, schedule
from flrc.modules.demo.neon import NeonError
from tests.test_demo_visitors import (
    OPS_TOKEN,
    _quiet_redis,  # noqa: F401 - autouse fixture shared with the visitor tests
    demo_settings,
    gmail_claims,
    google,  # noqa: F401
    login,
    session_store,  # noqa: F401
    visitor_rows,
)

NO_NEON: dict[str, object] = {
    "neon_api_key": "",
    "neon_project_id": "",
    "neon_demo_branch_id": "",
    "neon_golden_branch_id": "",
}
RESET_KEYS = (reset.LOCK_KEY, reset.STATE_KEY, reset.LAST_KEY, reset.ERROR_KEY)


def reset_settings(**overrides: object):
    return demo_settings(**overrides)


@pytest.fixture(autouse=True)
async def _clean_reset_keys():
    await client().delete(*RESET_KEYS)
    yield
    await client().delete(*RESET_KEYS)


@pytest.fixture
def fake_neon(monkeypatch):
    restore = AsyncMock(return_value=["op-1", "op-2"])
    wait = AsyncMock()
    monkeypatch.setattr(neon.NeonClient, "reset_branch_from", restore)
    monkeypatch.setattr(neon.NeonClient, "wait_for_operations", wait)
    monkeypatch.setattr(reset, "_wait_for_database", AsyncMock())
    return restore, wait


def ops_client(app) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-ops-token": OPS_TOKEN},
    )


def test_reset_day_boundary_is_istanbul_midnight() -> None:
    with reset_settings():
        late_evening = datetime(2026, 9, 9, 20, 59, tzinfo=UTC)  # 23:59 in Istanbul
        just_after = datetime(2026, 9, 9, 21, 0, tzinfo=UTC)  # 00:00 in Istanbul
        assert schedule.local_today(late_evening).isoformat() == "2026-09-09"
        assert schedule.local_today(just_after).isoformat() == "2026-09-10"
        assert schedule.next_reset_at(late_evening) == datetime(2026, 9, 9, 21, 0, tzinfo=UTC)
        assert schedule.next_reset_at(just_after) == datetime(2026, 9, 10, 21, 0, tzinfo=UTC)
        assert schedule.needs_reset(None, late_evening) is True
        assert schedule.needs_reset("2026-09-08", late_evening) is True
        assert schedule.needs_reset("2026-09-09", late_evening) is False
        assert schedule.needs_reset("2026-09-09", just_after) is True


def test_public_login_requires_the_nightly_reset() -> None:
    with demo_settings(**NO_NEON):
        with pytest.raises(RuntimeError, match="requires the nightly reset"):
            create_app()
    with reset_settings(neon_golden_branch_id=""):
        with pytest.raises(RuntimeError, match="NEON_GOLDEN_BRANCH_ID"):
            create_app()
    with reset_settings(ops_token="dev-ops-token"):
        with pytest.raises(RuntimeError, match="OPS_TOKEN"):
            create_app()
    with reset_settings(demo_reset_timezone="Mars/Olympus"):
        with pytest.raises(RuntimeError, match="DEMO_RESET_TIMEZONE"):
            create_app()
    with reset_settings(env="dev", demo_public_login=False):
        with pytest.raises(RuntimeError, match="NEON_"):
            create_app()


async def test_demo_routes_exist_only_in_demo_mode() -> None:
    with reset_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            info = await api.get("/api/demo")
    assert info.status_code == 200
    body = info.json()
    assert body["state"] == "ready"
    assert body["visitor_lifetime_hours"] == 24
    assert datetime.fromisoformat(body["next_reset_at"]) > datetime.now(UTC)

    app = create_app()  # dev settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        assert (await api.get("/api/demo")).status_code == 404
        assert (await api.get("/api/ops/demo/status")).status_code == 404


async def test_ops_routes_require_the_token() -> None:
    with reset_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            missing = await api.get("/api/ops/demo/status")
            wrong = await api.get("/api/ops/demo/status", headers={"x-ops-token": "nope"})
            unsafe = await api.post("/api/ops/demo/reset", headers={"x-ops-token": "nope"})
        async with ops_client(app) as api:
            right = await api.get("/api/ops/demo/status")
    assert (missing.status_code, wrong.status_code, unsafe.status_code) == (401, 401, 401)
    assert right.status_code == 200
    assert right.json()["state"] == "idle"
    assert right.json()["due"] is True


async def test_reset_restores_the_branch_and_clears_server_state(fake_neon) -> None:
    restore, wait = fake_neon
    redis = client()
    await redis.set("session:stale", "1")
    await redis.set("user_sessions:7", "1")
    await redis.set("demo:visitors:2026-01-01", "40")
    await redis.set("rate_limit:auth:login:abc", "3")
    await redis.set(reset.LAST_KEY, "2020-01-01")
    await redis.set(reset.ERROR_KEY, "NeonError")
    try:
        with reset_settings():
            outcome = await reset.run_reset(reason="test")
            today = schedule.local_today().isoformat()
        assert outcome == "reset"
        restore.assert_awaited_once_with("br-demo", "br-golden")
        wait.assert_awaited_once_with(["op-1", "op-2"])
        assert await redis.get(reset.LAST_KEY) == today
        assert (
            await redis.exists(
                "session:stale",
                "user_sessions:7",
                "demo:visitors:2026-01-01",
                "rate_limit:auth:login:abc",
            )
            == 0
        )
        assert await redis.exists(reset.STATE_KEY, reset.LOCK_KEY, reset.ERROR_KEY) == 0
        with reset_settings():
            assert await reset.ensure_current() is None
    finally:
        await redis.delete("session:stale", "user_sessions:7")


async def test_failed_reset_records_the_error_and_reopens_the_demo(fake_neon) -> None:
    restore, _ = fake_neon
    restore.side_effect = NeonError("restore_http_500")
    await client().set(reset.LAST_KEY, "2020-01-01")
    with reset_settings():
        outcome = await reset.run_reset(reason="test")
    assert outcome == "failed"
    assert await client().get(reset.ERROR_KEY) == "NeonError"
    assert await client().get(reset.LAST_KEY) == "2020-01-01"
    assert await client().exists(reset.STATE_KEY, reset.LOCK_KEY) == 0


async def test_unreachable_neon_is_a_recorded_failure_not_a_crash(monkeypatch) -> None:
    async def unreachable(self, *args, **kwargs):
        raise neon.httpx2.ConnectError("synthetic network failure")

    monkeypatch.setattr(neon.httpx2.AsyncClient, "post", unreachable)
    with reset_settings():
        outcome = await reset.run_reset(reason="test")
    assert outcome == "failed"
    assert await client().get(reset.ERROR_KEY) == "NeonError"
    assert await client().exists(reset.STATE_KEY, reset.LOCK_KEY) == 0


async def test_self_heal_loop_survives_an_unexpected_error(monkeypatch) -> None:
    calls: list[str] = []

    async def boom():
        calls.append("tick")
        raise RuntimeError("synthetic")

    async def stop(delay: float) -> None:
        assert delay == reset.HEAL_RETRY_SECONDS
        raise asyncio.CancelledError

    monkeypatch.setattr(reset, "ensure_current", boom)
    monkeypatch.setattr(reset.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        await reset.self_heal_loop()
    assert calls == ["tick"]


async def test_reset_is_single_flight(fake_neon) -> None:
    restore, _ = fake_neon
    await client().set(reset.LOCK_KEY, "someone-else", ex=60)
    with reset_settings():
        assert await reset.run_reset(reason="test") == "busy"
    restore.assert_not_awaited()


async def test_gate_holds_data_traffic_while_resetting(api, world) -> None:
    await client().set(reset.STATE_KEY, "resetting", ex=60)
    with reset_settings():
        async with api(world.admin) as data:
            me = await data.get("/api/me")
            health = await data.get("/api/healthz")
            info = await data.get("/api/demo")
    assert me.status_code == 503
    assert me.json()["code"] == "demo_resetting"
    assert me.headers["retry-after"] == "10"
    assert health.status_code == 204
    assert info.status_code == 200
    assert info.json()["state"] == "resetting"


async def test_ops_reset_runs_in_the_background(monkeypatch) -> None:
    run = AsyncMock(return_value="reset")
    monkeypatch.setattr(reset, "run_reset", run)
    with reset_settings():
        app = create_app()
        async with ops_client(app) as api:
            accepted = await api.post("/api/ops/demo/reset")
            await client().set(reset.STATE_KEY, "resetting", ex=60)
            busy = await api.post("/api/ops/demo/reset")
    assert accepted.status_code == 202
    assert busy.status_code == 409
    run.assert_awaited_once_with(reason="ops")


async def test_self_heal_resets_only_when_today_is_missing(monkeypatch) -> None:
    run = AsyncMock(return_value="reset")
    monkeypatch.setattr(reset, "run_reset", run)
    with reset_settings():
        await client().set(reset.LAST_KEY, "2020-01-01")
        assert await reset.ensure_current() == "reset"
        run.assert_awaited_once_with(reason="self-heal")
        await client().set(reset.LAST_KEY, schedule.local_today().isoformat())
        assert await reset.ensure_current() is None
    assert run.await_count == 1


async def test_me_describes_the_visitor_session(api, google, session_store, world) -> None:  # noqa: F811
    google(gmail_claims())
    with reset_settings():
        async with api(None) as anonymous:
            await login(anonymous)
        [(visitor, row)] = await visitor_rows()
        async with api(visitor) as as_visitor:
            mine = await as_visitor.get("/api/me")
        async with api(world.admin) as as_admin:
            seeded = await as_admin.get("/api/me")
    assert mine.status_code == 200
    demo_info = mine.json()["demo"]
    assert datetime.fromisoformat(demo_info["expires_at"]) == row.expires_at.replace(tzinfo=UTC)
    assert datetime.fromisoformat(demo_info["next_reset_at"]) > datetime.now(UTC)
    assert seeded.json()["demo"] is None
