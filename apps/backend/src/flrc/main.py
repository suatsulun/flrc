import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flrc.config import settings
from flrc.core.logging import configure_logging
from flrc.core.middleware import (
    gateway_check_middleware,
    origin_check_middleware,
    request_context_middleware,
    security_headers_middleware,
)
from flrc.core.rate_limit import report_rate_limit
from flrc.core.telemetry import configure_telemetry
from flrc.modules.academics.assignments import router as assignments_router
from flrc.modules.academics.columns import router as columns_router
from flrc.modules.administration.classes import router as admin_classes_router
from flrc.modules.administration.coordinator import router as coordinator_router
from flrc.modules.administration.lifecycle import router as lifecycle_router
from flrc.modules.administration.roster import router as roster_router
from flrc.modules.administration.students import router as students_router
from flrc.modules.administration.users import router as users_router
from flrc.modules.archive.router import router as archive_router
from flrc.modules.audit.router import router as audit_router
from flrc.modules.auth.admin import router as admin_router
from flrc.modules.auth.dependencies import current_user
from flrc.modules.auth.me import router as me_router
from flrc.modules.auth.router import router as auth_router
from flrc.modules.demo import reset as demo_reset
from flrc.modules.demo.router import ops_router as demo_ops_router
from flrc.modules.demo.router import router as demo_router
from flrc.modules.grades.router import router as grades_router
from flrc.modules.imports.router import router as imports_router
from flrc.modules.jobs.router import router as jobs_router
from flrc.modules.reports.router import router as reports_router
from flrc.modules.system.router import router as system_router


def _operation_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    # The demo catches up on a missed midnight reset as soon as it wakes.
    heal = asyncio.create_task(demo_reset.self_heal_loop()) if demo_reset.enabled() else None
    try:
        yield
    finally:
        if heal is not None:
            heal.cancel()
            with suppress(asyncio.CancelledError):
                await heal


def create_app() -> FastAPI:
    settings.validate_security_configuration()
    configure_logging()
    configure_telemetry()
    expose_schema = settings.env != "school"
    app = FastAPI(
        title="FL-ReportCard",
        openapi_url="/api/openapi.json" if expose_schema else None,
        docs_url="/api/docs" if expose_schema else None,
        redoc_url=None,
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=(
            "__Host-flrc_oauth_state" if settings.env == "school" else "flrc_oauth_state"
        ),
        max_age=10 * 60,
        same_site="lax",
        https_only=settings.env != "dev",
        path="/",
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_size=settings.max_request_body_bytes,
    )
    if settings.env == "demo":
        # Innermost, so held requests still get security headers and a log line.
        app.middleware("http")(demo_reset.reset_gate_middleware)
    app.middleware("http")(origin_check_middleware)
    app.middleware("http")(request_context_middleware)
    app.middleware("http")(gateway_check_middleware)
    app.middleware("http")(security_headers_middleware)
    if settings.env == "school":
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.trusted_host_list(),
            www_redirect=False,
        )

    app.include_router(auth_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    if settings.env == "demo":
        app.include_router(demo_router, prefix="/api")
        app.include_router(demo_ops_router, prefix="/api")
    protected_api = APIRouter(dependencies=[Depends(current_user)])
    protected_api.include_router(me_router)
    protected_api.include_router(admin_router)
    protected_api.include_router(columns_router)
    protected_api.include_router(assignments_router)
    protected_api.include_router(grades_router)
    protected_api.include_router(audit_router)
    protected_api.include_router(students_router)
    protected_api.include_router(users_router)
    protected_api.include_router(admin_classes_router)
    protected_api.include_router(roster_router)
    protected_api.include_router(lifecycle_router)
    protected_api.include_router(imports_router)
    protected_api.include_router(archive_router)
    protected_api.include_router(coordinator_router)
    protected_api.include_router(jobs_router)
    protected_reports = APIRouter(dependencies=[Depends(report_rate_limit)])
    protected_reports.include_router(reports_router)
    protected_api.include_router(protected_reports)
    app.include_router(protected_api, prefix="/api")
    if settings.env == "test":
        from flrc.modules.auth.test_router import router as test_router

        app.include_router(test_router, prefix="/api")
    return app


app = create_app()
