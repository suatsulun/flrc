# Backend architecture

The Python application contains the HTTP API, durable-job worker and maintenance CLI. Read this when changing an endpoint, transaction, permission check or background task; start with the [system overview](overview.md) for runtime boundaries.

## Entry points and shared infrastructure

All paths below are relative to `apps/backend/src/flrc/`.

| Path                                   | Responsibility                                                                                                                |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `main.py:create_app`                   | Validate settings, configure logging/telemetry, compose middleware and `/api` routers; operation IDs use route function names |
| `config.py:Settings`                   | `.env`/environment parsing and fail-closed deployment validation; see [configuration](../reference/configuration.md)          |
| `core/middleware.py`                   | Request IDs/timing, origin validation, gateway isolation, private/no-store API responses and security headers                 |
| `core/rate_limit.py`                   | Atomic Redis counter/expiry limits, HMAC-pseudonymized identities and `Retry-After`                                           |
| `core/redis.py`                        | Shared async Redis client lifecycle                                                                                           |
| `core/logging.py`, `core/telemetry.py` | Structured logging and privacy-filtered error reporting                                                                       |
| `core/spreadsheets.py`                 | Shared spreadsheet safety helpers                                                                                             |
| `db/base.py`, `db/models.py`           | Declarative metadata, timestamp mixin and mapped entities                                                                     |
| `db/session.py`                        | Async engine (`pool_pre_ping=True`), `expire_on_commit=False`, request-scoped `get_session`                                   |
| `db/sync.py`                           | Synchronous engine for workers and CLI                                                                                        |
| `workers/celery.py`                    | Redis broker and task registration                                                                                            |
| `cli.py:app`                           | Typer application, installed as `flrc` by `pyproject.toml`                                                                    |

Endpoints explicitly commit their transactions. A yielded session is not an automatic commit. Do not use a synchronous DB connection or CPU-heavy PDF layout on the API event loop.

## Feature-module map

| `modules/` directory | Responsibility and primary implementation                                                                                                                                                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `academics`          | `assignments.py`: catalog/year discovery and assignment replacement; `columns.py`: definitions, rename/reorder/copy; `programme.py`: stage and assessment rules; `fields.py`, `class_names.py`: shared field/name semantics                                                                                                                                                                 |
| `administration`     | `classes.py`, `students.py`, `roster.py`: school/class/student/enrollment management; `roster_service.py`: shared roster validation; `users.py`: allowlist, roles, revocation and permanent deletion; `lifecycle.py`: year/semester transitions and rollover; `coordinator.py`: completion/missing cells; `report_identity.py`: names/signatures; `account_locks.py`: account-lock protocol |
| `archive`            | `router.py`: historical years, read-only class grids and student history                                                                                                                                                                                                                                                                                                                    |
| `audit`              | `router.py`: grade audit filtering and exports                                                                                                                                                                                                                                                                                                                                              |
| `auth`               | `router.py`: OAuth/logout; `dependencies.py`: identity/role/writable-state guards; `cookies.py`, `sessions.py`: signed IDs and Redis; `me.py`: session profile; `demo.py`: visitor identities; `test_router.py`: test-only sessions                                                                                                                                                         |
| `backup`             | Dump/encryption/Drive upload, restore tests, year archives, status, scheduling and CLI subcommands                                                                                                                                                                                                                                                                                          |
| `changes`            | `service.py`: atomic undo-record creation; `router.py`: recent actions and undo; `undo.py`: conflict-aware per-action restorers                                                                                                                                                                                                                                                             |
| `dashboard`          | `router.py`: one bounded operational summary for admin/coordinator landing pages                                                                                                                                                                                                                                                                                                            |
| `demo`               | Public metadata/operations routes, Neon restore orchestration, reset scheduling and reset gate                                                                                                                                                                                                                                                                                              |
| `grades`             | `router.py`: grid read/save, temporary override grants and grade-batch undo                                                                                                                                                                                                                                                                                                                 |
| `imports`            | `parser.py`: hostile XLSX parsing; `review.py`: editable/paged dry-run review; `router.py`: preview and commit; `fixture.py`: synthetic workbook                                                                                                                                                                                                                                            |
| `jobs`               | `service.py`: durable state/output transitions and purge; `router.py`: list/status/download authorization                                                                                                                                                                                                                                                                                   |
| `reports`            | Builder, report identity/branding overlays, Jinja templates, WeasyPrint renderer, packaging, filenames, previews and class sheets                                                                                                                                                                                                                                                           |
| `system`             | `router.py`: `/api/healthz`                                                                                                                                                                                                                                                                                                                                                                 |

