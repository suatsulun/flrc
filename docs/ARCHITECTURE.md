# FL-ReportCard — Architecture Companion

_Deep-theory companion to `HANDBOOK.md`. The handbook is the assembly manual. This file explains the decisions underneath the assembly: domain model reasoning, deployment boundaries, security/KVKK posture, save semantics, report generation, and operational tradeoffs._

## How to use this file

Read this when the handbook says "Why deeper: ARCH §x". Do not use it as a replacement for the handbook's step-by-step instructions. The handbook tells you what to type and how to check it; this document tells you why those instructions are shaped that way.

The project is an internal school report-card system. Its central constraints are:

1. **Small user count, high correctness requirement.** About 30 teachers may use it, but each saved grade matters.
2. **School data is sensitive.** Student data must not appear in source control, demo data, logs, crash reports, or third-party services that do not need it.
3. **The system must be cheap to run.** The chosen architecture deliberately fits free or near-free tiers.
4. **The project is also a learning portfolio.** It should use real production patterns without hiding all the hard parts behind a framework.
5. **The school year is a lifecycle.** Data changes state over time: draft, open, closed, archived, and reportable.

---

# §1 — Product shape and non-negotiables

## §1.1 The problem

Turkish school report cards are not merely a table of grades. Teachers need to enter scores, observations, skill ratings, second-language fields, and localized labels. Coordinators need to audit completeness. Admins need to manage yearly rosters and classes. At the end, the school needs printable report-card PDFs and safe archival.

The system therefore has four product surfaces:

- **Teacher daily surface:** fast, simple grade entry and observations.
- **Admin setup surface:** classes, students, teachers, teaching assignments, columns, imports, lifecycle controls.
- **Coordinator oversight surface:** completeness, exceptions, audit trails, report generation jobs.
- **Operations surface:** backups, restore drill, logging, deployment, rollback.

## §1.2 The architectural target

The target is a monorepo containing two React SPAs, one FastAPI backend, one Celery worker mode, and three shared TypeScript packages:

```text
fl-reportcard/
├── apps/
│   ├── teacher/
│   ├── admin/
│   └── api/
├── packages/
│   ├── ui/
│   ├── api-client/
│   └── i18n/
├── e2e/
└── docs/
    ├── HANDBOOK.md
    ├── ARCHITECTURE.md
    └── DECISIONS.md
```

The split is not aesthetic. Static frontends, API compute, slow background jobs, and cron-like maintenance all have different hosting and failure profiles. Forcing them into one deployable would make the free-tier math worse and the operational story harder.

## §1.3 What the app must not do

The app must not:

- store passwords;
- use real students in seed/demo data;
- store gender unless the school later proves a real requirement;
- put student names, scores, or comments in logs or Sentry payloads;
- let teachers save during closed semesters;
- silently overwrite another teacher's newer edit;
- generate official PDFs from stale or incomplete data without surfacing warnings;
- rely on Render's ephemeral filesystem for durable report bundles or backups;
- treat backup upload as proven until a restore drill has succeeded.

These "must nots" are the hidden backbone of many implementation choices.

---

# §2 — Runtime architecture and hosting boundaries

## §2.1 Deployables

The system has six deployable/runtime things:

1. `apps/teacher` — React SPA for normal teachers.
2. `apps/admin` — React SPA for admins/coordinators.
3. Public gateway — fixed path router composing the two SPAs and `/api/*` under one origin.
4. `apps/backend` — FastAPI web service.
5. `apps/backend` in worker mode — Celery worker, deployed separately.
6. GitHub Actions — CI, keep-alive, backup, demo reset, and release checks.

The two frontends are separate because they have different blast radii. A broken admin dialog should not block every teacher from saving grades. The teacher app must stay boring, fast, and narrow.

## §2.2 Deployment profiles

The project supports two deployment profiles with the same application images and configuration
contract.

The preferred managed profile uses:

- static hosting for frontends;
- Render free web service for the API;
- a second Render free web service for the worker;
- Neon Postgres with pooled app connections and direct migration connections;
- Upstash Redis for sessions and Celery broker messages;
- GitHub Actions for scheduled robots;
- school-owned Google Drive for backups and final export storage.

The school-hosted profile uses one school-controlled VM with Caddy, both compiled SPAs, FastAPI,
the Celery worker, PostgreSQL, and Redis orchestrated by Docker Compose. Only Caddy publishes host
ports; PostgreSQL and Redis remain on the internal container network. Persistent database storage
does not replace off-machine backups.

