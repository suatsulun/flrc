import secrets
import time
import uuid

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from flrc.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Swagger UI loads its own scripts and styles, so the API-wide "trust
# nothing" policy would break it. These paths only exist outside school
# mode, where create_app() passes openapi_url=None and docs_url=None.
INTERACTIVE_DOC_PATHS = {"/api/docs", "/api/openapi.json", "/docs/oauth2-redirect"}
log = structlog.get_logger()


def _append_vary(current: str | None, value: str) -> str:
    values = {item.strip() for item in (current or "").split(",") if item.strip()}
    values.add(value)
    return ", ".join(sorted(values))


async def request_context_middleware(request: Request, call_next):
    clear_contextvars()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return response


async def origin_check_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/ops/"):
        # Operations routes are called by automation with a bearer-style token
        # and never by a browser cookie, so there is no CSRF surface to guard.
        return await call_next(request)
    if request.method not in SAFE_METHODS:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        allowed_origins = {
            settings.frontend_origin,
            settings.admin_origin,
        }
        if settings.env == "school":
            # School browsers always send Origin for the unsafe fetch/form
            # methods used by this app. Requiring it also makes curl-style
            # mutations fail unless the operator deliberately supplies it.
            allowed = origin in allowed_origins and site in {None, "same-origin", "none"}
        elif site is not None:
            allowed = site in ("same-origin", "none")
        else:
            allowed = origin in allowed_origins or (
                origin is None and settings.env in {"dev", "test"}
            )
        if not allowed:
            return JSONResponse(status_code=403, content={"code": "bad_origin"})
    return await call_next(request)


async def gateway_check_middleware(request: Request, call_next):
    """Make the managed API origin unusable without the school gateway."""
    if (
        settings.env == "school"
        and request.url.path.startswith("/api")
        and request.url.path != "/api/healthz"
    ):
        supplied = request.headers.get("x-flrc-gateway", "")
        if not supplied or not secrets.compare_digest(supplied, settings.gateway_secret):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        if request.url.path not in INTERACTIVE_DOC_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        response.headers["Cache-Control"] = "no-store, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = _append_vary(response.headers.get("Vary"), "Cookie")
    if settings.env == "school":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
