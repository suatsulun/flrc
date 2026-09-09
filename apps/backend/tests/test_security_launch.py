import re
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.routing import APIRoute
from httpx2 import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from flrc.config import settings
from flrc.core.telemetry import before_breadcrumb, configure_telemetry, scrub
from flrc.main import create_app
from flrc.modules.auth import cookies
from flrc.modules.auth.dependencies import current_user

SCHOOL_ORIGIN = "https://flrc.school.example"
GATEWAY_SECRET = "gateway-7Mkp2Qv9Zx4Tr8Nc6Hs1Wy5Bd0Lf3Aj"  # gitleaks:allow
SCHOOL_VALUES: dict[str, object] = {
    "env": "school",
    "frontend_origin": SCHOOL_ORIGIN,
    "admin_origin": SCHOOL_ORIGIN,
    "trusted_hosts": "flrc.school.example,flrc-api-school.onrender.com",
    "gateway_secret": GATEWAY_SECRET,
    "session_secret": "session-D8x2Vn7Qp4Lm9Kr5Yt1Wc6Hs3Bf0ZjAaEuOi92Gh",  # gitleaks:allow
    "ops_token": "operations-J3m7Qz1Wx9Cv5Bn2Hs8Kp4Df6Rt0YaLe",  # gitleaks:allow
    "google_client_id": "school-client.apps.googleusercontent.com",
    "google_client_secret": "school-oauth-secret",
    "allowed_google_domain": "school.example",
    "e2e_auth_secret": "",
    "session_ttl_seconds": 8 * 60 * 60,
    "max_request_body_bytes": 1024,
}


@contextmanager
def school_settings(**overrides: object) -> Iterator[None]:
    values = SCHOOL_VALUES | overrides
    previous = {name: getattr(settings, name) for name in values}
    for name, value in values.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)


def gateway_headers(*, unsafe: bool = False) -> dict[str, str]:
    headers = {"x-flrc-gateway": GATEWAY_SECRET}
    if unsafe:
        headers.update({"origin": SCHOOL_ORIGIN, "sec-fetch-site": "same-origin"})
    return headers


def api_routes(router: object, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in getattr(router, "routes", ()):
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        original_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        if original_router is not None and include_context is not None:
            yield from api_routes(original_router, prefix + include_context.prefix)


async def test_test_session_route_absent_in_school_mode() -> None:
    with school_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url=SCHOOL_ORIGIN) as client:
            response = await client.post(
                "/api/test/session",
                headers=gateway_headers(unsafe=True) | {"x-e2e-secret": "not-relevant"},
                json={"email": "synthetic@example.test"},
            )
    assert response.status_code == 404


async def test_school_mode_rejects_missing_and_bad_origin() -> None:
    with school_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url=SCHOOL_ORIGIN) as client:
            missing = await client.post(
                "/api/auth/logout", headers={"x-flrc-gateway": GATEWAY_SECRET}
            )
            bad = await client.post(
                "/api/auth/logout",
                headers={
                    "x-flrc-gateway": GATEWAY_SECRET,
                    "origin": "https://attacker.example",
                    "sec-fetch-site": "cross-site",
                },
            )
    assert missing.status_code == 403
    assert bad.status_code == 403


async def test_every_data_route_is_fail_closed_without_a_session() -> None:
    public_routes = {
        ("GET", "/api/healthz"),
        ("GET", "/api/auth/login"),
        ("GET", "/api/auth/callback"),
        ("POST", "/api/auth/logout"),
    }
    checked: set[tuple[str, str]] = set()
    failures: list[tuple[str, str, int]] = []
    with school_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url=SCHOOL_ORIGIN) as client:
            for route_path, route in api_routes(app):
                path = re.sub(r"\{[^}]+\}", "1", route_path)
                for method in route.methods:
                    key = (method, route_path)
                    if key in public_routes:
                        continue
                    headers = gateway_headers(unsafe=method not in {"GET", "HEAD", "OPTIONS"})
                    response = await client.request(method, path, headers=headers)
                    checked.add(key)
                    if response.status_code != 401:
                        failures.append((method, route_path, response.status_code))

    assert len(checked) >= 40
    assert failures == []