In the managed profile, the API and worker are allowed to sleep outside school hours. The
keep-alive schedule is a deliberate compromise: conserve Render free hours while preventing cold
starts during normal use. The worker has no official free worker dyno, so it runs as a web service
with a tiny health endpoint and a Celery process command.

This means every slow operation must be shaped as a job:

- enqueue request quickly;
- store durable status in Postgres;
- wake the worker if needed;
- poll job status through the API;
- keep Redis as a broker, not as the source of truth.

## §2.3 Same-origin proxy rule

The browser should call `/api/*` on its own origin. Vercel or Cloudflare Pages proxies that path to
Render in the managed profile; Caddy proxies it to the API container in the school-hosted profile.
The browser does not need to know which backend host or container exists.

This rule buys:

- first-party cookies;
- `SameSite=Lax` session behavior;
- minimal CORS;
- simpler CSRF protection;
- fewer environment-specific frontend URLs;
- fewer production-only auth bugs.

It is tempting to call Render directly from the SPA. Do not do that unless a future ADR explicitly replaces the cookie/session strategy.

## §2.4 Frontend hosts

Use Vercel for the personal demo if desired. Use Cloudflare Pages plus a narrowly configured
gateway for managed school production. If the school chooses its own VM, Caddy serves the
compiled SPAs and performs the same routing job.

The public browser boundary is one origin. The SPAs remain separate deployables, but the gateway
composes them by path:

Recommended production shape:

```text
flrc.<school-domain>/          → teacher SPA
flrc.<school-domain>/admin/*   → admin SPA
flrc.<school-domain>/api/*     → Render FastAPI
worker Render service          → Celery worker + /health
```

Supported school-hosted shape:

```text
flrc.<school-domain> → Caddy → teacher build at /
                            → admin build at /admin/*
                            → /api/* → FastAPI container
FastAPI + Celery worker   → private Postgres and Redis containers
off-machine backup        ← scheduled pg_dump
```

The admin build uses `/admin` as its Vite and client-router base path. Routing order is a security
and correctness requirement: `/api/*`, then `/admin` and `/admin/*`, then the teacher catch-all.
The gateway targets are fixed configuration, never user-provided URLs.

This topology deliberately keeps `flrc_session` host-only. Both panels receive the same cookie
because they use the exact same host; no parent-domain cookie is needed. The two SPAs therefore do
not have origin isolation from each other, and must never be treated as authorization boundaries.
FastAPI dependencies such as `require_admin` remain the boundary that protects admin operations.

The teacher SPA owns the only login screen. The admin route guard sends anonymous users there and
sends authenticated non-admins back to the teacher dashboard. OAuth always returns to the teacher
dashboard; an admin enters `/admin` through the role-gated link. This is intentional friction: it
keeps authentication errors and account selection in one UI instead of maintaining a second login
surface.

## §2.5 Database connection split

Use two database URL roles:

- `DATABASE_URL` — normal application traffic; this is pooled when the provider offers a pooler.
- `DATABASE_URL_DIRECT` — migrations and backup/restore operations; on a simple self-hosted
  PostgreSQL instance it may initially identify the same server.

Migrations through a transaction pooler can fail in confusing ways. The direct URL is not optional ceremony; it protects schema operations.

## §2.6 Worker status source of truth

Redis is a queue and session store. It is not the durable job database. Celery's result backend is intentionally avoided because Upstash command counts matter and because Postgres gives better auditability.

The `job_runs` table stores:

- job id;
- job type;
- requested by;
- status;
- progress counters;
- sanitized error code/message;
- artifact pointer;
- timestamps.

The UI reads job status from the API, and the API reads from Postgres.

---

# §3 — Domain model

## §3.1 Table inventory

The application deliberately uses fourteen core tables:

1. `users`
2. `teacher_allowlist`
3. `academic_years`
4. `classes`
5. `students`
6. `enrollments`
7. `teaching_assignments`
8. `sessions`
9. `report_columns`
10. `grade_values`
11. `delegate_grants`
12. `save_batches`
13. `audit_entries`
14. `job_runs`

The number matters because it reveals a design discipline: do not create one table per UI whim. Model durable business facts only.

### Why no `grades` table per subject?

Columns are data. A subject, skill, term, score, observation, or scale choice is represented by a configured `report_column`, not by a new SQL column or new table. This makes the school year configurable without migrations.

