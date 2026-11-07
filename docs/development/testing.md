# Testing

This describes executable checks and their destructive-data boundaries; read this before running tests or adding regression coverage. Setup prerequisites are in [local development](../getting-started/local-development.md).

## Test behavior, not implementation trivia

Write regression coverage that fails on the broken behavior before applying the fix where practical. Assert persisted values, permissions, versions, audit rows, visible state, and rollback—not just successful response status or a helper being called. Cover absent/null/empty values, boundaries, authorization failures, duplicates, stale writes, locked/archived state, failure and retry, and cleanup where relevant. Do not snapshot incidental markup or duplicate generated types in mocks.

Backend tests use pytest, dependency overrides, in-process ASGI clients, and synthetic identities. Preserve the two-independent-browser grade-conflict E2E test: single-user tests cannot prove conflict safety. Neither `apps/teacher` nor `apps/admin` has a standalone unit-test runner or `test` script. Root `pnpm test` runs workspace test scripts, not frontend component tests; it includes backend pytest and the i18n check.

## Backend: fixed, shared disposable database

`apps/backend/tests/conftest.py` hardcodes `postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test`. It applies Alembic migrations at session start and deletes table contents between tests. Migration tests also downgrade to base. Changing application `DATABASE_URL` does **not** redirect these fixtures. Never run this suite against a school database or concurrently with another pytest session.

From the root, start services and create the database once:

```sh
pnpm dev:services
docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_test
```

An “already exists” error means creation is unnecessary; do not drop it while another session owns it. From `apps/backend`, serialize all test invocations using the same lock:

```sh
flock /tmp/flrc-pytest.lock uv run pytest -q
flock /tmp/flrc-pytest.lock uv run pytest tests/test_migrations.py -q
```

Use the same prefix for a focused test path. PostgreSQL must remain on port 5432 for this suite. Redis is needed by relevant integration tests. Read the fixtures before introducing parallelization; `pytest-xdist` is not a safe shortcut.

## Browser E2E: isolated application stack

Playwright does not start servers: there is no `webServer` entry. `playwright.config.ts` fixes `workers: 1` and `fullyParallel: false` because files mutate one seeded database. Local retries are zero; CI retries once. Chromium is the configured project. Failure traces/screenshots/videos are retained; treat them as potentially sensitive and use synthetic data only.

Choose an unused database, Redis index, and port pair rather than accidentally testing another session's stack. Example root setup:

```sh
pnpm dev:services
docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_feature
pnpm --filter @flrc/teacher build
pnpm --filter @flrc/admin build
pnpm exec playwright install --with-deps chromium
```

In a backend terminal (`apps/backend`), export these values so migration, seed, and API use the **same** database:

```sh
export ENV=test E2E_AUTH_SECRET=local-synthetic-e2e-secret
export ALLOWED_GOOGLE_DOMAIN=example-school.k12.tr
export DATABASE_URL=postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_feature
export DATABASE_URL_DIRECT="$DATABASE_URL"
export REDIS_URL=redis://localhost:6379/3
export FRONTEND_ORIGIN=http://localhost:4273
export ADMIN_ORIGIN=http://localhost:5274
uv run alembic upgrade head
uv run flrc seed-e2e
uv run uvicorn flrc.main:app --host 127.0.0.1 --port 8100
```

Start each preview from the root in a separate terminal:

```sh
VITE_API_TARGET=http://localhost:8100 pnpm --filter @flrc/teacher preview --port 4273
VITE_API_TARGET=http://localhost:8100 pnpm --filter @flrc/admin preview --port 5274
```

Run specs from another root terminal:

```sh
E2E_AUTH_SECRET=local-synthetic-e2e-secret \
  E2E_BASE_URL=http://localhost:4273 \
  E2E_ADMIN_BASE_URL=http://localhost:5274 pnpm e2e
```

Both origins are necessary: `e2e/helpers/origins.ts` defaults teacher to `4173` and admin to `5174`. Backend origins must match the chosen frontend origins or CSRF checks reject writes. Admin URLs retain `/admin/`. `VITE_API_TARGET` controls the Vite proxy at process startup; the browser still uses same-origin `/api` calls. Rebuild previews after source changes.

