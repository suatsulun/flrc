# Configuration reference

This lists settings and their validation boundaries; read this when configuring an API/worker, diagnosing startup rejection, or choosing frontend build variables. `apps/backend/src/flrc/config.py` is the backend source of truth; deployment procedures live in [operations](../operations/deployment.md).

## Loading and modes

Pydantic Settings reads process environment plus `.env` relative to the working directory, ignores extra `.env` keys, and converts typed integers/booleans. Run backend tools from `apps/backend`; environment variables override `.env`. Names below are the uppercase environment spelling of the Python fields. API startup calls `validate_security_configuration()` in `main.py`; this method is not automatically invoked by every maintenance CLI command.

`ENV` is a string, not a validated enum. Supported behavior branches are `dev`, `test`, `demo`, and `school`; use those exact values. Test authentication is registered only in `test`; API docs/schema are hidden in `school`. Do not assume an arbitrary value is production-safe.

## Core services and sessions

| Variable                 | Default                                              | Meaning / requirement                                                                                    |
| ------------------------ | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ENV`                    | `dev`                                                | Runtime mode, as above                                                                                   |
| `DATABASE_URL`           | `postgresql+asyncpg://flrc:flrc@localhost:5432/flrc` | Async application connection; pooled endpoint where applicable                                           |
| `DATABASE_URL_DIRECT`    | `postgresql+asyncpg://flrc:flrc@localhost:5432/flrc` | Direct connection for migrations and sync maintenance/export work                                        |
| `REDIS_URL`              | `redis://localhost:6379/0`                           | Sessions and the Celery broker (no result backend; job state lives in Postgres `job_runs`)               |
| `SESSION_SECRET`         | `dev-secret-change-me`                               | Signs session IDs and OAuth state; replace for deployments                                               |
| `SESSION_TTL_SECONDS`    | `28800`                                              | Absolute session lifetime (8 hours); demo visitors may have a shorter remaining lifetime                 |
| `MAX_REQUEST_BODY_BYTES` | `12582912`                                           | API request-body middleware limit (12 MiB)                                                               |
| `OPS_TOKEN`              | `dev-ops-token`                                      | Bearer credential for protected operational endpoints                                                    |
| `E2E_AUTH_SECRET`        | empty                                                | Enables secret-authenticated `/api/test/session` only with `ENV=test`; forbidden nonempty in school mode |
| `SENTRY_DSN`             | empty                                                | Backend error telemetry; empty disables it; privacy scrubbing remains required                           |

In school mode: session TTL must be **900–28800** seconds; body limit **1024–26214400** bytes. `SESSION_SECRET` requires 48+ characters, `OPS_TOKEN` 32+, and `GATEWAY_SECRET` 32+. Each must have at least 12 distinct characters, must not equal a known placeholder (`change-me`, `change-me-48-random-chars`, `dev-ops-token`, `dev-secret-change-me`), and all three must differ.

For remote database URLs in school mode, query `ssl` or `sslmode` must be `require`, `verify-ca`, `verify-full`, or `true`. Remote Redis must use `rediss` and a password. The validator considers `localhost`, `127.0.0.1`, `::1`, `postgres`, `redis`, and `db` local service hosts. This exception is not authorization to expose those services publicly.

## OAuth, browser origins, and gateway

| Variable                | Default                               | Meaning / requirement                                                                                                  |
| ----------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `GOOGLE_CLIENT_ID`      | empty                                 | Google Web OAuth client; school requires suffix `.apps.googleusercontent.com`                                          |
| `GOOGLE_CLIENT_SECRET`  | empty                                 | Client secret; school requires stripped length at least 16                                                             |
| `ALLOWED_GOOGLE_DOMAIN` | empty                                 | Workspace email/hosted domain gate; school requires valid dotted DNS domain and rejects `yourschool.*` placeholders    |
| `FRONTEND_ORIGIN`       | `http://localhost:5173`               | Teacher origin; OAuth callback is this plus `/api/auth/callback`                                                       |
| `ADMIN_ORIGIN`          | `http://localhost:5174`               | Admin origin, **without** `/admin/`; used for write-origin checks                                                      |
| `TRUSTED_HOSTS`         | `localhost,127.0.0.1,test,testserver` | Comma-separated hostnames; stripped/casefolded for school host middleware                                              |
| `GATEWAY_SECRET`        | empty                                 | School public gateway's shared authentication secret; must match gateway configuration                                 |
| `WORKER_HEALTH_URL`     | empty                                 | Optional URL the API requests best-effort to wake a sleeping worker when jobs are queued or polled; not a health check |