### Why no `class_id` on `grade_values`?

A grade belongs to a student enrollment, subject/assignment context, and report column. Classes are historical groupings that can change. Storing class directly on grade rows would create contradictions after roster moves.

### Why no gender column?

Gender is not required for report-card generation or grade entry. Import files may contain it; the importer should discard it. Do not store sensitive fields merely because a school spreadsheet includes them.

## §3.2 Lifecycle states

Academic years and semesters are state machines, not booleans.

Suggested year states:

- `draft` — setup is in progress; admins can import, edit, configure.
- `active` — teachers can work in currently open semesters.
- `closed` — no normal writes; reports and exports are allowed.
- `archived` — historical browsing only.

Suggested semester states:

- `setup`
- `open`
- `locked`
- `reported`

Every write endpoint that changes teacher-entered grade data must pass through a lifecycle dependency such as `writable_semester`. This avoids scattering calendar logic across services.

## §3.3 Columns as data

A `report_column` describes what a teacher can fill:

- academic year;
- term/semester;
- subject or subject group;
- skill category;
- label translations;
- column type;
- min/max or allowed values;
- ordering;
- required/optional status;
- report visibility;
- active/inactive status.

Default column sets use stable semantic identifiers in seed code, such as
`active_class_participation`, so the fixture remains readable when wording changes. Those
identifiers are not translation keys consumed by the frontend and are not persisted as the
display label. The seed resolves each identifier to a complete `tr`/`en`/`de`/`fr` label object
and stores that object with the column. This preserves the central rule that report definitions
are school-owned data rather than application chrome.

Column types should be explicit. Examples:

- numeric score;
- three-point skill scale;
- text observation;
- attendance/value code;
- second-language comment.

Do not let the frontend invent validation rules. The backend returns column definitions; the UI renders cells from those definitions; the save endpoint validates again using the same persisted rules.

## §3.4 Enrollment, assignments, and grants

`enrollments` answer: _Which student belongs to which class in which academic year?_

They also own the student's **school number for that year**. `students.id` is the stable identity;
`enrollments.school_number` is unique only inside one academic year. This is what lets a continuing
student receive a new number without rewriting history, and lets a different student reuse an old
number years later. Automatic rollover assigns promoted students fresh sequential numbers rather
than copying the archived values. A setup-year enrollment may still have no number during manual
preparation or import, and activation rejects the year until all numbers are present.

`teaching_assignments` answer: _Which teacher owns which subject/role for which class in which academic year?_

`users.teaching_field` constrains subject ownership: English permits `main` and `skills`; German and
French permit only their matching roles. English users also have a required `teaching_stage`
(`primary` for grades 1–4 or `middle` for grades 5–8). Both assignment routes enforce field and
stage; the assignment board can filter the same five operational groups: all, primary, middle,
German, and French.

`delegate_grants` answer: _Which teacher temporarily has permission to edit another teacher's area, who granted it, why, and until when?_

A teacher can save a cell only if:

1. the session is valid;
2. the user is allowed and active;
3. the academic year/semester is writable;
4. the report column is active and applicable;
5. the teacher owns the assignment or holds a live grant;
6. the submitted value matches the column type;
7. the optimistic version check passes.

The grant table exists so temporary coverage is auditable. Do not solve coverage by making everyone admin.

## §3.5 Grade save algorithm

The grade save path is the heart of the application.

Every editable cell has a version. The client sends:

```json
{
  "studentId": "...",
  "columnId": "...",
  "value": 91,
  "expectedVersion": 3
}
```

The backend performs structural checks, permission checks, then a compare-and-set update.

Conceptually:

```sql
UPDATE grade_values
SET value = :value,
    version = version + 1,
    updated_by = :user_id,
    updated_at = now()
WHERE student_id = :student_id
  AND column_id = :column_id
  AND version = :expected_version;
```

If `rowcount = 1`, the save applied. If `rowcount = 0`, someone else changed the cell first, or the row did not exist. The service then determines whether to insert, report conflict, or reject the write.

The response must be per-cell, not just `ok: true`, because a batch can partly apply:

- `applied`
- `conflict`
- `invalid`
- `forbidden`
- `stale_column`

A successful save also writes:

- one `save_batch` row for the button press;
- one or more `audit_entries` rows for meaningful changes.

The audit entry should not be noisy, but it must answer: who changed what, when, from which value to which value, and under what permission path.

## §3.6 Version zero