**Reseed between runs.** From a shell with the same backend exports, run `uv run flrc seed-e2e` before each new suite invocation. It destructively recreates the tiny E2E dataset; the suite is not idempotent on dirty data (fixed student numbers can collide). Never use this command on shared real data. Stop your own servers after use; do not kill processes belonging to other sessions.

For focused execution, replace `pnpm e2e` with `pnpm exec playwright test e2e/conflict.spec.ts` (or the relevant spec). See [the E2E recipe](how-to.md#write-an-e2e-spec) for auth and fixtures.

## Phone, loading, and accessibility checks

Use `page.setViewportSize({ width: 390, height: 844 })` for the phone acceptance viewport, and separately exercise desktop width 1440. Existing specs such as `e2e/admin-workspace.spec.ts` and `e2e/teacher-shell.spec.ts` cover responsive interactions. Add tests for the touched page rather than assuming the Desktop Chrome project covers phones automatically.

Delay mocked responses to observe page-shaped skeletons, then assert ready/error behavior. Check no unwanted horizontal page overflow, readable cards, reachable actions, long translated labels, keyboard focus/return focus, dialog names, and that desktop tables still behave. Screenshots support review but are not a substitute for interaction assertions.

## Static and contract checks

| Scope                     | Command from root unless stated                                                          |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| All lint                  | `pnpm lint`                                                                              |
| All type checks           | `pnpm typecheck`                                                                         |
| Focused app               | `pnpm --filter @flrc/admin lint` / `pnpm --filter @flrc/admin typecheck` (or teacher)    |
| Python lint/format        | From `apps/backend`: `uv run ruff check .` and `uv run ruff format --check .`            |
| Python types              | From `apps/backend`: `uv run mypy src/flrc`                                              |
| Formatting                | `pnpm format:check` (check only); `pnpm exec prettier --write <changed-files>` to format |
| Locales                   | `pnpm i18n:check`                                                                        |
| Contract                  | `pnpm generate`; inspect/commit generated changes under `packages/api-client`            |
| Branding                  | `pnpm brand:check`, `pnpm brand:test`                                                    |
| Browser telemetry privacy | `pnpm telemetry:test`                                                                    |

Lefthook pre-commit checks staged Prettier/ESLint/Ruff files in parallel. It does not run mypy, type checking, pytest, Playwright, or all CI checks. Run one shared-DB suite at a time even when other lightweight checks run independently.

## CI map

Source: `.github/workflows/ci.yml` and `security.yml`. These are workflow check names, not a promise about remote branch-protection configuration.

| Check                          | What it does                                                                                                                                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Production image (backend/web) | Builds both production Dockerfiles without publishing                                                                                                            |
| JavaScript                     | Frozen pnpm install; branding check/tests; telemetry privacy tests; non-backend Turbo lint/typecheck/build; verifies assembled teacher/admin demo output         |
| Python                         | Python 3.13 + frozen uv install; Ruff lint/format; mypy; PostgreSQL 18/Redis 8 services; creates `flrc_test`; pytest                                             |
| API contract                   | Frozen installs; regenerates client; fails on `packages/api-client` diff                                                                                         |
| Deployment templates           | Validates school Compose, Caddy, gateway forwarding, and cloud-init YAML                                                                                         |
| Browser E2E                    | After JS/Python/contract; migrates/seeds fresh synthetic data; starts API on 8000, teacher preview on 4173, admin on 5174; installs Chromium and runs Playwright |
| Secret scan                    | Gitleaks over repository history                                                                                                                                 |
| Locked dependency audit        | High-severity production pnpm audit; exports frozen production Python dependencies; pip-audit against PyPI and OSV                                               |
| CodeQL (language)              | Security-extended JavaScript/TypeScript and Python analysis when repository visibility/GHAS permits                                                              |
| Dependency review              | On eligible PRs, rejects moderate-or-higher runtime dependency vulnerabilities                                                                                   |

Release, keepalive, demo-reset, and dependency auto-merge workflows are operational automation, not replacements for contribution checks. See [deployment](../operations/deployment.md) and [public demo](../operations/public-demo.md).
