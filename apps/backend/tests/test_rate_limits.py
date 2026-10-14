"""Exercise production limiter policies against Redis, with isolated test keys."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from flrc.config import settings
from flrc.core import rate_limit
from flrc.db.models import User


def request(address: str = "192.0.2.20") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/login",
            "headers": [],
            "client": (address, 1234),
        }
    )


@pytest.fixture
async def rate_store(monkeypatch):
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    prefix = f"test:rate:{uuid4().hex}:"

    async def evaluate(script, numkeys, key, window):
        # Only namespace the key; run the actual production Lua in Redis.
        return await redis.eval(script, numkeys, prefix + key, window)

    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    try:
        yield redis, prefix
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


async def test_oauth_burst_limit_keeps_callback_and_other_addresses_available(rate_store):
    login = rate_limit.auth_rate_limit("login")
    for _ in range(30):
        await login(request())
    with pytest.raises(HTTPException) as caught:
        await login(request())
    assert caught.value.status_code == 429
    assert 1 <= int(caught.value.headers["Retry-After"]) <= 60

    await rate_limit.auth_rate_limit("callback")(request())
    await login(request("192.0.2.21"))


async def test_oauth_sustained_limit_survives_short_window_resets(rate_store):
    redis, prefix = rate_store
    login = rate_limit.auth_rate_limit("login")
    for _ in range(2):
        for _ in range(30):
            await login(request())
        burst_keys = [
            key async for key in redis.scan_iter(match=f"{prefix}rate_limit:auth:login:burst:*")
        ]
        assert len(burst_keys) == 1
        # Expire only the short window; the five-minute counter must survive.
        await redis.expire(burst_keys[0], 0)

    with pytest.raises(HTTPException) as caught:
        await login(request())
    assert caught.value.status_code == 429
    assert 1 <= int(caught.value.headers["Retry-After"]) <= 300
    await rate_limit.auth_rate_limit("callback")(request())


@pytest.mark.parametrize(
    ("dependency", "allowance"),
    [
        (rate_limit.report_rate_limit, 5),
        (rate_limit.export_rate_limit, 3),
        (rate_limit.import_rate_limit, 3),
        (rate_limit.import_preview_rate_limit, 30),
    ],
)
async def test_operation_limits_are_per_account(rate_store, dependency, allowance):
    for _ in range(allowance):
        await dependency(request(), User(id=101))
    with pytest.raises(HTTPException) as caught:
        await dependency(request(), User(id=101))
    assert caught.value.status_code == 429
    assert 1 <= int(caught.value.headers["Retry-After"]) <= 60
    # Another teacher at the same public address retains their own allowance.
    await dependency(request(), User(id=102))


async def test_operation_budgets_do_not_spend_each_other(rate_store):
    user = User(id=101)
    for _ in range(3):
        await rate_limit.import_rate_limit(request(), user)
    with pytest.raises(HTTPException):
        await rate_limit.import_rate_limit(request(), user)
    await rate_limit.import_preview_rate_limit(request(), user)
    await rate_limit.report_rate_limit(request(), user)
    await rate_limit.export_rate_limit(request(), user)


async def test_concurrent_requests_cannot_exceed_the_allowance(rate_store):
    results = await asyncio.gather(
        *(
            rate_limit.enforce_rate_limit(request(), scope="concurrent", limit=5, window_seconds=60)
            for _ in range(40)
        ),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 5
    rejected = [result for result in results if result is not None]
    assert all(
        isinstance(result, HTTPException) and result.status_code == 429 for result in rejected
    )


async def test_rejected_request_does_not_extend_window_and_expiry_restores_budget(rate_store):
    redis, prefix = rate_store

    async def attempt():
        await rate_limit.enforce_rate_limit(request(), scope="expiry", limit=1, window_seconds=60)

    await attempt()
    keys = [key async for key in redis.scan_iter(match=f"{prefix}rate_limit:expiry:*")]
    assert len(keys) == 1
    assert 0 < await redis.ttl(keys[0]) <= 60
    # Shorten the real Redis expiry so this integration check needs no minute-long wait.
    await redis.pexpire(keys[0], 1000)
    with pytest.raises(HTTPException) as caught:
        await attempt()
    assert caught.value.headers == {"Retry-After": "1"}
    assert 0 < await redis.pttl(keys[0]) <= 1000
    await asyncio.sleep(1.05)
    await attempt()
    assert await redis.get(keys[0]) == "1"


@pytest.mark.parametrize("completed_windows", [0, 1])
async def test_school_login_fails_closed_if_either_redis_check_fails(
    monkeypatch, completed_windows
):
    evaluate = AsyncMock(side_effect=[*([(1, 60)] * completed_windows), ConnectionError("offline")])
    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    monkeypatch.setattr(settings, "env", "school")
    with pytest.raises(HTTPException) as caught:
        await rate_limit.auth_rate_limit("login")(request())
    assert caught.value.status_code == 503
    assert caught.value.detail == {"code": "security_service_unavailable"}