async def test_gateway_https_host_schema_and_headers_are_enforced() -> None:
    with school_settings():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url=SCHOOL_ORIGIN) as client:
            direct = await client.get("/api/me")
            forged = await client.get("/api/me", headers={"x-flrc-gateway": "wrong"})
            proxied = await client.get("/api/me", headers=gateway_headers())
            schema = await client.get("/api/openapi.json", headers=gateway_headers())
            docs = await client.get("/api/docs", headers=gateway_headers())
            health = await client.get("/api/healthz")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://flrc.school.example"
        ) as client:
            insecure = await client.get("/api/healthz", follow_redirects=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://attacker.example"
        ) as client:
            bad_host = await client.get("/api/healthz")

    assert direct.status_code == 404
    assert forged.status_code == 404
    assert proxied.status_code == 401
    assert schema.status_code == 404
    assert docs.status_code == 404
    assert health.status_code == 204
    assert health.content == b""
    assert health.headers["cache-control"] == "no-store, private, max-age=0"
    assert health.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["cross-origin-opener-policy"] == "same-origin"
    assert health.headers["content-security-policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert insecure.status_code in {307, 308}
    assert insecure.headers["location"].startswith("https://")
    assert bad_host.status_code == 400


async def test_request_body_limit_counts_streamed_bytes() -> None:
    async def oversized_body():
        yield (
            b"--security-boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="oversized.xlsx"\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
        )
        yield b"x" * 1400
        yield b"\r\n--security-boundary--\r\n"

    with school_settings():
        app = create_app()
        app.dependency_overrides[current_user] = lambda: SimpleNamespace(is_admin=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url=SCHOOL_ORIGIN) as client:
            response = await client.post(
                "/api/admin/import/dry-run",
                headers=gateway_headers(unsafe=True)
                | {"content-type": "multipart/form-data; boundary=security-boundary"},
                content=oversized_body(),
            )
    assert response.status_code == 413


def test_school_configuration_fails_closed() -> None:
    with school_settings(frontend_origin="http://flrc.school.example"):
        with pytest.raises(RuntimeError, match="FRONTEND_ORIGIN"):
            create_app()
    with school_settings(session_secret="dev-secret-change-me"):
        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            create_app()
    with school_settings(trusted_hosts="*"):
        with pytest.raises(RuntimeError, match="TRUSTED_HOSTS"):
            create_app()
    with school_settings(e2e_auth_secret="must-never-be-enabled"):
        with pytest.raises(RuntimeError, match="E2E_AUTH_SECRET"):
            create_app()
    with school_settings(demo_public_login=True):
        with pytest.raises(RuntimeError, match="DEMO_PUBLIC_LOGIN"):
            create_app()
    with school_settings(ops_token=SCHOOL_VALUES["session_secret"]):
        with pytest.raises(RuntimeError, match="must all be different"):
            create_app()
    with school_settings(redis_url="redis://cache.example:6379/0"):
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            create_app()
    with school_settings(
        database_url="postgresql+asyncpg://user:pass@db.example/app",
        database_url_direct="postgresql+asyncpg://user:pass@db.example/app",
    ):
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            create_app()


def test_school_session_cookie_is_host_only_secure_and_short_lived() -> None:
    with school_settings():
        response = Response()
        cookies.set_session_cookie(response, "synthetic-session")
    header = response.headers["set-cookie"]
    assert header.startswith("__Host-flrc_session=")
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Max-Age=28800" in header
    assert "Domain=" not in header


def test_school_oauth_state_cookie_honors_host_prefix_contract() -> None:
    with school_settings():
        app = create_app()
    middleware = next(item for item in app.user_middleware if item.cls is SessionMiddleware)
    assert middleware.kwargs["session_cookie"] == "__Host-flrc_oauth_state"
    assert middleware.kwargs["path"] == "/"
    assert middleware.kwargs["https_only"] is True


def test_telemetry_scrubber_is_recursive() -> None:
    event = {
        "email": "synthetic@example.test",
        "nested": [{"score": 91, "safe_id": 42}],
        "request": {
            "url": "https://flrc.school.example/api/users?q=synthetic-student",
            "query_string": "q=synthetic-student",
            "data": {"full_name": "Synthetic Student"},
            "headers": {
                "Authorization": "secret",
                "X-Flrc-Gateway": "gateway-secret",
                "Cookie": "session-secret",
            },
        },
    }
    filtered = scrub(event)
    assert filtered["email"] == "[Filtered]"
    assert filtered["nested"][0] == {"score": "[Filtered]", "safe_id": 42}
    assert filtered["request"]["headers"]["Authorization"] == "[Filtered]"
    assert filtered["request"]["headers"]["X-Flrc-Gateway"] == "[Filtered]"
    assert filtered["request"]["headers"]["Cookie"] == "[Filtered]"
    assert filtered["request"]["url"] == "[Filtered]"
    assert filtered["request"]["query_string"] == "[Filtered]"
    assert filtered["request"]["data"] == "[Filtered]"


def test_telemetry_disables_request_bodies_and_local_variables(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("flrc.core.telemetry.sentry_sdk.init", fake_init)
    with school_settings(sentry_dsn="https://public@example.ingest.sentry.io/1"):
        configure_telemetry()

    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["before_breadcrumb"] is before_breadcrumb
