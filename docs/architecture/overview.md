# Architecture overview

FL-ReportCard manages school-year rosters, language assessments and printable report cards. Read this when finding your way around the repository or tracing a change across the browser, API and worker.

## Users and boundaries

| User          | Working surface                        | Responsibility                                                                                                               |
| ------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Teacher       | Teacher SPA at `/`                     | Enter assessments, resolve save conflicts, undo the last grade save, print class sheets and preview assigned students' cards |
| Coordinator   | Admin SPA at `/admin/` and teacher SPA | Monitor completion and report readiness, inspect coordinator views and generate reports                                      |
| Administrator | Both SPAs                              | Manage accounts, rosters, assignments, columns, lifecycle, administrative undo and exports                                   |
| Demo visitor  | Both SPAs in public-demo mode          | Temporary pseudonymous administrator of synthetic shared data                                                                |

Roles are independent user flags, not separate login systems. Hiding a button is not authorization: API dependencies enforce permissions. See [authentication and sessions](auth-and-sessions.md).

## Runtime topology

```text
Browser ── one public origin ── /          → teacher SPA
                            ├─ /admin/*   → admin SPA
                            └─ /api/*     → FastAPI
                                             ├─ PostgreSQL
                                             └─ Redis → Celery worker → PostgreSQL job state/output
```

Both React SPAs are static builds. FastAPI serves business APIs; the same Python package supplies Celery tasks and the maintenance CLI. PostgreSQL holds durable school data, history and job outputs. Redis holds revocable sessions, rate-limit counters and Celery messages—not authoritative job results.

The gateway must route `/api/*` before `/admin/*` before the teacher fallback. Both panels share a host-only session cookie; separate builds do not provide origin isolation. This is [ADR-022](../adr/022-one-public-frontend-origin-with-the-admin-spa-under-admin.md), built on [ADR-004](../adr/004-same-origin-proxy-for-api.md). Deployment variants belong in [deployment](../operations/deployment.md), not business code.

## Repository map

| Directory/package                                                    | Role                                                                                               |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `apps/backend` (`@flrc/backend`, Python distribution `flrc-backend`) | FastAPI, SQLAlchemy, Alembic, Celery, CLI, importer, reports and backend tests                     |
| `apps/teacher` (`@flrc/teacher`)                                     | Grade grid, single-student stepper, class report and card previews                                 |
| `apps/admin` (`@flrc/admin`)                                         | Dashboard, setup, school lifecycle, reports, audit and undo                                        |
| `packages/api-client` (`@flrc/api-client`)                           | OpenAPI snapshot, generated TypeScript SDK/types/Query factories, shared session query             |
| `packages/ui` (`@flrc/ui`)                                           | Shared shell, controls, grade cells, responsive cards, skeletons, theme and file delivery          |
| `packages/i18n` (`@flrc/i18n`)                                       | Turkish, English, German and French UI resources and academic labels                               |
| `branding` (`@flrc/branding`)                                        | Generic identity source, generation and runtime branding integration                               |
| `infra`                                                              | Local Compose services, web gateway/image, school deployment template and managed-host definitions |
| `scripts`                                                            | Branding generation/checks, translation checks, telemetry tests and proxy checks                   |
| `e2e`                                                                | Playwright browser scenarios using synthetic accounts and school data                              |
| `docs`                                                               | Architecture, workflows, operations, security, references and numbered ADRs                        |
| `.github`                                                            | Workflows and dependency-update configuration                                                      |
| `.vscode`                                                            | Shared editor settings and extension suggestions                                                   |

`node_modules` and `.turbo` are generated dependency/cache directories; `.git` is version-control metadata. Root workspace/task configuration is in `pnpm-workspace.yaml`, `package.json` and `turbo.json`. Backend dependencies are separately locked in `apps/backend/uv.lock`.

## Follow one grade save

1. A shared grade cell records the teacher's draft in `apps/teacher/src/grid/dirty-store.ts`, keyed by `studentId:columnId`, including the server version it was based on. No write has reached the server.
2. `useSaveGrid` submits typed cells through generated `saveGridMutation` to `POST /api/classes/{class_id}/grid/save`, using the browser's own origin.
3. The gateway proxies the request. FastAPI middleware checks the mutation origin; `current_user` verifies the signed cookie, Redis session and active account. `writable_semester` requires an open semester in an active year.
4. `modules/grades/router.py` holds the caller's account lock, checks the class/year, active columns, subject roster, value types and assignment/grant confirmation. Existing grade rows are locked; their versions must match unless the user explicitly forces conflict resolution.
5. Applied cells, their `AuditEntry` rows and one `SaveBatch` commit together. The response separates `applied`, `conflicts` and `rejected`; partial application is part of the contract.
6. `mergeSavedGrid` merges confirmed values/versions into TanStack Query and clears only matching submitted drafts. Its generation check prevents a late response from resurrecting discarded edits. Related class-sheet queries are invalidated.
7. Reports later read the saved database values, not browser drafts. One-class PDFs are direct responses; larger selections use durable background jobs. See [reports and jobs](reports-and-jobs.md).

## Where to look

- Endpoint/module ownership, errors, locks, dashboard and administrative undo: [backend](backend.md).
- Routes, caches, dirty state, skeletons and responsive composition: [frontend](frontend.md).
- Tables, lifecycle and migrations: [data model](data-model.md).
- Identity, role guards and revocation: [authentication](auth-and-sessions.md).
- Turkish school vocabulary and project terms: [glossary](../reference/glossary.md).
- Commands and checks: [local development](../getting-started/local-development.md), [testing](../development/testing.md) and [CLI reference](../reference/cli.md).