Version `0` means the client has no existing row for that student/column pair. It is an insert expectation, not an actual stored version. After insert, the server returns version `1`.

This lets the client use one dirty-map shape for both new and existing values.

## §3.7 Audit model

Audit is not a debugging log. It is a business record.

Audit entries should be structured and queryable:

- actor user id;
- action type;
- entity type;
- entity id;
- academic year;
- class/student/column context when relevant;
- old value/new value for grade changes;
- reason or grant id when relevant;
- request id;
- timestamp.

Never store sensitive free-form dumps. Store the minimum structured facts needed for accountability.

---

# §4 — Implementation architecture

## §4.1 Monorepo rationale

A monorepo is chosen because the API contract, shared UI, and locale bundles must evolve together. A grade cell shape change should be visible to the backend tests, generated client, and frontend typecheck in one PR.

The repo uses:

- pnpm workspaces;
- Turborepo task graph;
- internal TypeScript packages consumed as source;
- uv for Python;
- Docker Compose for local PostgreSQL 18/Redis;
- GitHub Actions for full validation.

## §4.2 Internal packages as source

`packages/ui`, `packages/i18n`, and `packages/api-client` are not published packages. They are workspace-internal source packages.

Benefits:

- no manual rebuild step;
- Vite hot reload sees shared UI edits;
- app imports look production-like;
- the repo stays small.

The risk is that some tooling expects packages to build to `dist/`. The handbook resolves that with explicit `main`/`types` fields and app-level Vite/TypeScript configuration.

## §4.3 Backend package layout

`apps/backend/src/flrc/` uses a feature-first layout. Code that changes for the same business
reason stays together, while genuinely shared technical infrastructure remains in `core/` and
`db/`:

```text
src/flrc/
├── core/               # middleware, logging, cross-cutting helpers
├── db/                 # engines, session dependencies, shared ORM metadata
├── modules/
│   ├── system/         # health and operational endpoints
│   ├── auth/           # OAuth, sessions, cookies, role dependencies
│   ├── academics/      # years, semesters, columns, assignments
│   ├── grades/         # grid reads, saves, conflicts, undo
│   ├── administration/ # roster and lifecycle administration
│   ├── imports/        # spreadsheet parsing, dry-run, commit
│   ├── reports/        # report data, templates, rendering, endpoints
│   ├── jobs/           # durable job state and endpoints
│   ├── audit/          # audit queries
│   └── archive/        # archival workflows
├── workers/            # Celery app, tasks, and worker health process
├── cli.py              # Typer commands
├── config.py           # Settings
└── main.py             # FastAPI app factory
```

Each feature may contain a router, schemas, services, and feature-specific queries. Routers should
stay thin. Do not create a global `schemas/` or `services/` dumping ground merely because two files
have the same technical role. Permission checks and domain decisions belong in services and
dependencies. SQLAlchemy statements should be testable without a running server.

## §4.3.1 Infrastructure layout

Deployment orchestration lives under `infra/`. Development services use
`infra/compose/compose.dev.yaml`; a school-controlled VM uses
`infra/compose/compose.production.yaml` plus `infra/caddy/Caddyfile`; managed-provider definitions
live in provider-named folders such as `infra/render/`. Application-specific Dockerfiles remain
beside the applications they build.

The managed and school-hosted profiles must consume the same images and environment-variable
contracts. Neon, Upstash, and Render are deployment choices, not imports inside business code.

## §4.4 FastAPI dependency architecture

Dependencies are the app's security gates. Important dependencies include:

- `current_user`
- `require_admin`
- `require_coordinator`
- `writable_semester`
- `assigned_teacher_or_grant`
- `request_id_context`

Do not duplicate role logic inside every route. If a route mutates protected data, it should compose the correct dependency chain.

## §4.5 Alembic and schema discipline

Rules:

1. Models define intended schema.
2. Alembic autogenerate creates migration candidates.
3. The developer reads every generated migration.
4. Applied migrations are never edited.
5. Data migrations are explicit and reversible when possible.
6. CI runs migrations on a clean database.

A migration is part of the product. Treat it as code, not generated trash.

## §4.6 Synthetic-data doctrine

Seed data must be fictional. Use `Faker(locale="tr_TR")` with deterministic seeds. Never paste real student names, real classes, real teacher emails, or real grades into the repo.

Screenshots for portfolio/demo should use synthetic data only. This is a KVKK boundary and a professional habit.

## §4.7 OAuth and sessions