School requires both origins to be the **same exact HTTPS origin**: no credentials, path (including trailing `/`), query, or fragment. The host allowlist must be nonempty, have no literal `*`, and include that public origin's hostname. Domain validation normalizes case/whitespace/trailing dot and checks DNS-label syntax; normal login additionally checks email domain, Google's `hd`, verified email, active allowlist and stable subject binding. Local consent/client setup is in [local development](../getting-started/local-development.md#sign-in-with-google), not a production bypass.

## Reports and branding

| Variable                | Default | Meaning / requirement                                                                                |
| ----------------------- | ------- | ---------------------------------------------------------------------------------------------------- |
| `SCHOOL_NAME`           | empty   | Report school-name override; normally use generated branding                                         |
| `SCHOOL_LOGO_PATH`      | empty   | Report logo-path override; normally use generated branding                                           |
| `SCHOOL_BRANDING_DIR`   | empty   | Runtime overlay directory containing branding and optional `reports/` configuration/templates/assets |
| `REPORT_RENDER_WORKERS` | `0`     | Renderer subprocess cap; zero auto-sizes using available CPUs/container quota                        |

These settings have no field-specific bounds/path validators in `Settings`; report consumers enforce asset containment and rendering requirements. Do not put private school assets in source to avoid configuring an overlay. See [branding](../operations/branding.md) and [reports and jobs](../architecture/reports-and-jobs.md).

## Public demo and reset

| Variable                     | Default           | Meaning / requirement                                                                                      |
| ---------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------- |
| `DEMO_PUBLIC_LOGIN`          | `false`           | Allows verified Google identities to obtain temporary demo administrator accounts; only legal in demo mode |
| `DEMO_VISITOR_LIMIT_PER_DAY` | `500`             | Daily newly admitted visitor limit; must be at least 1 when public login is enabled                        |
| `NEON_API_KEY`               | empty             | Neon control-plane credential for demo reset                                                               |
| `NEON_PROJECT_ID`            | empty             | Project containing demo branches                                                                           |
| `NEON_DEMO_BRANCH_ID`        | empty             | Child branch restored during reset                                                                         |
| `NEON_GOLDEN_BRANCH_ID`      | empty             | Pristine parent branch used for reset                                                                      |
| `DEMO_RESET_TIMEZONE`        | `Europe/Istanbul` | IANA timezone for local-midnight reset                                                                     |

If **any** Neon reset value is set after stripping, all four must be supplied and `ENV=demo`; `DEMO_RESET_TIMEZONE` must resolve as an IANA timezone and `OPS_TOKEN` must meet the 32-character/randomness rules above. Reset is enabled only in demo mode with the full set.

`DEMO_PUBLIC_LOGIN=true` additionally requires demo mode, all four reset values, nonempty `ALLOWED_GOOGLE_DOMAIN` for the **synthetic** school identity domain, session TTL **900–86400**, and a positive daily visitor limit. Public demo login does not turn the school allowlist into a public registration path. See [public demo operations](../operations/public-demo.md).

## Backups and archives

| Variable                      | Default           | Meaning / requirement                                                  |
| ----------------------------- | ----------------- | ---------------------------------------------------------------------- |
| `BACKUP_DIR`                  | `/srv/backups`    | Backup work/status directory; writable by sidecar/CLI                  |
| `BACKUP_AGE_RECIPIENT`        | empty             | age public recipient used to encrypt uploads                           |
| `BACKUP_AGE_IDENTITY`         | empty             | age private identity used for restore tests; keep secret               |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | empty             | Service-account JSON document (not a path), used to authenticate Drive |
| `GDRIVE_BACKUP_FOLDER_ID`     | empty             | School-owned Drive destination folder ID                               |
| `BACKUP_AT`                   | `02:30`           | Local wall-clock backup time                                           |
| `BACKUP_RETAIN`               | `7`               | Number of newest encrypted dumps retained                              |
| `BACKUP_RESTORE_TEST_DAY`     | `1`               | Day of month for scheduled restore test                                |
| `BACKUP_TIMEZONE`             | `Europe/Istanbul` | IANA timezone for scheduling                                           |

These fields have no backup-specific startup validation in `Settings`. Backup commands that need a store require nonempty recipient, service-account JSON, and folder ID; `restore-test` also requires identity. The scheduler parses hour/minute into `datetime.time` and resolves `ZoneInfo` when used; configure a real clock/timezone and a valid day (not a promise of a Settings-level range check). Keep retention positive. See [backups and restore](../operations/backups-and-restore.md) for encryption, scratch restores, and operator procedures.

## Frontend variables

All `VITE_*` values are public, not secret storage. Browser variables are compiled by Vite; changing them requires rebuilding. `VITE_API_TARGET` is read by Vite's configuration from the process environment when the dev/preview server starts.

| Variable           | Application | Default                                                  | Meaning                                                                                      |
| ------------------ | ----------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `VITE_API_TARGET`  | Both        | `http://localhost:8000`                                  | Dev and preview `/api` proxy upstream; does not change production static-host routing        |
| `VITE_SENTRY_DSN`  | Both        | absent                                                   | Enables browser Sentry with shared privacy options; environment label comes from Vite `MODE` |
| `VITE_ADMIN_URL`   | Teacher     | Dev: `http://localhost:5174/admin/`; otherwise `/admin/` | Other SPA's document-navigation destination                                                  |
| `VITE_TEACHER_URL` | Admin       | Dev: `http://localhost:5173/`; otherwise `/`             | Teacher SPA's document-navigation destination                                                |

Built-in `import.meta.env.DEV` and `MODE` are Vite-provided, not custom application secrets. Proxy ports/base paths come from each app's `vite.config.ts`; configure `FRONTEND_ORIGIN` and `ADMIN_ORIGIN` consistently.

## Non-Settings tool variables

`FLRC_MIGRATIONS_URL` overrides `DATABASE_URL_DIRECT` in `apps/backend/migrations/env.py`; pytest sets it to its fixed disposable database. `E2E_BASE_URL`, `E2E_ADMIN_BASE_URL`, and the runner's `E2E_AUTH_SECRET` select browser-test origins/login credentials; see [testing](../development/testing.md). Hosting/Compose-specific variables belong to the [deployment](../operations/deployment.md) and [self-hosting](../operations/self-hosting.md) references rather than `Settings`.
