import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request
from redis.exceptions import RedisError

from flrc.config import settings
from flrc.core.redis import client
from flrc.db.models import User
from flrc.modules.auth.dependencies import current_user

log = structlog.get_logger()
_INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""

# Every login costs one /auth/login and one /auth/callback request, and a whole
# school shares one public address behind NAT. The window is therefore wide
# enough for a morning rush (roughly one login per second, sustained) while
# still stopping the automated abuse this protects against. Each endpoint gets
# its own counter so a flood of one cannot lock users out of the other.
AUTH_LIMIT = 120
AUTH_WINDOW_SECONDS = 5 * 60

# Report rendering and workbook parsing are the two CPU-bound paths that a
# single authenticated account can use to exhaust the small school dyno.
EXPENSIVE_LIMIT = 10
EXPENSIVE_WINDOW_SECONDS = 60


def _client_identity(request: Request) -> str:
    if settings.env == "school":
        # Only reachable behind the Cloudflare Worker: gateway_check_middleware
        # rejects any /api request that does not carry the gateway secret, so
        # this header cannot be attacker-supplied in school mode.
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    identity: str | None = None,
) -> None:
    raw_identity = identity or _client_identity(request)
    digest = hmac.new(
        settings.session_secret.encode(),
        f"{scope}:{raw_identity}".encode(),
        hashlib.sha256,
    ).hexdigest()
    key = f"rate_limit:{scope}:{digest}"
    try:
        count, ttl = await client().eval(_INCREMENT_WINDOW, 1, key, window_seconds)
    except RedisError as exc:
        log.warning("rate_limit_store_unavailable", scope=scope)
        if settings.env == "school":
            raise HTTPException(503, {"code": "security_service_unavailable"}) from exc
        return
    if int(count) > limit:
        raise HTTPException(
            429,
            {"code": "rate_limited"},
            headers={"Retry-After": str(max(1, int(ttl)))},
        )


def auth_rate_limit(scope: str) -> Callable[[Request], Awaitable[None]]:
    """Per-client-address limit for an unauthenticated OAuth endpoint."""

    async def dependency(request: Request) -> None:
        await enforce_rate_limit(
            request,
            scope=f"auth:{scope}",
            limit=AUTH_LIMIT,
            window_seconds=AUTH_WINDOW_SECONDS,
        )

    return dependency


def user_rate_limit(
    scope: str, *, limit: int = EXPENSIVE_LIMIT
) -> Callable[[Request, User], Awaitable[None]]:
    """Per-account limit for an expensive authenticated endpoint."""

    async def dependency(
        request: Request,
        user: Annotated[User, Depends(current_user)],
    ) -> None:
        await enforce_rate_limit(
            request,
            scope=scope,
            limit=limit,
            window_seconds=EXPENSIVE_WINDOW_SECONDS,
            identity=str(user.id),
        )

    return dependency


report_rate_limit = user_rate_limit("report_pdf")
export_rate_limit = user_rate_limit("bulk_export")
import_rate_limit = user_rate_limit("workbook_import")
# Paging and edits each revalidate the workbook. Allow an interactive review
# without consuming the separate, stricter commit budget.
import_preview_rate_limit = user_rate_limit("workbook_preview", limit=60)