The app uses Google OAuth/OIDC for identity and server-side sessions for persistence.

Login flow:

1. user clicks login;
2. backend redirects to Google with state;
3. Google returns code;
4. backend exchanges code and validates ID token;
5. backend requires the exact hosted-domain claim, a verified school email, and an active
   pre-registered allowlist row;
6. first login binds that row to Google's stable `sub` identifier; later logins must match it;
7. backend creates a Redis-backed session;
8. browser receives a signed, host-only, HttpOnly session cookie.

The browser never stores access tokens. The cookie contains only a signed session id, not user facts.

## §4.8 Domain claim and allowlist

The Google `hd` claim is a domain proof, not merely a UI hint. Still, domain membership is not enough. The teacher must also be on the app's allowlist.

This gives two gates:

- the account belongs to the school domain;
- the school/admin intentionally allowed that teacher.

Departed teacher handling is immediate: deactivate allowlist entry and revoke/delete active sessions.
The stable Google subject prevents a newly created account that reuses a departed teacher's email
from inheriting access. Resetting that binding is an explicit admin action performed only while the
allowlist row is inactive.

All school-data routers are included under one FastAPI router dependency on `current_user`.
Endpoint-specific role dependencies remain, but a newly added data endpoint cannot accidentally
become anonymous merely because its author forgot the local guard.

## §4.9 Contract generation

FastAPI produces OpenAPI. `@hey-api/openapi-ts` consumes the committed OpenAPI snapshot and generates the TypeScript client plus Query hooks.

Contract rule:

- backend schema changes;
- export OpenAPI;
- regenerate client;
- commit both;
- CI fails if regeneration produces a diff.

No frontend code should hand-write request/response types that already exist in OpenAPI.

## §4.10 i18n from day one

UI chrome uses `i18next` resource bundles. Database-stored report labels are localized records
because the school may customize them. Built-in seed definitions follow the same boundary:
semantic identifiers organize the backend fixture, while their four-locale values are written to
Postgres rather than copied into browser translation bundles.

Rules:

- API returns stable machine codes for errors and statuses;
- frontend translates machine codes;
- report column and group labels are stored per locale, with Turkish as the required fallback;
- deterministic seed columns provide Turkish, English, German, and French values that fluent
  school staff review before production;
- seed-only semantic identifiers never become a second runtime translation system;
- no literal UI strings in production components after the i18n step lands.

## §4.11 Error handling philosophy

Backend errors should be stable and machine-readable:

```json
{
  "code": "SEMESTER_LOCKED",
  "message": "This semester is locked.",
  "details": {}
}
```

The frontend displays localized user-facing text. Logs include the code and request id, not student data.

---

# §5 — Teacher grid architecture

## §5.1 Server state vs unsaved human input

TanStack Query owns server-confirmed data. Zustand owns dirty, unsaved edits.

This separation prevents the most common grid bug: mixing optimistic local edits into the same cache that claims to represent the server. A dirty cell can visually override the cached value, but it should remain distinguishable until the server confirms it.

## §5.2 Dirty map

The dirty map key should be deterministic, for example:

```text
studentId:columnId
```

Each dirty entry stores:

- typed value;
- expected server version;
- validation state;
- last edited timestamp;
- optional client-side note/error.

The header Save button observes dirty count. The leave guard blocks navigation when dirty count is nonzero.

## §5.3 Cell components

Grid cells should be small, typed components:

- `ScoreCell`
- `ScaleCell`
- `TextCell`
- possibly `ReadonlyCell` or `ConflictCell`

They receive column definition, student context, server value, and dirty state. They should not fetch data themselves.

## §5.4 No premature virtualization

A class has roughly 20–35 rows. Column count can be moderately high but still manageable. Virtualization adds keyboard, focus, pinned column, and accessibility complexity. Do not add it until measured performance proves it is needed.

The learning target is cell semantics and save correctness, not virtualization theater.

## §5.4.1 Table-first navigation

The grid is not a destination hidden behind a dashboard. Teacher routes expose academic year,
semester, grade, subject, and same-grade class tabs directly above the grid, and the default route
opens the first usable board. Admin uses the same table metaphor for roster setup: class tabs are
drop targets, students are rows, and column/teacher controls live at the table boundary. This keeps
the dominant object—the class table—stable while its context changes.