Feature-first organization follows [ADR-019](../adr/019-feature-first-backend-and-dedicated-infrastructure-directory.md). Keep validation used by multiple write surfaces in the existing shared feature helpers, not a second endpoint-specific implementation.

## HTTP and error contract

`main.py` places application routers behind `current_user`; individual routes add admin/coordinator and expensive-operation dependencies. OAuth, health and demo metadata have separate entry paths. Test routes are only mounted for `ENV=test`.

Business errors normally use `HTTPException(status, {"code": "stable_code", ...})`, which FastAPI wraps as `{"detail":{"code":"stable_code",...}}`. Structured details may include counts, `reason` and `params`; clients translate codes rather than displaying backend prose. `undo_blocked` is a 409 with an actionable reason. Validation errors retain FastAPI's `detail` array, and middleware can return a top-level `{"code":"bad_origin"}`. Do not assume every failure has the same nesting or is JSON (downloads and gateways can fail too). Admin normalization is in `apps/admin/src/admin/feedback.ts`.

Origin checking applies to unsafe methods except token-authenticated `/api/ops/` routes. School mode requires an allowed exact Origin and rejects cross-site fetch metadata; dev/test may accept missing Origin. School gateway checks require `X-FLRC-Gateway` for `/api` except health and disguise a missing secret as 404. HTTPS, trusted-host checks and disabled interactive API docs are additional school-mode boundaries; details are in [authentication](auth-and-sessions.md) and the [security model](../security/security-model.md).

Rate limits are Redis-backed. Store failure is a 503 `security_service_unavailable` in school mode rather than bypassing protection. OAuth has separate login/callback burst and sustained budgets; expensive authenticated operations are per-account, not per-school NAT address. Exact budgets live in [reports and jobs](reports-and-jobs.md#limits) and [authentication](auth-and-sessions.md#oauth-rate-limits).

## Transaction and concurrency rules

- Grade saves lock current rows, compare `expected_version`, use conflict-safe insert for absent cells and increment versions on updates. Version zero represents an absent row. Explicit force resolution is audited; never silently overwrite stale edits.
- Save responses can contain applied cells alongside conflicts/rejections. Applied grades, audit rows and their batch share one commit. See [the data model](data-model.md#grades-and-history).
- Lifecycle mutations lock year and semester rows. Activation serializes against competing active-year changes. A write must validate its class against the writable semester's year.
- Account-related transactions call `lock_accounts` **before** admin actions and assignments, in ascending account-ID order. Readers use shared locks; account writers/permanent deletion use exclusive locks. Reload current state with `populate_existing`; `assignable` requires active and not deleted. This prevents reassigning, granting or restoring a deleted teacher during races: [ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md).
- Do not replace FK-preserving teacher anonymization with physical row deletion. Historical grade/audit authors must remain resolvable.

## Administrative undo and dashboard

`record_action` adds an `AdminAction` inside the original write transaction. Supported kinds cover student add/remove/move/edit/language, class create/edit/delete, column create/delete/edit/reorder/copy, account create/edit, signature upload/delete and assignment replacement. The response carries `action_id`. These records are available for seven days; lifecycle transitions and permanent teacher deletion are not ordinary undoable edits.

`POST /api/admin/actions/{action_id}/undo` locks relevant accounts before the action, checks expiry/already-undone status, and runs the matching `HANDLERS` restorer. If current state no longer permits restoration, it rolls back and returns `undo_blocked`, never partly restoring the old snapshot. Session revocation needed by a restored account change runs after commit. Expired snapshots/images are purged rather than kept indefinitely. See [ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md).

The dashboard (`modules/dashboard/router.py`, [ADR-079](../adr/079-admins-and-coordinators-land-on-one-dashboard.md)) focuses the active year, otherwise a setup/latest year. It combines term state/next action, setup gaps, expected/filled-cell completion, report readiness and missing printed teacher identities. Lists are bounded (`ITEM_LIMIT=50`); detailed screens remain the place to fix every item. No expected columns means unknown completion, **not** 100%. Frontend dashboard cards also consume jobs and recent administrative changes according to role.

## Workers and CLI

Celery accepts JSON only, ignores result-backend storage, prefetches one task, acknowledges late and rejects tasks when a worker is lost. Its broker visibility timeout is one hour. `workers/tasks/reports.py` and `exports.py` update PostgreSQL `job_runs`; rendering and retention are described in [reports and jobs](reports-and-jobs.md).

Run Python tools from `apps/backend` so `.env` and `alembic.ini` resolve correctly. `uv run flrc --help` exposes the maintenance entry point; command-specific behavior and destructive-command precautions belong in the [CLI reference](../reference/cli.md). Schema changes follow [migration rules](data-model.md#migrations-and-inspection).
