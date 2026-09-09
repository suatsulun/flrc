"""Nightly reset of the shared demo school (ADR-052).

The demo runs on a Neon child branch. A reset restores that branch to the head
of its pristine parent, drops every server-side session and counter, and
records the local date so the self-heal loop knows today is done. A GitHub
schedule asks for the reset at local midnight; the in-process loop catches up
after a missed run or a cold start.
"""

import asyncio
from typing import Literal

import structlog
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text

from flrc.config import settings
from flrc.core.redis import client
from flrc.db import session as db_session
from flrc.modules.demo import schedule
from flrc.modules.demo.neon import NeonClient, NeonError

log = structlog.get_logger()

LOCK_KEY = "demo:reset:lock"
STATE_KEY = "demo:reset:state"  # present while a reset is running
LAST_KEY = "demo:reset:last"  # ISO local date of the last successful reset
ERROR_KEY = "demo:reset:error"  # machine reason of the last failure, if any
RESET_TTL_SECONDS = 15 * 60
FLUSH_PATTERNS = ("session:*", "user_sessions:*", "demo:visitors:*", "rate_limit:*")
GATE_EXEMPT_PREFIXES = ("/api/healthz", "/api/ops/", "/api/demo")
HEAL_INTERVAL_SECONDS = 60
HEAL_RETRY_SECONDS = 10 * 60
DATABASE_RETRIES = 10
DATABASE_RETRY_SECONDS = 3.0

ResetOutcome = Literal["reset", "busy", "failed"]


def enabled() -> bool:
    return settings.demo_reset_enabled()


async def status() -> dict[str, object]:
    state, last, error = (
        _text(value) for value in await client().mget(STATE_KEY, LAST_KEY, ERROR_KEY)
    )
    return {
        "state": "resetting" if state else "idle",
        "last_reset_date": last,
        "last_error": error,
        "next_reset_at": schedule.next_reset_at(),
        "due": schedule.needs_reset(last),
    }


async def is_resetting() -> bool:
    try:
        return await client().exists(STATE_KEY) == 1
    except RedisError:
        return False


async def run_reset(*, reason: str) -> ResetOutcome:
    """Reset now unless another reset holds the lock."""
    redis = client()
    if not await redis.set(LOCK_KEY, reason, nx=True, ex=RESET_TTL_SECONDS):
        return "busy"
    log.info("demo_reset_started", reason=reason)
    try:
        await redis.set(STATE_KEY, "resetting", ex=RESET_TTL_SECONDS)
        neon = NeonClient(api_key=settings.neon_api_key, project_id=settings.neon_project_id)
        operations = await neon.reset_branch_from(
            settings.neon_demo_branch_id, settings.neon_golden_branch_id
        )
        await neon.wait_for_operations(operations)
        await db_session.engine.dispose()
        await _wait_for_database()
        await _flush_state(redis)
        await redis.set(LAST_KEY, schedule.local_today().isoformat())
        await redis.delete(ERROR_KEY)
        log.info("demo_reset_finished")
        return "reset"
    except (NeonError, OSError, RedisError, TimeoutError) as exc:
        await redis.set(ERROR_KEY, type(exc).__name__)
        log.error("demo_reset_failed", error=type(exc).__name__)
        return "failed"
    finally:
        await redis.delete(STATE_KEY, LOCK_KEY)


async def ensure_current() -> ResetOutcome | None:
    """Run a catch-up reset when none has completed on the current local day."""
    last = _text(await client().get(LAST_KEY))
    if not schedule.needs_reset(last):
        return None
    return await run_reset(reason="self-heal")


async def self_heal_loop() -> None:
    while True:
        delay = HEAL_INTERVAL_SECONDS
        try:
            if await ensure_current() == "failed":
                delay = HEAL_RETRY_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the loop must outlive any single failure
            log.error("demo_self_heal_failed", error=type(exc).__name__)
            delay = HEAL_RETRY_SECONDS
        await asyncio.sleep(delay)


async def reset_gate_middleware(request, call_next):
    """Hold data traffic while the branch is being replaced underneath it."""
    path = request.url.path
    if (
        path.startswith("/api")
        and not path.startswith(GATE_EXEMPT_PREFIXES)
        and await is_resetting()
    ):
        return JSONResponse(
            status_code=503, content={"code": "demo_resetting"}, headers={"Retry-After": "10"}
        )
    return await call_next(request)


def _text(value: object) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


async def _wait_for_database() -> None:
    """The restored branch's compute restarts; wait until it answers again."""
    for attempt in range(1, DATABASE_RETRIES + 1):
        try:
            async with db_session.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except OSError:
            if attempt == DATABASE_RETRIES:
                raise
        except Exception as exc:  # driver-specific connection errors
            if attempt == DATABASE_RETRIES:
                raise OSError("database_unavailable") from exc
        await asyncio.sleep(DATABASE_RETRY_SECONDS)


async def _flush_state(redis: Redis) -> None:
    for pattern in FLUSH_PATTERNS:
        batch: list[str] = []
        async for key in redis.scan_iter(match=pattern, count=500):
            batch.append(key)
            if len(batch) >= 200:
                await redis.delete(*batch)
                batch = []
        if batch:
            await redis.delete(*batch)