All primary tables use the document as their only vertical scrolling surface. They do not create
horizontal or nested vertical scroll containers: fixed-layout columns divide the available width,
cell controls shrink to their column, and long labels wrap. Class and context tabs wrap as well.
This makes every field discoverable without a hidden sideways region. The shared shell's side and
top panels can be minimized for more working width, but the expanded layout must still fit every
column. While a student is dragged, holding the pointer near the viewport's top or bottom edge
auto-scrolls the document so distant class tabs remain reachable.

## §5.5 Conflict UX

When a cell conflicts:

- show the server's current value;
- show the user's unsaved attempted value;
- identify who changed it when possible;
- let the teacher keep theirs, accept server value, or cancel;
- never silently overwrite.

Conflict handling must be understandable to teachers who do not care about optimistic concurrency.

---

# §6 — Admin, importer, and lifecycle architecture

## §6.1 Admin CRUD scope

Admin features exist to support the school year, not to become a generic school information system.

Included:

- students;
- classes;
- enrollments;
- teacher allowlist;
- teaching assignments;
- report columns;
- academic year/semester lifecycle;
- imports;
- audit and completeness views.

Excluded unless future ADR says otherwise:

- attendance management outside report-card needs;
- parent accounts;
- payments;
- discipline records;
- birthdate/gender/ID fields not needed for reports.

## §6.2 Importer philosophy

The importer must treat Excel as hostile input.

It should:

- search for headers instead of assuming row 1;
- tolerate Turkish casing and whitespace variation;
- report exact sheet/cell addresses for errors;
- parse into typed Pydantic row models;
- discard columns the app does not store;
- produce a dry-run summary before commit;
- commit only if the uploaded file hash matches the dry-run hash.

Dry-run and commit must be separated because import mistakes are high-impact.

## §6.3 Dry-run hash handshake

Dry-run returns:

- parsed counts;
- warnings;
- blocking errors;
- proposed class/student/enrollment changes;
- file SHA-256;
- short-lived import token or server-side staging reference.

Commit must include the same SHA-256. This prevents "dry-run file A, commit file B" accidents.

## §6.4 Lifecycle controls

Lifecycle transitions should be explicit button actions with confirmation and preflight checks.

Examples:

- open semester;
- lock semester;
- mark reports generated;
- close academic year;
- archive academic year.

Each transition writes an audit entry. Some transitions require no incomplete required fields. Others may allow exceptions but must surface them.

## §6.5 Archive browsing

Archived data is read-only. The UI may let admins and coordinators browse previous years, but write routes must reject changes at the dependency layer.

Longitudinal student history should derive from enrollments and grade/report data, not by mutating old rows into a new shape.

Closing a standard `YYYY-YYYY` year after both semesters are locked creates the next setup year in
the same transaction. Class structure, teacher assignments, column templates, promoted grade 1–7
students, and second-language choices are copied. Grade values, old school numbers, audit entries,
and grade 8 enrollments are not copied. The promoted enrollment keeps the same student id, which is
the longitudinal connection, and receives a fresh sequential number in the new year. A partial
unique index permits at most one `open` semester per year; transitions lock the old semester before
opening another.

---

# §7 — Reports, jobs, exports, and operations

## §7.1 Report rendering shape

Reports are produced from a typed report context:

```text
student + enrollment + class + year + term + columns + values + localized labels
```

The renderer should not query random tables from inside templates. Build a report DTO first, then pass it to Jinja2.

## §7.2 HTML-to-PDF choice

Jinja2 + WeasyPrint is chosen because report cards are layout-heavy documents and the project owner already knows HTML/CSS. CSS `@page`, page breaks, tables, and print-specific styling are easier to reason about than coordinate-based PDF drawing.

The Docker image carries WeasyPrint's system dependencies so production matches local execution.

## §7.3 Job model

PDF batches and exports are jobs because they can be slow.

A report generation request should:

1. create a `job_runs` row;
2. enqueue a Celery task with the job id;
3. return immediately;
4. let the frontend poll `/api/jobs/{id}`;
5. update progress in Postgres;
6. store final artifact in durable storage;
7. expose a short-lived download route.

## §7.4 Artifact durability

Do not rely on Render filesystem for final report bundles. Render's filesystem is ephemeral. Use a durable target such as school-owned Google Drive or object storage. Local temp files are allowed only during rendering.

## §7.5 Backups

The system needs backups because Neon's restore window is not the whole recovery strategy.

Minimum backup story:

- weekly `pg_dump` from direct database URL;
- encrypted or access-controlled upload to school-owned Google Drive folder;
- retention policy;
- logged success/failure;
- alert path when backup fails;
- documented restore drill.

## §7.6 Restore drill

A backup is unproven until restored.

Restore drill procedure:

1. create temporary database or branch;
2. restore latest dump;
3. run smoke queries;
4. verify expected row counts;
5. run app against restored DB in safe mode if needed;
6. record the result in an operations log.

---

# §8 — Security, privacy, and KVKK posture

## §8.1 Data minimization

Store only what the report-card workflow needs.

Allowed core data:

- student display name;
- student number if required by school reports;
- class/enrollment;
- teacher school email;
- report values;
- audit metadata;
- report artifacts;
- job status.

Avoid by default:

- gender;
- birthdate;
- national ID;
- parent contact data;
- health/disability notes;
- free-form sensitive comments outside report needs.

## §8.2 Authentication and authorization

Authentication answers who the user is. Authorization answers what they may do.

Never assume domain membership equals authorization. Use the allowlist and assignments.

Authorization should be enforced on the backend even if the frontend hides buttons.

## §8.3 Session security

Session cookie requirements:

- `HttpOnly`;
- signed session id;
- `SameSite=Lax`;
- `Secure` in production;
- eight-hour absolute TTL;
- server-side revocation.

CSRF protection is still needed for unsafe methods. Same-origin proxying makes it simpler, not irrelevant.
School mode requires the exact Origin on unsafe methods, disables OpenAPI/docs, rejects untrusted
Host headers, redirects HTTP to HTTPS, and applies a streaming request-body limit. The managed API
origin also requires a secret header injected by the Cloudflare gateway; only the information-free
liveness route bypasses that origin gate.

## §8.4 Logging policy

Logs may contain:

- request id;
- route;
- status code;
- duration;
- user id or hashed user id;
- error code;
- job id;
- counts.

Logs must not contain:

- student names;
- student numbers;
- grade values;
- teacher comments;
- raw Excel rows;
- OAuth tokens;
- cookies;
- full request bodies.

## §8.5 Demo and repository safety

Synthetic data only. This rule applies to:

- seed scripts;
- screenshots;
- tests;
- fixture Excel files;
- demo database;
- README examples;
- bug reports;
- commit messages.

The repo should be safe to show a recruiter without leaking a child’s personal data.

## §8.6 Sentry and telemetry

Sentry may be used for crash reporting only with data scrubbing.

Required posture:

- `send_default_pii=False`;
- set `max_request_body_size="never"` and `include_local_variables=False`;
- scrub event and breadcrumb request bodies, URLs, and query strings;
- scrub cookies and authorization headers;
- do not attach Excel files;
- use release/version tags;
- sample conservatively.

## §8.7 Access review

Before launch and at least once per term:

- review teacher allowlist;
- remove departed teachers;
- verify admins/coordinators;
- revoke unnecessary grants;
- confirm backup folder ownership;
- confirm OAuth client ownership.

---

# §9 — Testing strategy

## §9.1 Backend tests

Backend tests should cover:

- model constraints;
- lifecycle write gates;
- OAuth/session helpers where feasible;
- teacher permission checks;
- grade save apply/conflict behavior;
- importer dry-run parsing;
- importer commit hash mismatch;
- report context assembly;
- job status transitions.

Use dependency overrides to fake users. Do not require real Google login for normal test runs.

## §9.2 Frontend tests

Frontend tests should focus on high-value behavior:

- dirty map behavior;
- Save button state;
- conflict dialog rendering;
- route guards;
- admin form validation;
- job polling UI.

Do not snapshot every component. Test behavior that can break teacher work.

## §9.3 E2E tests

Playwright should cover the actual risks:

- login/session smoke through test harness or seeded auth;
- teacher saves a grade;
- admin closes semester and teacher cannot write;
- two teachers edit same cell and conflict appears;
- report job starts and reaches downloadable status;
- archive year is browse-only.

The two-user test must use isolated browser contexts or request contexts. Sharing storage state will hide the exact bug the test exists to catch.

---

# §10 — Deployment and rollback

## §10.1 Environments

Use at least:

- local dev;
- demo;
- school production.

Do not reuse OAuth clients, databases, or secrets across those environments.

## §10.2 Deployment order

Typical safe order:

1. run CI;
2. apply database migrations;
3. deploy API;
4. deploy worker;
5. deploy frontends;
6. run smoke test;
7. watch logs/Sentry.

For breaking API/client changes, use backward-compatible transitions or deploy in a sequence that prevents old frontend/new backend mismatch.

## §10.3 Rollback

Rollback must be documented before launch.

Frontend rollback is usually easiest: redeploy previous static build. API rollback is harder if migrations changed schema. Any destructive migration requires a special decision record and backup confirmation.

## §10.4 First-week operations

During the first week:

- check job queue daily;
- check backup action result;
- watch Sentry;
- collect teacher friction points;
- avoid adding features unless a blocker appears;
- record operational issues and follow-up actions in the appropriate operations log.

---

# §11 — Performance expectations

The app should feel instant for normal teacher operations.

Expected scale:

- around 30 teachers;
- classes around 20–35 students;
- limited concurrent edits;
- report generation in batches;
- one school database.

This means the bottleneck is not raw scale. The real bottlenecks are cold starts, PDF rendering, accidental N+1 queries, and over-rendering the grid on every keystroke.

Optimization order:

1. correctness;
2. query shape;
3. UI render stability;
4. job offloading;
5. caching;
6. only then advanced performance machinery.

User-visible latency is treated as state, not as an absence of UI. The first unresolved query on a
page shows a skeleton plus a non-blocking activity indicator. Mutations disable their initiating
control and overlay a spinner without changing the control's width. Long jobs also publish toast
state transitions, while errors use the same in-app feedback system. The teacher and admin class
workspaces prefetch the other class tabs in the selected grade after the current table settles;
this bounded warm-up is at most one grade's A–G classes, not the whole school, and each browser
warms those tabs sequentially to avoid multiplying a twenty-user arrival into a large request burst.

The four direct PDF report sets remain synchronous at the API boundary (ADR-028), but the browser
fetches the PDF as a blob while keeping a user-opened tab in a generating state. When rendering
finishes that same tab receives the PDF and the initiating button returns to idle. Whole-year XLSX
exports remain durable background jobs with queued/running/succeeded/failed toast transitions.

---

# §12 — Configuration inventory

Core backend settings:

```text
ENV
DATABASE_URL
DATABASE_URL_DIRECT
REDIS_URL
SESSION_SECRET
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
ALLOWED_GOOGLE_DOMAIN
FRONTEND_ORIGIN
ADMIN_ORIGIN
TRUSTED_HOSTS
GATEWAY_SECRET
SESSION_TTL_SECONDS
MAX_REQUEST_BODY_BYTES
WORKER_HEALTH_URL
OPS_TOKEN
SENTRY_DSN
DRIVE_BACKUP_FOLDER_ID
GOOGLE_APPLICATION_CREDENTIALS_JSON
REPORT_ARTIFACT_TTL_HOURS
```

Rules:

- `.env.example` documents required settings;
- `.env` is never committed;
- production secrets live in host secret settings;
- CI uses dedicated test values;
- secrets must never appear in screenshots or docs.

---

# §13 — Decision index

The living decision log is `DECISIONS.md`. This architecture companion assumes at least the following decisions exist:

- ADR-001 — Monorepo with pnpm and Turborepo.
- ADR-002 — Two separate SPAs.
- ADR-003 — FastAPI instead of Django/DRF.
- ADR-004 — Same-origin proxy for `/api/*`.
- ADR-005 — Server-side sessions over JWT/localStorage tokens.
- ADR-038 — Fail-closed school authentication and managed-origin isolation.
- ADR-006 — Synthetic demo data only.
- ADR-007 — No direct class FK on grade rows.
- ADR-008 — Columns as data.
- ADR-009 — Celery on Redis with Postgres job state.
- ADR-010 — Jinja2 + WeasyPrint for PDFs.
- ADR-011 — Neon pooled/direct URL split.
- ADR-012 — Google OAuth + allowlist.
- ADR-013 — i18n from first component.
- ADR-014 — TanStack Query for server state, Zustand for dirty state.
- ADR-015 — Excel dry-run before commit.
- ADR-016 — Lefthook for polyglot hooks.
- ADR-017 — Cloudflare Pages for school production frontends.

---

# §14 — Change rule

When the implementation deviates from this architecture:

1. stop and name the deviation;
2. decide whether it is a bug, simplification, or improvement;
3. update `DECISIONS.md` if the reason will matter later;
4. update this file only if the architecture itself changed;
5. continue only after the handbook step's Check is green again.

The architecture is not sacred. Hidden, undocumented drift is the enemy.
