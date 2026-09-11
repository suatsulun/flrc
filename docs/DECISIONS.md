# FL-ReportCard: Decision Log

_Architecture Decision Records for the project. Each decision explains the choice, the alternatives rejected, and the consequences. Add new records when the project changes direction or when a future maintainer would ask, "Why is it like this?"_

## Reading the current state (2026-09-11)

Records preserve the reasoning at their date; later explicit amendments take precedence over
superseded parts. ADR-060's middle-English comments are superseded by ADR-063, while its grade-4
German/French comments remain. ADR-053 to ADR-058 supply the current image/deployment/backup
layout. The original fourteen-table design now includes `demo_visitors` and
`report_identity_audits`.

At this documentation refresh, ADR-063 and its implementation were still uncommitted.
Year-label ordering and bounded PDF layout/fallback changes were also pending. No new architecture
decision is asserted for those maintenance edits. See [TODO.md](TODO.md) for review gates and
[AI-HANDOFF.md](AI-HANDOFF.md) for the next AI's review scope. Accepted means a decision was made;
it does not prove a test run, migration, release publication, or deployment.

## Status values

- **Accepted**: current project direction.
- **Superseded**: replaced by a later ADR.
- **Proposed**: not final yet.

---

# ADR-001: Monorepo with pnpm workspaces and Turborepo

**Status:** Accepted  
**Phase:** 1.1

## Context

The project contains two React SPAs, one Python backend, generated TypeScript client code, shared UI components, shared i18n bundles, E2E tests, and documentation. These parts must change together.

## Decision

Use one repository with pnpm workspaces and Turborepo. TypeScript packages under `packages/*` are consumed as source. The Python API participates in the Turbo graph through an `apps/backend/package.json` shim that delegates to `uv`.

## Alternatives considered

- Separate frontend/backend repos.
- Nx monorepo.
- npm workspaces without Turborepo.
- A single app folder without packages.

## Consequences

- One PR can change API schema, generated client, UI, and tests together.
- CI can validate the whole project from one root command.
- The repo teaches modern full-stack monorepo practice.
- Tooling setup is slightly more complex on day zero.

---

# ADR-002: Two separate SPAs: teacher and admin

**Status:** Accepted  
**Phase:** 1.1

## Context

Teachers and admins use different workflows. The teacher app must remain fast and low-risk. Admin features are broader, more dangerous, and less frequently used.

## Decision

Build `apps/teacher` and `apps/admin` as separate Vite React SPAs.

## Alternatives considered

- One React app with role-based routes.
- Server-rendered admin pages inside FastAPI.
- One Next.js application.

## Consequences

- Smaller teacher bundle.
- Admin bugs are less likely to break teacher grade entry.
- The two builds can deploy independently even when a gateway composes them under one public
  origin.
- Some layout/auth code must be shared through packages instead of one app tree.

---

# ADR-003: FastAPI instead of Django/DRF or Express

**Status:** Accepted  
**Phase:** 1.3

## Context

The backend needs typed request/response schemas, dependency-based auth guards, OpenAPI generation, async database access, and good testability. The project is also intended as a portfolio project.

## Decision

Use FastAPI with Pydantic v2, SQLAlchemy 2.0, Alembic, and uv.

## Alternatives considered

- Django + Django REST Framework.
- Flask.
- Node/Express or NestJS.
- SQLModel.

## Consequences

- OpenAPI generation becomes the source for the TypeScript client.
- Dependency injection becomes the main security composition mechanism.
- The project demonstrates a real Python backend stack.
- More admin functionality must be built manually than in Django.

---

# ADR-004: Same-origin proxy for `/api/*`

**Status:** Accepted  
**Phase:** 1.10 / deployment

## Context

Cross-site cookies and browser auth flows are easy to misconfigure. The app needs secure sessions without storing tokens in localStorage.

## Decision

The browser calls `/api/*` on the frontend origin. Vercel or Cloudflare Pages proxies those requests to the Render API service.

## Alternatives considered

- SPA calls Render API URL directly.
- JWTs stored in localStorage.
- Full CORS setup with cross-site cookies.

## Consequences

- Cookies are first-party from the browser's point of view.
- `SameSite=Lax` is practical.
- CSRF protection is simpler.
- Frontend environment configuration is smaller.
- Hosting rewrites/functions become part of the deployment contract.

---

# ADR-005: Server-side sessions over JWTs

**Status:** Accepted  
**Phase:** 1.7

## Context

The school must be able to revoke a teacher's access immediately. Browser-stored tokens increase theft risk and make logout/revocation harder.

## Decision

Use server-side sessions. The browser stores only a signed `HttpOnly` session id cookie. Session
data lives in Redis with an absolute TTL of at most eight hours.

## Alternatives considered

- JWT access tokens in localStorage.
- JWTs in cookies.
- Third-party auth session provider.

## Consequences

- Departed teachers can be revoked by deleting Redis sessions.
- The browser never sees OAuth tokens.
- Redis availability matters for active sessions.
- Session middleware and CSRF checks must be implemented carefully.

---

# ADR-006: Synthetic demo data only

**Status:** Accepted  
**Phase:** 1.6 and all demos

## Context

The project handles children's school data. Real data in source control, demos, tests, logs, or screenshots would be unacceptable.

## Decision

Use deterministic `Faker(tr_TR)` seed data for all demos, tests, and screenshots. Never commit real student or teacher data.

## Alternatives considered

- Anonymized real data.
- Small hand-written examples based on real rosters.
- No demo data.

## Consequences

- Portfolio screenshots are safe.
- Tests are reproducible.
- Some fake data may not match every real school edge case.
- Importer fixtures must also be synthetic.

---

# ADR-007: Grade rows do not directly reference classes

**Status:** Accepted  
**Phase:** 1.5 / 2.6

## Context

Students can move classes. Historical report values should remain tied to the student/year/column context without becoming inconsistent when class membership changes.

## Decision

Represent class membership through `enrollments`. Grade values do not store a direct `class_id` as their core identity.

## Alternatives considered

- Store `class_id` on every grade value.
- Store one grade table per class.
- Snapshot full class context into every grade row.

## Consequences

- Class moves do not corrupt grade identity.
- Queries must join through enrollment/year context where class filtering is needed.
- The data model separates historical membership from cell values.

---

# ADR-008: Report columns are data, not schema

**Status:** Accepted  
**Phase:** 2.1

## Context

Schools may need different report-card columns by year, subject, language, or term. Changing SQL schema for each report-card adjustment would be brittle.

## Decision

Store report columns as data. The implemented table is named `column_definitions`; the earlier
design called it `report_columns`. The grid and reports render from those definitions.

## Alternatives considered

- Hardcoded columns in frontend.
- SQL column per report-card field.
- JSON blob per student.

## Consequences

- Admins can configure columns without migrations.
- The frontend can render typed cells from server-provided definitions.
- The backend must validate values against column definitions on every save.
- Report generation must respect column ordering and localization.

---

# ADR-009: Celery with Redis broker and Postgres job state

**Status:** Accepted  
**Phase:** 4.3

## Context

PDF generation and year exports can be slow. Teachers should not wait behind long-running work. Render's free tier lacks a native worker service, and Upstash Redis command counts are limited.

## Decision

Use Celery with Upstash Redis as the broker. Run the worker as a Render web service with a `/health` endpoint. Store job state in Postgres `job_runs`, not in Celery's Redis result backend.

## Alternatives considered

- Run PDF generation synchronously in FastAPI.
- ARQ or Dramatiq.
- Celery Redis result backend.
- Paid Render worker.

## Consequences

- The project demonstrates Celery, a useful backend skill.
- Worker wake-up and quiet Celery settings are required.
- Job status is durable and auditable in Postgres.
- Operational complexity increases.

---

# ADR-010: Jinja2 + WeasyPrint for PDFs

**Status:** Accepted  
**Phase:** 4.2

## Context

Report cards are visual, bilingual, and print-sensitive. The developer already knows HTML/CSS, and the project should reuse those skills.

## Decision

Render report contexts through Jinja2 templates and convert HTML/CSS to PDF with WeasyPrint.

## Alternatives considered

- ReportLab.
- Headless Chromium print-to-PDF.
- LaTeX.
- Typst.

## Consequences

- Report layouts are authored in HTML/CSS.
- Docker must include WeasyPrint system dependencies.
- Page sizing and print CSS become part of the test surface.
- Typst remains a possible future experiment, not the main path.

---

# ADR-011: Neon pooled/direct URL split

**Status:** Accepted  
**Phase:** 1.5 and deployment

## Context

Neon provides pooled and direct connection URLs. Transaction poolers are useful for app traffic but problematic for DDL and some migration operations.

## Decision

Use the pooled URL for normal app connections and the direct URL for Alembic migrations, backups, and restore operations.

## Alternatives considered

- Use pooled URL everywhere.
- Use direct URL everywhere.
- Host Postgres manually.

## Consequences

- Migrations are more reliable.
- App traffic benefits from pooling.
- Configuration has two database URLs that must not be confused.

---

# ADR-012: Google OAuth plus explicit allowlist

**Status:** Accepted  
**Phase:** 1.7 / 3.2

## Context

The school already has Google Workspace accounts. The app should not store passwords. Domain membership alone is not a full authorization policy.

## Decision

Use Google OAuth/OIDC for identity, verify the hosted-domain claim, then require a matching active teacher allowlist entry.

## Alternatives considered

- Email/password accounts.
- Google OAuth domain only.
- Magic links.
- External auth provider such as Auth0/Firebase/Clerk.

## Consequences

- No password storage.
- Admins can deactivate specific teachers.
- Production needs a school-owned OAuth client.
- Demo and school OAuth clients must remain separate.

---

# ADR-013: i18n from first component

**Status:** Accepted  
**Phase:** 1.10 / 2.1 / 4.4

## Context

The app requires Turkish and may require English, German, and French for UI/report contexts. Retrofitting i18n after building the UI would be tedious and error-prone.

## Decision

Use i18next and react-i18next from the beginning. API errors use machine codes, and the frontend
localizes fixed display text. Report column and group labels are localized database records because
administrators can customize them without deploying code.

The deterministic column seed catalog uses stable semantic identifiers for readability, but those
identifiers are not frontend i18n keys and are not persisted as display text. Seeding resolves each
identifier to complete Turkish, English, German, and French values stored in
`ColumnDefinition.labels` or `group_labels`. Turkish remains the required runtime fallback. Seed
translations require review by fluent school staff before production use.

## Alternatives considered

- Hardcoded Turkish strings first, translate later.
- Store report-label translations in `packages/i18n` and persist only a translation key.
- Seed Turkish into all locale fields and postpone every report-label translation until launch.
- react-intl.
- Lingui.

## Consequences

- More setup early.
- UI strings stay disciplined.
- Reports and app chrome can localize separately.
- Schools can change report wording without a frontend deploy.
- Seed identifiers can be renamed without changing persisted label semantics.
- Custom columns may temporarily fall back to Turkish until all locale values are supplied.

---

# ADR-014: TanStack Query for server state, Zustand for dirty state

**Status:** Accepted  
**Phase:** 2.5

## Context

A grade grid has confirmed server values and unsaved human edits at the same time. Combining them into one state source causes confusion and save bugs.

## Decision

Use TanStack Query for server-confirmed data and Zustand for the dirty map of unsaved edits.

## Alternatives considered

- All state in React component state.
- All state in TanStack Query cache.
- Redux Toolkit.
- React Context.

## Consequences

- Clear mental model: Query owns what the server said; Zustand owns what the human typed.
- Save/leave guards become straightforward.
- The UI must merge cached and dirty values carefully when rendering cells.

---

# ADR-015: Excel importer uses dry-run before commit

**Status:** Accepted  
**Phase:** 3.8

## Context

School Excel files are inconsistent, and roster import mistakes can affect many students. Admins need to see consequences before data changes.

## Decision

Implement the importer as dry-run first. Dry-run parses the file, reports exact warnings/errors, shows proposed changes, and returns a hash. Commit requires matching the dry-run hash.

## Alternatives considered

- Direct import on upload.
- Manual copy/paste forms only.
- CSV-only import.

## Consequences

- Safer admin workflow.
- More importer code.
- Better error messages and testability.
- A file identity mismatch is detectable.

---

# ADR-016: Lefthook for polyglot git hooks

**Status:** Accepted  
**Phase:** 1.2

## Context

The repo contains TypeScript and Python. Pre-commit checks should not be JS-only or Python-only.

## Decision

Use Lefthook to run Prettier/ESLint for TS and Ruff for Python on staged files.

## Alternatives considered

- Husky + lint-staged.
- Python `pre-commit` framework.
- No hooks, CI only.

## Consequences

- One hook tool covers the repo.
- Bad formatting is caught before commit.
- New clones need hook installation through the package prepare script.

---

# ADR-017: Cloudflare Pages for school production frontends

**Status:** Accepted  
**Phase:** 4.10

## Context

The school production deployment should be stable, cheap, and compatible with static SPA hosting plus `/api` proxying. Vercel Hobby is suitable for personal demo use but not the cleanest school production story.

## Decision

Use Cloudflare Pages for school production frontends. Use Vercel only for the demo if desired.

## Alternatives considered

- Vercel for production.
- Render static sites.
- Self-hosted frontend server.
- One FastAPI server serving static assets.

## Consequences

- Production frontend hosting is free/static and school-appropriate.
- Pages Functions may be needed for `/api/*` proxying.
- Deployment introduces another platform to learn.

---

# ADR-018: ESLint 10 flat-config baseline

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.2

## Context

The original handbook named ESLint 9, while the current Vite scaffold installed ESLint 10. ESLint 10 is the current stable major, removes the legacy eslintrc system, and is supported by the selected TypeScript and React plugins.

## Decision

Use ESLint 10 with per-package flat configs. Require Node `^22.13.0 || >=24.0.0`, matching ESLint 10's supported Node releases while retaining the project's Node 22 baseline.

## Alternatives considered

- Downgrade the Vite-generated apps to ESLint 9.
- Keep different ESLint majors across workspace packages.
- Replace ESLint with Biome.

## Consequences

- The project follows the current ESLint configuration model and release line.
- Each linted workspace package owns its config and lint dependencies.
- Node 23 and Node releases older than 22.13 are unsupported.
- Plugin upgrades must retain explicit ESLint 10 peer support.

---

# ADR-019: Feature-first backend and dedicated infrastructure directory

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.4

## Context

The original backend path, `apps/api/app/api`, used “api” for both the deployable project and its
router layer while “app” was a generic Python package name. As the same Python project will also
contain a Celery worker, CLI, importer, and report renderer, the path obscured its actual boundary.
The repository also kept deployment definitions at the root even though it must support both
managed hosting and a school-controlled virtual machine.

## Decision

Rename the Python project to `apps/backend` and make it an installable uv package under
`apps/backend/src/flrc`. Organize business code feature-first under `flrc.modules`; keep shared
technical infrastructure under `flrc.core` and `flrc.db`, and worker process code under
`flrc.workers`.

Create a top-level `infra/` boundary for orchestration:

- development and production Compose definitions under `infra/compose/`;
- the school-hosted reverse proxy under `infra/caddy/`;
- provider definitions under provider-named directories such as `infra/render/`.

**Later layout amendment (ADR-053 to ADR-055):** the current school deployment template lives in
`infra/school-template/compose.yaml`, and the web image/Caddy configuration in `infra/web/`.
The development Compose file remains in `infra/compose/`; `infra/caddy/` is no longer a current path.

Application Dockerfiles remain beside the applications they build. Managed and school-hosted
deployments use the same images and environment-variable contracts.

## Alternatives considered

- Keep `apps/api/app/api` and add more layer-oriented folders.
- Move the backend to `services/backend`.
- Use a strict `domain/application/infrastructure/presentation` clean-architecture hierarchy.
- Put Dockerfiles and all build contexts under `infra/docker/`.
- Keep production provider files at the repository root.

## Consequences

- Imports identify the product, for example `from flrc.config import settings`.
- A feature's router, schemas, service, and queries can evolve together.
- Shared layer folders must not become dumping grounds for feature-specific code.
- Python packaging requires a build-system declaration and `src`-layout-aware Docker builds.
- Deployment commands use explicit paths such as `infra/compose/compose.dev.yaml`.
- The managed profile remains preferred, while a school-controlled VM is a supported fallback.
- Existing handbook paths, CI working directories, hooks, and deployment definitions must follow
  the new layout.

---

# ADR-020: PostgreSQL 18 baseline

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.4

## Context

The handbook originally pinned PostgreSQL 17. PostgreSQL 18 is now the current supported major,
the official `postgres:18-alpine` image is available, and Neon supports PostgreSQL 18 projects.
The project has no durable development data or applied migrations yet, so changing the baseline
now avoids a later major-version migration.

PostgreSQL 18's official container changed its data-directory layout: its version-specific
`PGDATA` lives below `/var/lib/postgresql`, unlike PostgreSQL 17 and earlier images that commonly
mounted `/var/lib/postgresql/data`.

References: [PostgreSQL version policy](https://www.postgresql.org/support/versioning/),
[official PostgreSQL container](https://hub.docker.com/_/postgres/), and
[Neon PostgreSQL 18 support](https://neon.com/docs/changelog/2026-02-27).

## Decision

Use PostgreSQL 18 for local development, CI, managed deployment, and the school-hosted profile.
Use the `postgres:18-alpine` major tag for development so compatible minor security and bug-fix
releases are received. Mount the named database volume at `/var/lib/postgresql`.

## Alternatives considered

- Keep PostgreSQL 17 until its end-of-life.
- Use PostgreSQL 18 locally but leave managed and CI environments on 17.
- Pin a complete PostgreSQL 18 minor and Alpine patch tag.

## Consequences

- Local, CI, Neon, and self-hosted database majors should remain aligned.
- Existing PostgreSQL 17 Docker volumes cannot be reused directly; disposable development volumes
  are recreated, while any future real upgrade requires `pg_dump`/`pg_restore` or `pg_upgrade`.
- Production changes must continue to use Alembic migrations regardless of database major.
- Minor releases can advance under the `postgres:18-alpine` development tag without silently
  crossing another major version.

---

# ADR-021: Slash-delimited class display names

**Status:** Accepted
**Date:** 2026-08-01
**Phase:** 1.7

## Context

Class names combine a numeric grade level and an alphabetic section. The handbook originally
rendered these labels with a hyphen, such as `5-A`, while the school's preferred convention is a
slash, such as `5/A`.

## Decision

Use `/` as the canonical display delimiter for class names in API responses, user interfaces,
reports, fixtures, and documentation. Import parsing may continue to accept `-` as a legacy or
hostile-input delimiter, but normalized output uses `/`.

## Alternatives considered

- Keep the handbook's original `5-A` format.
- Store a formatted class name in the database.
- Allow each interface to choose its own delimiter.

## Consequences

- Class labels are displayed consistently as `5/A` throughout the product.
- Grade level and section remain separate database fields; this is only a presentation rule.
- Import tests retain coverage for noncanonical hyphenated input.

---

# ADR-022: One public frontend origin with the admin SPA under `/admin`

**Status:** Accepted
**Date:** 2026-08-02
**Phase:** 1.11 / production deployment

## Context

The teacher and admin SPAs were initially exposed on separate production subdomains. Their
host-only `flrc_session` cookies were therefore independent: moving between panels required a
second login, and logging out on one host did not log out the other. Sharing the cookie by setting
`Domain=flrc.suatsulun.com` would solve that symptom by widening the cookie's authority to sibling
and descendant hosts, but it would also widen the session boundary and make cookie deletion and
subdomain trust part of the security contract.

The applications still need separate builds and deployments so an admin-only failure does not
prevent teachers from entering grades.

## Decision

Expose both independently deployed SPAs through one public origin:

```text
https://flrc.suatsulun.com/          teacher SPA
https://flrc.suatsulun.com/admin     admin SPA
https://flrc.suatsulun.com/api/*     FastAPI proxy
```

Attach the public domain to a small gateway deployment. Route `/admin` and `/admin/*` to the admin
deployment, `/api/*` to Render, and all remaining paths to the teacher deployment. Preserve rule
order so API and admin routes are matched before the teacher catch-all.

Keep `flrc_session` host-only: do not set a cookie `Domain`. Configure the admin Vite build and
TanStack Router with `/admin` as their base path. Production uses one exact Google callback URI,
`https://flrc.suatsulun.com/api/auth/callback`.

The teacher SPA owns the only login screen. An unauthenticated request to `/admin` redirects to
`/login`; successful authentication lands on the teacher dashboard, where admins receive the
“Go to admin panel” link. An authenticated non-admin who manually requests `/admin` returns to the
teacher dashboard. The admin SPA has no login route, and OAuth has no admin return target.

Local development may continue to run the teacher and admin Vite servers on ports 5173 and 5174.
The backend retains both configured origins for local Origin checks; in production
`FRONTEND_ORIGIN` and `ADMIN_ORIGIN` are both `https://flrc.suatsulun.com`.

## Alternatives considered

- Keep separate production hosts and require an independent session on each.
- Use `a.flrc.suatsulun.com` and set the session cookie's `Domain` to
  `flrc.suatsulun.com`.
- Merge teacher and admin into one React application.
- Add a dedicated SSO broker that exchanges short-lived one-time codes between hosts.

## Consequences

- Login, refresh, and logout use one host-only browser session across both panels.
- There is one login and error surface to maintain and translate.
- The session cookie is not exposed to every child host under `flrc.suatsulun.com`.
- Teacher and admin remain separate build and deployment units.
- A gateway deployment and ordered path rewrites become production infrastructure.
- The admin app must remain base-path-safe for routes and static assets.
- Both SPAs share an origin, so origin isolation is not a security boundary between them; backend
  role dependencies remain the authorization boundary.
- Preview deployments may still have different hosts and therefore separate preview sessions;
  the shared-session guarantee applies to the public gateway domain.

## Supersedes / Superseded by

This replaces the separate-production-subdomain topology previously described by ADR-002's
deployment consequence. It does not replace the decision to keep two SPAs or ADR-004's
same-origin `/api/*` proxy.

---

# ADR-023: Excel worksheet class names use hyphens at the file boundary

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 3.6-3.8

## Context

The domain displays classes as `5/A`, but XLSX forbids `/` in worksheet titles. A fixture that
sets a sheet title to `5/A` cannot be saved by Excel-compatible libraries.

## Decision

Use `5-A` for class-specific worksheet titles and accept both hyphen and slash forms in cell
values/parser input. Normalize every accepted form back to the canonical `5/A` domain display.

## Consequences

- The hostile fixture is valid XLSX and opens in Excel/LibreOffice.
- The UI, API, and database retain slash-delimited class names.
- Import tests permanently cover this boundary normalization.

---

# ADR-024: Completed job output is a short-lived Postgres blob

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 4.1

## Context

Render container files are ephemeral, while the school workload is small and must survive worker
restart without adding another student-data processor.

## Decision

Store completed PDF/XLSX bytes in deferred `job_runs.output_blob` columns for 24 hours. Polling
never loads the blob; authorized download explicitly loads it. Purging removes only bytes, not job
history. Preserve the API contract so an object-storage adapter can replace this later.

## Consequences

- Outputs survive worker restart and stay under existing database authorization.
- Database storage temporarily grows with generated artifacts and must be purged.
- Move behind approved object storage if measured volume exceeds the small-school assumption.

---

# ADR-025: Class discovery is school-wide while grade writes remain ownership-aware

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 2.1-2.7

## Context

An assignment-only teacher dashboard hid most of the school and exposed invalid seeded role links,
such as a primary French assignment where no French grid exists. Teachers need to review any active
class, while accidental edits outside their responsibility must remain visible, deliberate, and
auditable.

## Decision

Every authenticated teacher receives an active-year class catalog derived from configured column
definitions and real roster membership rather than from their assignments alone. The catalog marks
the teacher's own responsibilities but permits navigation to every valid class and subject grid.

Non-owned cells accept local drafts. Saving those drafts requires an explicit ownership warning. A
teacher receives the existing one-hour audited override grant before the save; an administrator must
explicitly confirm use of administrator authority. The API continues to reject unowned writes that
have neither assignment, active grant, nor administrator authority.

## Consequences

- Teachers can review the complete active school without false empty-class links.
- Assignment ownership remains visible without becoming a read-access boundary.
- Cross-assignment saves are deliberate and remain attributable in the audit trail.
- The class catalog reports only class/subject combinations that have active columns.

---

# ADR-026: Node 26 and explicit pnpm installation

**Status:** Accepted
**Date:** 2026-08-13
**Phase:** Maintenance

## Context

The workstation and CI moved to Node 26. Node no longer bundles Corepack starting with Node 25,
so changing fnm versions can make a previously available pnpm shim disappear even though the
repository and pnpm store remain intact.

## Decision

Standardize local development and CI on Node 26, record the exact runtime in `.node-version`, and
install pnpm 11 explicitly into the active Node environment. Keep the pnpm major and minimum
version in `package.json` so CI and local tooling use the same supported line.

The legacy static Vercel gateway keeps an isolated Node 24 manifest because Vercel Builds do not
yet offer Node 26. It contains no application code or dependencies; the teacher/admin builds and
all local/CI application checks continue to use the repository's Node 26 baseline.
Because Vercel treats that directory as a standalone project root, its manifest must also repeat
the root `packageManager` pin; the two values move together during pnpm upgrades.

Upgrade dependencies to their latest mutually compatible stable versions. Keep TypeScript on 6.0
until the stable `typescript-eslint` release declares TypeScript 7 support; do not suppress the peer
incompatibility. Migrate TanStack Table to the native v9 API instead of its deprecated legacy hook.

## Consequences

- Switching fnm versions may require installing pnpm for that Node installation.
- CI and local development exercise the same Node major.
- The static Vercel gateway remains deployable until Vercel Builds support Node 26.
- The table no longer triggers the React Compiler incompatibility warning from TanStack Table v8.
- TypeScript 7 remains a tracked follow-up rather than an unsupported forced upgrade.

## Supersedes / Superseded by

Supersedes ADR-018 only for its Node-version baseline; the ESLint 10 flat-config decision remains.

---

# ADR-027: Grade responsibility warns but does not block collaboration

**Status:** Accepted
**Date:** 2026-08-17
**Phase:** 2.4-2.7 maintenance

## Context

The role-level ownership check prevented teachers from saving notes owned by another teaching role,
and an unassigned role could make those notes effectively admin-only. The school needs any teacher
to be able to help with any note while making out-of-responsibility edits deliberate and visible.

## Decision

Keep ownership at the column's assigned role: main teachers are warned for skills-owned notes and
skills teachers are warned for main-owned notes. Ownership controls the warning, not ultimate write
authority. Every authenticated teacher may confirm an out-of-assignment save, including when the
role currently has no assigned owner.

The save request carries an explicit `confirm_outside_assignment` flag. The API records a short-lived
override grant for each confirmed foreign role and links the resulting audit entries to it. Active
grants do not hide future warnings in the grid, so each save outside the teacher's responsibility is
deliberate. Optimistic concurrency, semester locks, validation, undo, and actor attribution remain
unchanged.

## Consequences

- Teachers can complete any report-card field without an administrator acting as a data-entry proxy.
- Assigned and foreign fields remain visually distinct, and foreign saves require confirmation.
- Missing teaching assignments no longer block urgent grade entry, but remain visible admin work.
- Direct API writes without ownership, an active grant, or explicit confirmation are rejected.

## Supersedes / Superseded by

Supersedes ADR-025 only where it treated the grant as a separate prerequisite and rejected saves for
unassigned roles.

---

# ADR-028: Four school-wide report sets use one HTML-to-PDF pass each

**Status:** Accepted
**Date:** 2026-08-17
**Phase:** 4.2-4.4 maintenance

## Context

Rendering one PDF per student through WeasyPrint, committing progress after each card, zipping the
files, waking a Celery worker, and polling the job made school-wide reports disproportionately slow.
The required outputs are four PDFs: elementary English, middle-school English, German, and French.

## Decision

Build each report set in a bounded number of database queries, render all matching classes through
Jinja2 as one HTML document, and convert that complete document to one PDF in a single WeasyPrint
pass. Return the PDF from an authenticated, non-cacheable endpoint. Elementary English uses grades
1-4, middle-school English uses grades 5-8, and German/French include every applicable class and
student selected into that language.

Remove the per-student PDF worker loop, ZIP assembly, and report-job polling from the normal report
flow. Keep WeasyPrint only as the final HTML-to-PDF stage, invoked once per complete set. Keep Celery
and durable `job_runs` for whole-year XLSX exports, which remain genuinely asynchronous work.

## Consequences

- Four actions cover the full school instead of requiring class-by-class selection.
- Hundreds of renderer startups become one renderer pass per requested PDF set.
- Report output is a real PDF but is no longer stored as a 24-hour ZIP bundle.
- The school's printer must be included in print-layout checks.

## Supersedes / Superseded by

Supersedes ADR-010's per-student batch shape and ADR-024's report ZIP storage. Jinja2 and WeasyPrint
remain the rendering layers; ADR-024 still applies to XLSX exports.

---

# ADR-029: One shared design system in packages/ui, driven by semantic tokens

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

Both SPAs had duplicated their entire `index.css` (140 near-identical lines each), and the admin app
carried a block of `@layer components` rules that restyled bare `<form>`, `<table>`, and `<select>`
elements by descendant selector under `.admin-page`. Screens were assembled from one-off Tailwind
utility strings, so the same table appeared with four different paddings, and raw palette classes
(`bg-white`, `bg-slate-50`, `text-blue-700`) were sprinkled through the routes. `packages/ui`
existed but exported one placeholder component, so it was not actually the source of shared UI.

## Decision

Design tokens live once, in `packages/ui/src/styles/theme.css`, and each app's `index.css` is a
five-line import of it. Screens compose named primitives from `packages/ui`
(`AppShell`, `Card`, `Table`, `PageHeader`, `Badge`, `Stat`, `Field`, `NativeSelect`, `Segmented`,
`EmptyState`, `Skeleton`, `Kbd`) and consume semantic tokens (`bg-card`, `text-muted-foreground`,
`border-border`, `bg-warning-surface`) rather than raw palette values. The element-restyling
`.admin-page` CSS block is deleted.

The palette is a calm, cool blue: one accent (`--primary`, oklch(0.5 0.15 256)) dark enough to carry
white text at 4.5:1, muted status colours beside it, and near-white blue-cast surfaces so white
cards read as raised.

## Alternatives considered

- Keep per-app CSS and just recolour it: the duplication is what let the two apps drift in the
  first place, and recolouring does not fix inconsistent spacing.
- Adopt a third-party component library: the handbook already chose owned shadcn/ui source in
  `packages/ui`; replacing it would discard that decision for no new capability.
- Tokens as a TS object consumed in JS: Tailwind v4 reads `@theme`, so CSS is the native home and
  needs no build step.

## Consequences

- A colour or radius change lands in one file and both apps move together.
- New screens are assembled, not hand-styled, so they are consistent by default.
- `packages/ui` is now a real dependency of both apps, so a change there can break both; the
  monorepo `typecheck`/`lint` tasks cover this.
- `next-themes` was dropped (see ADR-030), removing one dependency.

## Supersedes / Superseded by

None.

---

# ADR-030: Light and dark themes follow the OS, with an explicit override

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

A `.dark` block existed in both apps but held unmodified neutral-grey shadcn defaults, and nothing
ever added the `dark` class, so it was dead code that would have looked broken if enabled. Teachers
enter grades outside school hours and asked for a dark option.

## Decision

`resolveTheme` follows `prefers-color-scheme` unless the person pins a side; the resolved value is
stamped on `<html>` as `light`/`dark`. The control is a three-way segmented toggle
(light · system · dark) pinned to the bottom-left of the sidebar in both apps. The preference is
stored in `localStorage` under `flrc-theme`.

The pre-paint stamp is a **static file**, `public/theme-boot.js`, loaded blocking from `<head>`, not
an inline `<script>`: the apps ship `script-src 'self'` in `public/_headers`, which forbids inline
script. An inline snippet would have needed a CSP hash recomputed on every edit.

## Alternatives considered

- `next-themes`: it was already a `packages/ui` dependency, but it needs a provider and its own
  anti-flash script, for behaviour that is ~40 lines here. Dropped the dependency instead.
- Inline bootstrap plus a CSP hash: brittle, since every edit to the snippet silently breaks the
  page until `_headers` is updated.
- Media-query-only dark mode with no override: it cannot honour an explicit choice, which was the
  ask.

## Consequences

- No flash of the wrong theme, and no CSP exception.
- `public/theme-boot.js` duplicates the logic of `applyTheme`; both carry comments pointing at each
  other, and the storage key is the contract between them.
- Every screen now has to be checked in both themes.

## Supersedes / Superseded by

None.

---

# ADR-031: Keyboard-first grade grid

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

Grade entry is the one screen teachers spend hours in. Navigation only handled `Enter` and
`ArrowUp`/`ArrowDown` within a column, there was no way to move sideways without the mouse, saving
required finding the button, and the unsaved count was only legible on the button label.

## Decision

Full spreadsheet movement: all four arrows, `Enter`/`Shift+Enter` for next/previous row, and
`⌘S`/`Ctrl+S` to save from anywhere, including mid-cell. Cells register in a `row:column` map so
movement is a lookup rather than a DOM query. The header and student column freeze; a persistent bar
shows the unsaved count, the keyboard hints, and Save.

Arrow-left/right serve two jobs, and the text selection decides which: a whole value selected
(true right after focus) or a caret at the very edge moves the cell; otherwise the caret moves
inside the text.
This needs no mode and no modifier.

Three-point scale cells take `1`/`2`/`3` directly, `0`/`Backspace`/`Delete` to clear, `Space` to
cycle, and render the numeral the report card prints, tinted by level, so what a teacher types is
what a parent reads.

None of this touches the dirty store, the optimistic-concurrency check, the conflict dialog, or the
ownership guard. Bulk fill-down and paste-a-column were considered and rejected.

## Alternatives considered

- Restyle only: it leaves the slowest part of the product slow.
- Add fill-down and column paste: a mis-aimed bulk write is exactly the silent mass overwrite the
  audit rules exist to prevent, and the value is far lower than per-cell speed.
- A canvas or virtualised grid: a real rewrite, and rosters are ~30 rows.

## Consequences

- Entering a column of grades is arrow keys and digits, no mouse.
- The ownership guard still interrupts `⌘S`, which is deliberate and covered by a test.
- The confirm buttons in the ownership and conflict dialogs now carry `data-testid`s, so the
  two-writer collision E2E test no longer breaks when that copy is reworded.

## Supersedes / Superseded by

Extends ADR-027; the warn-not-block behaviour is unchanged.

---

# ADR-032: One report-card template, with page geometry as data

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

`bilingual.html`, `middle.html`, and `progress.html` were three ~70-line templates that had each
drifted: only one showed an average, only two rendered group headings, and each repeated its own
copy of the same CSS. Visually, all three were a grey boxed grid with every cell outlined, closer
to a spreadsheet printout than a school record. Nothing on the page identified the school.

## Decision

One `templates/report.html`. What differs between the four sets is page geometry, which lives in
`LAYOUTS` in `render.py` as a `PageLayout` (page size, margin, type size, block rhythm, signature
geometry). A change to the school's report card can no longer land on some sets and miss others.

The design is an official school record: a serif masthead with the school's logo at top-left,
hairline rules instead of boxed cells, group headings as small-caps rules, values right-aligned in
tabular figures, comments in a full-width block, a signature line, and a running footer carrying the
student's name via `string-set`. Blue appears only as an accent.

Two supporting decisions:

- Grouping happens in Python (`group_fields`), not in the template, because Jinja's `groupby` sorts
  its input and would silently reorder the columns the school arranged.
- The logo is embedded as a data URI, so the same markup works for WeasyPrint and for a standalone
  HTML preview.

## Alternatives considered

- Keep three templates and restyle each: this guarantees they drift again.
- A Jinja base template with `{% block %}` overrides: blocks inside the per-card `{% for %}` loop
  need `scoped` and read worse than passing geometry as data.
- A modern branded card with a filled header band: striking on screen, but it uses far more toner
  and reads less like an official record.
- Two-column compact layout: it saves paper but is tight for long comments.

## Consequences

- Each student still fits one page in all three geometries, which is asserted by rendering the
  synthetic sets and counting pages.
- A5 elementary is the tight one: its block rhythm and signature are deliberately smaller, and an
  unusually long column set will still flow to a second page.
- `templates/` is in `.prettierignore` because Prettier parses Jinja as plain HTML and reflows
  `{# … #}` and `{% … %}` in ways that damage the template.

## Supersedes / Superseded by

Supersedes the three-template layout from ADR-028. ADR-028's one-renderer-pass-per-set decision is
unchanged.

---

# ADR-033: The school's logo and name are configuration, not repository content

**Status:** Superseded by ADR-034

**Date:** 2026-08-17
**Phase:** 4.x

## Context

The school's logo has to appear top-left on every screen and on every printed report card, but this
repository is not where the school's branding belongs; it arrives later in the school's own private
repository.

## Decision

Four swap points, none of which require a code change:

| What        | Where                                                                      | How                                  |
| ----------- | -------------------------------------------------------------------------- | ------------------------------------ |
| Web logo    | `apps/teacher/public/school-logo.svg`, `apps/admin/public/school-logo.svg` | replace the file                     |
| Web name    | `VITE_SCHOOL_NAME`                                                         | deploy environment                   |
| Report logo | `modules/reports/assets/school-logo.svg`, or `SCHOOL_LOGO_PATH`            | replace the file, or point elsewhere |
| Report name | `SCHOOL_NAME`                                                              | deploy environment                   |

Each app resolves its logo through `import.meta.env.BASE_URL` so the URL stays correct under the
admin app's `/admin/` base and resolves from deep client routes. `SchoolLogo` falls back to a neutral
monogram if the file is missing or fails to load, so a checkout without branding never shows a broken
image. The committed files are placeholders carrying a comment that says so.

## Alternatives considered

- Import the logo as a bundled module: a build-time dependency on a file the public repo must not
  contain.
- Serve the logo from an API endpoint: it adds a request and a backend route for a static asset.
- Hardcode and let the private repo patch the component: a merge conflict on every UI change.

## Consequences

- The private repository overlays files and sets two environment variables; it never forks a
  component.
- The placeholder is visible in the public demo, which is intended.
- `VITE_SCHOOL_NAME` is baked at build time, so changing it needs a rebuild.

## Supersedes / Superseded by

Superseded by ADR-034, which keeps this decision's substance but collapses the four
swap points into one root folder.

---

# ADR-034: A single root `branding/` folder, applied by `pnpm brand`

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

ADR-033 made branding configuration rather than code, but it left four separate
swap points across three packages: two `public/school-logo.svg` files, a
`VITE_SCHOOL_NAME` build variable, a logo inside the reports package, and a
`SCHOOL_NAME` backend variable. Rebranding meant remembering all four, and
forgetting one produced a half-branded product, the worst possible state in which
to show a prospective school. Nothing made a partial rebrand visible.

## Decision

One folder at the repository root, `branding/`, holds `brand.json` (name, short
name, accent colour) and `logo.svg`, plus an optional `favicon.svg`. It is also a
workspace package, `@flrc/branding`, so the web apps import the name and the logo
directly: the bundler fingerprints the logo and resolves it correctly under the
admin app's `/admin/` base, and there is no copy to drift.

`pnpm brand` (`scripts/branding.mjs`) feeds the three kinds of consumer that
cannot import a module: `index.html`, the CSS palette, and the Python backend
(whose Docker image only copies `src/`). Its output is committed so a fresh clone
works untouched, `predev`/`prebuild` run it automatically, and `pnpm brand:check`
fails CI when a derived file has drifted.

The palette is derived from the **hue** of `accentColor` only. `theme.css` reads
`--brand-hue` and keeps the lightness and chroma that were checked for contrast,
so any school colour still yields white-on-primary above 4.5:1. Status colours
(success, warning, destructive) deliberately do not rotate: they carry meaning,
not brand.

Environment variables survive as per-deployment overrides for the multi-school
case; for a single school they stay unset.

## Alternatives considered

- Keep the four swap points and document them: documentation does not stop a
  partial rebrand reaching production.
- Have the backend read the repo-root folder at runtime: the Docker build context
  is `apps/backend`, so the root folder is not in the image. Changing the build
  context to fix a branding concern is the wrong trade.
- Derive the palette from the school's exact colour: this cannot guarantee
  readable button labels for a pale or very dark brand colour.
- Generate a TypeScript module for the name: unnecessary once `branding/` is a
  workspace package that can be imported directly.

## Consequences

- A full rebrand is: replace `logo.svg`, edit `brand.json`, run `pnpm brand`.
- `pnpm brand` prints the derived hue, the resulting primary, and its contrast
  ratio, so the result is inspectable without opening the app.
- A school's exact corporate colour is matched by hue, not reproduced exactly.
  That is a deliberate accessibility trade, documented in `branding/README.md`.
- Derived files are committed, so a rebrand is a reviewable diff, but they must
  never be hand-edited.
- The front-end name and logo are compiled in, so several schools need several
  builds.

## Supersedes / Superseded by

Supersedes ADR-033. Extends ADR-029 (the token system) and ADR-032 (the report
template), both of which now read their brand values from here.

---

# ADR-035: School numbers belong to yearly enrollments

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 3.x

## Context

`students.school_number` was globally unique. That modeled a reusable administrative number as if
it were a permanent identity: student 200 in 2026-2027 prevented a different student from receiving
200 in 2030-2031, and changing a continuing student's number would rewrite what archive screens
showed for earlier years.

## Decision

`students.id` is the permanent person identity. `enrollments.school_number` is the number for one
academic year, unique on `(year_id, school_number)`. A setup-year enrollment may temporarily have no
number; activation fails until every enrollment has one. All grids, reports, exports, searches, and
archive views resolve the number through the enrollment for the displayed year.

## Alternatives considered

- Keep a non-unique last-known number on `students`: easy to misuse and wrong for archives.
- Create a separate number-history table: it duplicates the year link already owned by enrollment.
- Encode the year into the number: it changes the school's actual identifier and its printed form.

## Consequences

- A number can be reused safely in different years without an archive conflict.
- One student can keep the same identity while receiving a different number each year.
- Import matches a promoted, numberless enrollment by normalized name before creating a new person.
- Downgrading to the old schema cannot represent reused numbers and therefore restores deterministic
  unique ids rather than pretending the old model can preserve the new meaning.

---

# ADR-036: Automatic rollover after a fully closed year

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 3.x

**Superseded in part by:** ADR-041 (fresh sequential rollover numbers)

## Context

Starting a school year by recreating dozens of class, column, teacher, and student connections is
slow and error-prone. Grades and school numbers, however, must never be copied forward.

## Decision

Archiving a standard `YYYY-YYYY` year after both semesters are locked creates the next consecutive
setup year in the same transaction. It copies class structure, teacher assignments, semester column
templates, and second-language choices. Students in grades 1-7 are enrolled in the next grade with
the same stable student id; grade 8 students graduate and are not enrolled. Grade values, audit
rows, save batches, and old school numbers are not copied. ADR-041 replaced the original empty-number
preparation step with fresh sequential numbers in the target year.

Activation is explicit and requires every promoted enrollment to have a number. Rollover is
idempotent when the target year already exists.

## Consequences

- The next year is available immediately after closing the current one.
- Admins prepare only the information that truly changes: numbers, new arrivals, departures, and
  exceptional class placement.
- Longitudinal history remains connected without mutating an archived year.

---

# ADR-037: Table-first workspaces and field-safe assignment

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 2.x-3.x

**Superseded in part by:** ADR-041 (English school-stage ownership)

## Context

The grade grid is the daily product, but both apps opened on navigation-heavy dashboards. Admin work
split one class across roster, columns, assignments, students, and lifecycle pages. This imposed too
many concepts and clicks on occasional computer users.

## Decision

Both apps open on a table. The teacher grid keeps year/semester, grade, subject, and browser-like
class tabs visible above the cells. The admin class table combines roster numbers, second languages,
column creation/reordering/ownership, class-level teacher assignment, and an add-student row. A
student can be dragged between same-grade class tabs; their stable identity keeps all grade and note
records connected.

Teachers have one persisted `teaching_field`: English, German, or French. English teachers are
eligible for Main and Skills; German and French teachers are eligible only for the matching role.
Both API assignment paths enforce this rule. The assignment page is a teacher-centered drag board;
the same assignments remain editable inline on each class table.

The UI uses native drag events and existing React primitives. No grid or drag dependency is added.

## Consequences

- The core table is visible without navigating through class cards.
- Most yearly administration happens in one mental model and one screen.
- Same-grade moves preserve grades and notes because values belong to stable students and semester
  column definitions, not to a transient class row.
- Assignment mistakes are rejected server-side even if a client bypasses UI filtering.

---

# ADR-038: Fail-closed school authentication and managed-origin isolation

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 4.8

## Context

Per-endpoint dependencies, a domain hint, and frontend guards are individually insufficient for
children's school data. A future route can omit a dependency, Google Workspace email addresses can
be reassigned, a managed API origin can bypass gateway controls, and a deployment can accidentally
start with HTTP or placeholder secrets.

## Decision

Include every data router beneath one central `current_user` dependency while retaining the
narrower endpoint role checks. In school mode:

- accept only verified Google identities whose exact `hd` and email domain match;
- require an active pre-created admin allowlist row;
- bind that row on first login to Google's stable `sub` and reject later mismatches;
- use an eight-hour absolute Redis session and a host-only `__Host-` cookie;
- require exact Origin on unsafe requests, explicit trusted hosts, HTTPS, body limits, no-store
  responses, and disabled OpenAPI/docs;
- require a secret header injected by the Cloudflare gateway at every non-health API path;
- refuse application startup when any production invariant is missing or weakened.

The health response and OAuth handshake remain the only public backend surface. Static browser
assets remain public by necessity and contain no school data or credentials.

## Consequences

- A forgotten local dependency on a new data route still fails closed.
- A reassigned email cannot inherit the previous Google identity's access without an explicit
  deactivate/reset/reactivate admin action.
- Direct requests to the managed API origin cannot reach OAuth or data routes.
- Rotating the gateway secret requires coordinated Cloudflare and API deployment.
- There is still no truthful claim of absolute security; provider configuration, MFA, monitoring,
  updates, and incident response remain launch requirements.

---

# ADR-039: One-scroll, always-visible table workspaces

**Status:** Accepted

**Date:** 2026-08-21
**Phase:** 2.x-3.x

## Context

The table workspaces had an application scroll, a nested vertical table scroll, and horizontal
table/tab scrolls. Teachers could miss fields outside the visible strip, and dragging a student to
a class tab above the viewport stopped at the table boundary.

## Decision

The document is the only vertical scrolling surface for primary admin and teacher tables. Table
wrappers use visible overflow; fixed-layout columns divide all available width; headers wrap; and
inputs/selects shrink to their cells. Context and class tabs wrap instead of scrolling sideways.
The app shell's side and top panels are independently minimizable, but expanded chrome is still a
supported fit target. Student dragging runs a request-animation-frame loop that scrolls the document
when the pointer enters the top or bottom 96 pixels of the viewport.

## Consequences

- Every column remains visible without discovering a horizontal scrollbar.
- Rows move with the normal page, so trackpads and mouse wheels have one predictable target.
- Very wide grids become denser, and header labels may wrap onto multiple lines.
- Phone users retain the one-student stepper when a dense table would be too small for touch.

---

# ADR-040: UI palette decoupled from the school accent colour

**Status:** Accepted

**Date:** 2026-08-21
**Phase:** 4.x

## Context

The whole UI palette derived its hue from the school's accent colour: `pnpm brand` converted
`branding/brand.json` (`#2f7168`) to `--brand-hue: 183.3` and every brand-family token rotated with
it, over green-tinted slate backgrounds. With a teal school colour, the apps read as mossy green,
and any future school colour would recolour every surface of the product, for better or worse.

## Decision

The design tokens in `packages/ui/src/styles/theme.css` no longer consume `--brand-hue`. The UI
uses two fixed, contrast-checked palettes chosen from a twenty-option ballot: light "Parchment"
(warm paper ground, slate-brown ink, navy action colour) and dark "Graphite" (lifted neutral
charcoal, light-key buttons, steel-blue focus ring as the only hue). The school's colour remains
where branding belongs: the logo, the printed report cards, and the `theme-color` meta that
`pnpm brand` still writes. `branding/generated/brand.css` keeps publishing `--brand-hue` so the
branding pipeline is unchanged, even though the UI ignores it.

## Alternatives considered

- Keep the hue rotation but tune lightness/chroma: this still recolours the whole UI per school and
  cannot make a teal brand look neutral.
- Rotate only action colours (buttons, links) with the brand: rejected for now; it can be
  revisited by pointing `--primary` back at a brand-derived value.

## Consequences

- Dark mode is neutral charcoal instead of green slate; light mode is warm paper with navy ink.
- Rebranding no longer changes the app's surfaces, only the logo, report cards, and browser chrome.
- The comment in generated `brand.css` claiming theme.css reads its hue is stale until
  `scripts/branding.mjs` is next touched.

---

# ADR-041: Explicit teaching stages and activation-ready rollover

**Status:** Accepted

**Date:** 2026-08-21
**Phase:** 3.x

## Context

`teaching_field=english` could not distinguish the twelve primary teachers from the twelve
middle-school teachers. The assignment UI therefore could not filter unassigned English teachers
reliably, and the API could prevent a German/Main mismatch but not a primary/middle mismatch.
Separately, automatic rollover created valid promoted enrollments with blank school numbers, so a
generated next year immediately failed its own activation guard.

## Decision

English users have a required `teaching_stage` of `primary` (grades 1-4) or `middle` (grades 5-8);
German and French users have no stage. Both individual and bulk assignment writes enforce the
field/stage combination. The assignment board filters All, Primary, Middle, German, and French.

Rollover never copies an archived school number. It assigns promoted students new sequential
numbers beginning at 1 in deterministic class/name order. A migration fills only missing numbers in
already-created setup years, preserving any values an administrator entered. Activation keeps its
missing-number guard. The same migration repairs duplicate open-semester states and adds a partial
unique index so at most one semester per year can be open.

## Consequences

- The generated 2027-2028 setup year is activation-ready without hundreds of manual edits.
- Reusing a number in a later year remains safe because uniqueness is scoped to the year.
- Primary/middle assignment mistakes fail at the API even if the UI filter is bypassed.
- Admin user creation and editing now include an English school-level choice.
- Translation integrity is checked automatically across all four locale bundles and literal UI keys.

---

# ADR-042: Pending work is visible and class tabs are warmed

**Status:** Accepted

**Date:** 2026-08-21
**Phase:** 2.x-4.x

## Context

Year activation, audit export, workbook import, PDF rendering, and cold class-table requests can
take long enough to look like a missed click. Pending states were inconsistent, the admin toast
renderer was easy to miss, and native browser confirmation prompts did not match the application.

## Decision

The shared button owns one `pending` contract: preserve its layout, disable repeated activation,
overlay a spinner, expose `aria-busy`, and keep an accessible pending label. Both app shells show a
first-query activity indicator; important page entry states use stable skeletons. Mutations always
surface errors globally, while meaningful saves, transitions, exports, and background job state
changes use localized success/loading/error toasts.

Typed confirmations use the shared site dialog. TanStack Router's resolver dialog handles internal
navigation away from dirty grades; the browser's mandatory `beforeunload` warning remains only for
closing or leaving the document itself.

Direct PDF actions open a user-initiated generating tab, fetch authenticated PDF bytes, replace the
tab with a blob URL when ready, and restore the initiating button. Admin and teacher class views
prefetch only the sibling tabs in the selected grade, after a short delay and on hover/focus, with a
30-second freshness window. Background warming is sequential per browser; hover and keyboard focus
still prioritize the class a user is about to open.

## Consequences

- Slow actions cannot be submitted twice and never look inert.
- Success, failure, and background completion are visible without browser alert boxes.
- Switching among A-G class tabs normally reads from the warm query cache.
- One selected grade can make several small speculative roster/grid reads; the bound prevents a
  whole-school prefetch storm, and sequential warming limits roughly twenty concurrent users to
  roughly twenty speculative reads at once.

---

# ADR-043: Plan-aware GitHub security gates

**Status:** Accepted

**Date:** 2026-08-24
**Phase:** 4.10 / operations

## Context

CodeQL SARIF upload and dependency review require GitHub Advanced Security for this private
repository. Running those actions without the entitlement made every push and pull request red even
though the actions could not perform a scan. The repository's independent JavaScript and Python
locked-dependency audit remained available and green.

## Decision

The locked-dependency audit remains unconditional. CodeQL and dependency review run for public
repositories or when the repository variable `GHAS_ENABLED` is exactly `true`. Operators set that
variable only after enabling GitHub Advanced Security. Dependabot ignores TypeScript 7 until both
typescript-eslint and the OpenAPI generator support it, and it does not change the Python 3.13 base
image to 3.14 without an explicit runtime migration.

## Alternatives considered

- Leave the unsupported actions red: rejected because failure no longer meant a code or dependency
  problem.
- Disable all security automation: rejected because the lockfile audits and Dependabot work on the
  current plan.
- Upload local CodeQL output without GitHub Advanced Security: rejected because private-repository
  CodeQL use is entitlement-bound, not only an upload configuration problem.

## Consequences

- Security workflow results distinguish actionable findings from unavailable paid capabilities.
- The repository retains always-on production dependency audits on its current plan.
- Enabling GitHub Advanced Security requires one explicit repository variable before the additional
  gates become required.

---

# ADR-044: Teacher assignments are object-level read and write boundaries

**Status:** Accepted

**Date:** 2026-09-04
**Phase:** Security hardening

## Context

The class catalog and grid allowed every authenticated teacher to enumerate every class, student,
school number, subject, and grade. The same broad discovery model let a teacher create an override
grant for a class or subject with which they had no relationship. Auditability recorded misuse but
did not prevent the disclosure or unauthorized grade change.

## Decision

A teacher must hold a teaching assignment for the exact class and subject before the catalog, grid,
save, grant, or undo paths proceed. English `main` and `skills` assignments share the English subject
boundary, so the existing warning and one-hour cross-role collaboration still works within that
class. German and French remain separate subject boundaries. Administrators retain full read/write
authority; coordinators retain school-wide read-only oversight.

## Consequences

- Authenticated teachers cannot enumerate or alter another class, language subject, or academic
  year merely by changing a path/query id.
- Existing same-class English collaboration remains available and audited.
- Missing assignments must be repaired by an administrator instead of being bypassed through an
  override grant.

## Supersedes / Superseded by

Supersedes ADR-025's school-wide teacher discovery decision and narrows ADR-027's collaboration
decision to an already-assigned class and subject.

---

# ADR-045: Contained table viewports preserve readable columns

**Status:** Accepted  
**Date:** 2026-09-04  
**Phase:** Product-wide UX

## Context

ADR-039 made every table fit the page to avoid hidden columns and nested scrolling. On dense class,
user, audit, archive, and grade-entry tables, fixed-layout percentages instead compressed headers,
form controls, and text below comfortable reading and interaction sizes. More columns made the
problem worse, while wrapping made individual rows tall and difficult to scan.

## Decision

Tables use a bounded, keyboard-focusable scroll viewport. Columns receive content-appropriate
widths, headers stay pinned during vertical scrolling, and the identity column stays pinned during
horizontal scrolling on every table wide enough to scroll. The scrollbar remains visibly styled in
both themes. Compact tables can still fill their card without needing to scroll. Phones retain the
one-student grade stepper rather than presenting a miniature grid.

Four rules make that work in practice:

1. **A trailing slack column absorbs leftover width.** `table-layout: fixed` distributes surplus
   width proportionally across the declared columns, which inflated the identity column on wide
   viewports. CSS sticky cannot move an element outside its containing block, so an inflated
   identity column silently unstuck, and the roster's fixed `left` offsets drifted out of step with
   the columns they follow. An unlabelled final column takes the surplus instead, so every declared
   width is exact at every viewport.
2. **Sentence-length labels are clamped, not laid out.** Assessment criteria are whole sentences.
   They are rendered in sentence case, clamped to three lines in the grade grid and one line
   elsewhere, and carry the full wording in a `title`. The one-student stepper remains the place to
   read a criterion in full.
3. **Empty-state text is anchored to the scroll viewport**, not centred across the table, so it
   stays visible on a table that is scrolled horizontally.
4. **Column header text has a 12px floor**, asserted by the e2e table contract.

## Consequences

- Every row and column remains reachable without creating page-level horizontal overflow, verified
  across nine table screens at desktop, laptop, and tablet widths in both themes.
- Labels, controls, and numeric values retain readable sizes at all three widths.
- Dense tables introduce a deliberate inner scroll region; captions, focus rings, and visible
  scrollbars make that interaction discoverable and accessible.
- Drag auto-scroll supports the class table viewport as well as the document.
- `e2e/helpers/table.ts` owns the contract (contained overflow, a caption, a pinned first column,
  a reachable last labelled column, and readable header sizes), and the three specs that assert
  table layout share it.

## Supersedes / Superseded by

Supersedes ADR-039.

---

# ADR-046: Parallel class rendering with ordered PDF assembly

**Status:** Accepted

**Date:** 2026-09-04
**Phase:** 4.2-4.4 maintenance

## Context

Profiling a synthetic 30-student middle-school class showed that Jinja rendering took about four
milliseconds while WeasyPrint layout and painting took 2.71 seconds. Four 30-student classes took
13.75 seconds in one document. Table layout, page layout, and PDF painting dominated the profile;
template compilation, branding assets, and DTO assembly did not. Reused font and image caches did
not reliably improve the workload, and threads made it slower.

Every class is already an independent print boundary. A middle-school class starts its own A5
guillotine stack, and elementary/second-language cards are independent duplex sheets. This permits
parallel work without changing a card's HTML or CSS.

## Decision

Keep the synchronous authenticated PDF endpoint from ADR-028. For a report set of at least twelve
already-imposed sheets, split that ordered sheet list into balanced contiguous chunks, render the
chunks in a lazy warm process pool bounded to four CPU-visible workers, then use pypdf to assemble
the results in their original order. Smaller reports stay on the existing direct WeasyPrint path.
Preserve the first document's PDF metadata during assembly.

pypdf becomes a runtime dependency. Celery remains reserved for durable year exports; report cards
are not moved back into job payloads or temporary artifact storage.

## Alternatives considered

- Reuse a WeasyPrint font configuration or image cache: measured as neutral or slower here.
- Render classes in threads: slower because the dominant layout work did not scale across threads.
- Change the score tables to fixed layout: potentially faster, but it changes the deliberate
  content-sized columns and therefore violates print-layout compatibility.
- Cache completed class PDFs: rejected because invalidation after grade, roster, column, locale, or
  branding changes would enlarge the stale-report risk.

## Consequences

- Multi-class PDF latency falls substantially on hosts with more than one available CPU.
- Page content, size, order, and per-class guillotine imposition remain unchanged and are regression
  tested against the original single-document renderer.
- Each API process may keep up to four renderer child processes warm after its first multi-class
  request, trading memory for lower subsequent latency.

## Supersedes / Superseded by

Extends ADR-028; the endpoint and the four school-wide report-set contract are unchanged.

---

# ADR-047: Paged import review with validated class moves

**Status:** Accepted

**Date:** 2026-09-08
**Phase:** 3.8

## Context

The import committed the full workbook but displayed only its first 100 students. Administrators
could not inspect later classes or correct class placement before finalizing the import.

## Decision

The stateless dry-run endpoint accepts bounded offset pages and searches/filters the full parsed
roster before slicing. It returns full-workbook counts, matching row counts, a next offset, and class
counts. Scrolling loads the next page; filters never narrow the committed import.

Admins can stage class moves using drag-and-drop or a row's class selector. Each move must reference
a school number in the original file and a class in that file or the selected year. Both endpoints
validate the same override list; names, identities, and languages remain owned by the parser. A
review digest binds the original file hash, year, and sorted moves. Commit rejects stale or missing
review digests when moves exist. Existing file-only clients remain compatible.

TanStack Query owns reviewed pages. A per-review Zustand store owns unsaved moves and undo history.
Changing the file/year discards that draft. Commit success replaces the editor with a result and
invalidates the affected server caches. Errors retain the draft for review and retry.

## Consequences

- All students can be reviewed without rendering the entire school at once.
- Class changes remain preview-only until one transactional commit.
- Each page/filter request resends and reparses the bounded workbook; no server-side upload cache,
  new processor, persistent draft, or schema migration is introduced.

---

# ADR-048: Editable roster previews and class-table removal

**Status:** Accepted

**Date:** 2026-09-08
**Phase:** 2.1, 3.4, 3.8

## Context

Administrators need to add or exclude students and clear German/French selections before importing.
The left grade selector changed only destination buttons, leaving the roster unfiltered. Class
tables exposed student creation and column arrows but lacked removal and direct column placement.

## Decision

Extend ADR-047 with a typed `roster_edits` object containing additions, excluded school numbers, and
language changes. Both preview and commit validate these operations against the reparsed workbook
and the selected year's classes. The review digest binds every operation. Additions cannot overwrite
a differently named enrolled student. Exclusions skip import rows and never delete saved enrollments.
All operations share per-review Zustand undo history; TanStack Query retains reviewed server data.
The left grade selector filters the roster and resets an individual class selection.

A Remove tab in class tables lists both students and assessment columns for the current context.
Removing a student deletes only the selected year's enrollment and language choice after a UI
confirmation, retaining the stable student identity, other enrollments, grade values, and grade audit
entries. The API is admin-only, locks the year, rejects archived years and stale class membership,
and logs only actor/student/class/year IDs. Retained grades are no longer part of that year's active
roster; removal is not erasure of the student record.

Assessment columns can be removed for English, German, and French using the existing
delete-or-disable behavior. Columns with grades stay stored and become inactive. The UI explains
that definitions are shared by all classes of the chosen grade/subject/semester. Native header
dragging saves the complete definition order; left/right arrows remain available. The API rejects
duplicate, incomplete, and mixed-scope reorder requests.

Use one backend programme constant for the Grade 4 start of L2, reconciling the existing seed/workbook
with roster editing's outdated Grade 5 threshold. Clearing a selection is allowed in any grade.

## Consequences

- Preview changes remain reversible until commit and cannot bypass parser or server validation.
- Removing an already enrolled student is a separate, explicit class-table action.
- No schema migration, third-party processor, or new dependency is needed.
- The original workbook is unchanged; selecting it again starts a fresh review.

## Supersedes

ADR-047's restriction of draft operations to class moves only. The paged import roster uses the
page scroll rather than ADR-045's bounded viewport so its sentinel loads rows at the end of the
visible roster. Preview parsing is limited to 60 requests per minute per account, separately from
the unchanged 10-per-minute commit limit; edits and page requests cannot consume the commit budget.

---

# ADR-049: Readable assessment pages and Grade 4 second-language rubrics

**Status:** Accepted

**Date:** 2026-09-08
**Phase:** 2.1, 2.4, 3.6, 4.1

## Context

Fitting every teacher assessment on screen (ADR-039) broke long criterion labels into tiny
fragments. The school also clarified that Grade 4 German and French use only the 1-2-3 rubric:
no numeric exam/homework columns, teacher-comment columns, or score average.

## Decision

The teacher grid shows up to three assessments at a time, reducing to two or one as the available
width narrows. Category buttons filter the assessments; previous/next controls expose every
column in its configured order. Full sentence headings use normal case and readable type, with
ownership notices on their own line. Student names remain visible, and a scale legend explains
1-2-3. The document remains the only scrolling surface. Switching assessment pages or categories
does not navigate away from the class or clear the Zustand draft; Save still drains every dirty
cell, including hidden columns, through the existing version/conflict and ownership checks.

`academics/programme.py` defines Grade 4 second-language type eligibility. Creation and updates
reject non-scale columns and score-average flags. Copying into Grade 4 includes only eligible
rubrics. Seed and academic-year rollover use the same rule, while Grade 4 English and Grades 5-8
second languages retain their existing column types.

Alembic data migration `f4b82d903e61` disables existing Grade 4 German/French score and text
columns and clears average flags in active/setup years. It preserves column identities, saved
values, audit history, and archived years. Grid reads and report builders already select active
columns, so both reflect the correction. Downgrading does not automatically resurrect disabled
columns; any restoration is deliberate. No schema fields or dependencies are added.

This focused teacher view supersedes ADR-045's bounded teacher-grid viewport: pagination keeps
columns readable while student rows follow the page scroll. Captions and readable controls remain;
the admin class table still uses the contained viewport.

## Consequences

- Teachers can read complete criteria, with an extra category/page action to reach other columns.
- Normal page scrolling and the phone stepper remain available.
- Old saved data is retained; current Grade 4 second-language assessments and reports use scale3.
- Archived reports retain the configuration under which they were issued.

## Supersedes

ADR-039's requirement that every teacher assessment be visible simultaneously. Its single
vertical scroll rule and the admin workspace behavior remain in place.

---

# ADR-050: Keep screen logic focused and confirm the values actually submitted

**Status:** Accepted

**Date:** 2026-09-08

**Phase:** 2-3, maintenance

## Context

The teacher grid and admin class page had accumulated cell rendering, form state, database
operations, dragging, navigation, and repeated UI configuration in single large files. The grade
save callback also read the live draft after the request completed. This could show an old grade
after clearing it, or silently lose an edit made while the request was pending.

## Decision

Keep the existing applications, libraries, database model, public API, and screens. Extract the
teacher's cell and table rendering into the existing grid folder. Let the admin's teacher,
column, and roster components own their corresponding forms and mutations. Keep the table and
column forms mounted when switching to the removal panel so unfinished form values survive.

Share the duplicated shell/academic labels, sibling-tab prefetch loop, and admin cache
invalidation. Use SQLAlchemy's direct scalar-query API instead of wrapping execute results, and
keep one implementation of writable-class validation and grant renewal. Column dragging and
arrow controls now use the same reorder operation, including inactive columns in its scope.

Save responses update the query cache from a snapshot of the submitted cells, including explicit
nulls. Only applied cells are acknowledged. Newer edits remain in Zustand and use the returned
versions for their next save. A draft generation counter prevents late responses from restoring
changes after the user discards or leaves a grid. Conflict overwrite, ownership confirmation,
and the server's audit/undo rules remain in place.

## Consequences

The two main route files become much smaller, and each editor can be understood independently.
Explicit component props and save regression coverage add some code; this change prioritizes
simpler responsibilities and removes repeated logic rather than compressing business rules.
No dependency, migration, generated-client change, or feature removal is required.

---

# ADR-051: Public demo visitors are pseudonymous temporary administrators

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.1 (public demo)

## Context

The public demo must let any Google account, personal or Workspace, try the product as an
administrator, while the school build keeps its fail-closed Workspace-domain, allowlist, and
stable-subject rules (ADR-012, ADR-038). Six NOT NULL foreign keys reference `users` (teaching
assignments, grade `updated_by`, save batches, audit actors, override grants, job requesters), so
a visitor row cannot simply be deleted without destroying audit history. Personal data from
visitors must never accumulate in a shared database that other visitors can browse.

## Decision

A `DEMO_PUBLIC_LOGIN` setting, honoured only when `ENV=demo` and refused at startup anywhere
else, switches the OAuth callback to visitor mode. A verified Google identity becomes an active
admin and coordinator whose email is a random synthetic address in `ALLOWED_GOOGLE_DOMAIN` and
whose name is a generated label. Google's `sub`, email, name, and picture are not stored. A
`demo_visitors` row links the account to an HMAC-SHA256 of the subject keyed by `SESSION_SECRET`,
with an absolute `expires_at` 24 hours after creation.

Repeat logins reuse the account while it has at least one live Redis session; each session's TTL
is capped at the remaining lifetime. Logout ends only that device's session. When the last session
ends, or a login finds an expired or session-less account, the account is scrubbed: sessions
revoked, hash nulled, row deactivated, identity fields replaced by a tombstone. Rows are removed
physically by the demo reset (ADR-052), never by cascading deletes. Visitors cannot modify other
visitor accounts, managed users must still use the configured synthetic domain, and new visitor
accounts are capped per day.

## Alternatives considered

- Store the real email and name for a friendlier UI. Rejected: personal data in a shared,
  browsable database and in provider history.
- Immediate hard delete with cascades through audit tables. Rejected: a demo-only deletion path
  through the school's audit tables.
- Visitor state in Redis only. Rejected: not durable, not covered by the database fixtures, and
  the guardrails would fail open after a cache flush.
- An isolated sandbox per visitor (schema or Neon branch). Rejected: exceeds the free-tier limits
  and adds tenant plumbing the school never needs.

## Consequences

- The demo needs no allowlist row and no bootstrap administrator for visitors; the seeded school
  stays shared.
- School mode is unchanged: the table stays empty, the flag cannot be enabled, and no user is
  ever deleted.
- The 24-hour lifetime is enforced by Redis TTL, so `current_user` gains no extra query.
- A scrubbed tombstone row remains until the nightly reset; it holds no identity data.
- The demo OAuth client's consent screen must be published to production so non-test users may
  sign in.

---

# ADR-052: The demo resets nightly by restoring a Neon branch from its golden parent

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.2 (public demo)

## Context

Every visitor is an administrator of one shared fictional school (ADR-051), so edits, vandalism,
and tombstoned visitor rows accumulate until something removes them. The demo runs on free
hosting: Render has no cron and sleeps after 15 minutes, Neon Free allows 0.5 GB and a 1 GB-month
change history, and reseeding the 42 MB school inside the application would take minutes over the
network every night.

## Decision

The demo database is a Neon child branch of a pristine, seeded parent. A reset calls Neon's branch
restore with the parent as source, which replaces data and schema in seconds while the branch id,
compute, and connection string stay the same. The API then disposes its connection pool, flushes
every session, visitor tally, and rate-limit key from Redis, and records the local reset date in
Redis, the one store the restore does not overwrite.

The day boundary is midnight in `DEMO_RESET_TIMEZONE` (Europe/Istanbul). A GitHub Actions
schedule requests the reset at that time through `POST /api/ops/demo/reset`, authenticated by
`X-Ops-Token`, and polls `GET /api/ops/demo/status` until the day's reset is recorded.
Independently, the API runs a self-heal loop: at startup and every minute it compares the recorded
date with today and runs a catch-up reset when they differ, so a delayed workflow, an auto-disabled
schedule, or a sleeping instance never leaves yesterday's edits in place. A Redis lock makes resets
single-flight, and a state key makes data routes answer `503 demo_resetting` while the branch is
being replaced. Public `GET /api/demo` lets the login page describe the demo and its next reset
before sign-in; `/api/me` carries the visitor's expiry and the next reset for the in-app banner,
which turns into a warning in the last fifteen minutes.

At startup the demo image migrates and, if empty, seeds the golden parent before migrating its own
branch, so a release can never be reverted by the next reset. The seed creates a synthetic
administrator when none exists, because a visitor-only demo has no allowlisted person.
`DEMO_PUBLIC_LOGIN` refuses to start unless the reset is configured. The OpenAPI export runs under
the demo profile so the generated client documents the demo-only routes.

## Alternatives considered

- In-app truncate and reseed: provider-neutral, but minutes of downtime per night and a full
  rewrite of the dataset into Neon's change history.
- Restore a golden `pg_dump`: a second copy of the fixture to keep in sync, and slower than a
  branch restore.
- A per-request marker check instead of a loop: one Redis round trip on every request for a
  condition that changes once a day.
- Preserve visitor accounts across the reset: more code for no visible benefit; accounts die at
  midnight and the 24-hour rule becomes automatic.

## Consequences

- A reset takes seconds; visitors see a 503 for that moment and are then signed out.
- The path is Neon-specific. The school build never uses it, and another demo host would need a
  different implementation behind the same ops routes.
- Operators create the child branch and set `NEON_*`, `OPS_TOKEN`, `DATABASE_URL_GOLDEN_DIRECT`,
  and the `DEMO_OPS_TOKEN` GitHub secret; `infra/README.md` is the runbook.
- The demo OAuth consent screen must be published to production before `DEMO_PUBLIC_LOGIN` is
  turned on.

---

# ADR-053: One public application repository, private deployment overlays, released images

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.3 (public release)

## Context

The project must be a portfolio piece anyone can read and a product one school runs, without the
school's branding, secrets, or operations ever entering the public tree and without maintaining
two copies of the application. Both installations must receive every fix without hand-copying
code, and the school must approve each upgrade explicitly.

## Decision

Application code lives in exactly one repository, the public `flrc` repository under the MIT
licence. It contains the code, tests, migrations, generic branding, and both the demo and school
runtime policies. It was created from a reviewed, squashed snapshot of the private development
history; that history stays private and is not published.

A version tag `vX.Y.Z` on the public repository publishes two multi-architecture images to GHCR,
`flrc-backend` and `flrc-web`, and a GitHub Release (`.github/workflows/release.yml`,
`docs/RELEASING.md`). The tag must equal the version in `apps/backend/pyproject.toml`.

A school's private repository holds only a Compose file that pins those image tags, the Caddy
site address, the branding overlay (ADR-054), the environment, and operational documentation.
Dependabot's Compose support opens the upgrade pull request there when a new tag exists; merging
it is the approval, and rolling back is reverting it. The public demo deploys from `main`
automatically and does not wait for a tag.

## Alternatives considered

- Flip the private repository to public with its full history: every past commit message and
  author identity becomes permanent; a reviewed snapshot is safer.
- A git submodule pin plus a build in the private repository: it requires the whole Node, uv, and
  Docker toolchain in every school repository and a cross-repository token for update requests.
- A subtree copy synchronized by a bot: a second physical copy of the application, which is the
  drift the single-repository rule exists to prevent.

## Consequences

- One place to change code; one tag to release; one pull request per school to upgrade.
- MIT is irrevocable for published versions. Copyright remains with the author, so future
  versions can be relicensed only while every contributor has assigned or licensed their work.
- The private repository never builds anything, so it cannot drift from the release it pins.
- GHCR packages inherit the public repository's visibility; a school pulls without credentials.

---

# ADR-054: Branding is a runtime overlay served next to the app

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.3 (public release)

## Context

ADR-034 compiled the school's name and logo into the web builds through `pnpm brand`, which was
right while every deployment was built from a checkout. ADR-053 ships prebuilt generic images, so
a school can no longer rebuild to rebrand, and ADR-040 removed the palette's dependency on the
accent colour, which leaves only the name, logo, favicon, and title as deployment-specific.

## Decision

Each web app serves a `branding/` folder: a blocking `brand.js` that sets `window.__FLRC_BRAND__`
before the app starts, plus `logo.svg` and `favicon.svg`. `@flrc/branding` prefers that runtime
object and falls back to the bundled generic values; `index.html` loads the script and favicon
from that folder, so the admin app resolves them under `/admin/`. `pnpm brand` still generates the
generic folder, the report assets, and the derived HTML, so the demo and a fresh clone stay
consistent and `pnpm brand:check` keeps guarding drift.

The `flrc-web` image serves `/branding/*` and `/admin/branding/*` from a mounted folder with the
generic files as fallback. The API reads `brand.json` and `logo.svg` from `SCHOOL_BRANDING_DIR`,
the same mounted folder, below the explicit `SCHOOL_NAME` and `SCHOOL_LOGO_PATH` overrides and
above the synced assets.

## Alternatives considered

- Keep build-time branding and build per school: rejected with ADR-053's delivery model.
- Fetch a JSON file at runtime from the app: a request before the first render and a visible
  flash of the generic name; a blocking script sets the identity before paint.
- Inline the brand into `index.html` at deploy time: it requires rewriting a built artifact and a
  CSP hash for inline script.

## Consequences

- A school rebrands by replacing three files in one folder; no build, no image change.
- `brand.js` is a five-line contract documented in `branding/README.md`.
- The demo and the school share one code path, so the overlay is exercised on every visit.

## Supersedes / Superseded by

Supersedes ADR-034's compiled-in name and logo. ADR-034's single source folder, `pnpm brand`, and
drift check remain.

---

# ADR-055: School hosting is one Compose stack on a school-owned server

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.4 (school deployment)

## Context

ADR-019 allowed a school-controlled VM as a fallback to the managed profile. With ADR-053, the
application ships as two images, so the school no longer needs the managed providers, and the
KVKK posture is simplest when every account and every byte belongs to the school.

## Decision

The school runs one Hetzner server (4 vCPU / 8 GB, EU) created from `infra/hetzner/cloud-init.yaml`
with Docker Compose managing five services: `web` (the `flrc-web` image: Caddy, both SPAs, the
`/api` proxy, TLS, the branding overlay), `api` and `worker` (the `flrc-backend` image), PostgreSQL
18, and Redis. A one-shot `migrate` service applies migrations before the API starts. Only `web`
publishes ports; the API is reachable solely through Caddy, which injects the school-mode gateway
secret and strips `Cf-Connecting-Ip`.

The school's private deployment repository starts from `infra/school-template/`: the pinned
Compose file, an environment template, the branding overlay, Dependabot for image bumps, and a
deploy workflow that ships the Compose file and branding over SSH, pulls, applies, and checks
health; merging the pull request is the approval, and a paid GitHub plan can add a required
reviewer on the `school` environment. Secrets exist only in `/srv/flrc/.env`
on the server. All accounts (Hetzner, DNS, Google Cloud, GitHub, backup storage) are school-owned
with the developer as a member. The runbook is `docs/SELF-HOSTING.md`.

## Alternatives considered

- The managed profile (Render, Neon, Upstash, Cloudflare): more moving parts and providers to
  contract with, and Vercel's non-commercial terms exclude it for the school.
- A separate edge proxy in the private repository: this moves the security-relevant routing order
  out of the tested public image.
- Developer-owned infrastructure billed to the school: student data on a private individual's
  account, contrary to the school-as-controller posture.

## Consequences

- One monthly invoice of roughly €9, one server to patch, and a runbook a school IT person can
  follow.
- Upgrades and rollbacks are pull requests; nothing is built on the server.
- The database and Redis have no public ports; backups must leave the machine another way
  (ADR-056).
- A single server is a single failure domain; the daily off-site backup and restore drill are the
  recovery plan.

---

# ADR-056: Encrypted nightly backups to the school's Shared Drive, proven monthly

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.5 (school operations)

## Context

ARCH §7.5 promised weekly dumps to school-owned Google Drive from a GitHub Actions workflow. On the
school-hosted profile (ADR-055), the database has no public port, the school wants daily copies kept
for a week, academic years must remain retrievable for years, and a backup is a hypothesis until a
restore succeeds. Service accounts have no Drive storage of their own, so the destination must be
a Shared Drive the school owns.

## Decision

A `backup` service in the school's Compose file runs the backend image with `flrc backup schedule`.
Every night at `BACKUP_AT` (02:30 Europe/Istanbul) it runs `pg_dump` with the PostgreSQL 18 client
now included in the image, encrypts the dump with age to the school's recipient key, uploads the
file and a SHA-256 companion to the school's Shared Drive folder through a service account, and
keeps the newest `BACKUP_RETAIN` (7) copies by upload time, so a failed night never shrinks the set.
On day `BACKUP_RESTORE_TEST_DAY` of each month it downloads the newest copy, verifies the checksum,
decrypts it with the identity the server holds, restores it into a scratch database on the same
server, checks the schema revision against the live one and that students and users are present,
and drops the scratch database. Every run also bundles each academic year in the `archived` state
that has no `archives/<label>/manifest.json` yet: every non-empty report set per semester as PDF,
the whole-year workbook, an encrypted full dump from that moment, and a manifest with checksums,
counts, the application version, and the schema revision. Archives are never pruned.

The service writes `status.json` into a bind-mounted `backups/` folder; nothing in it is personal
data. The deployment repository's daily workflow reads that file over SSH and fails when the last
success is older than 26 hours, the last run failed, or the restore test failed or is older than
40 days. A person performs the drill in `docs/RESTORE-DRILLS.md` each semester with only the Drive
folder and the identity from the school safe. The identity and the service-account key live only
in the server's `.env`; the recipient alone cannot decrypt anything.

## Alternatives considered

- Keep the GitHub Actions workflow: it cannot reach a database with no public port, and it would
  hold the school's credentials in a repository secret.
- Hetzner Storage Box with restic: decided against earlier because the school already owns Google
  Workspace and wants one vendor for its records.
- A dedicated backup image: the backend image already has the application, the reports, and the
  workbook builder that the year archive needs; adding the client tools was smaller.
- Age-based retention: it deletes the last good copy after a week of failures; count-based
  retention cannot.

## Consequences

- One `.env` block and one Shared Drive folder configure the whole backup story.
- Losing the age identity loses every backup; the runbook requires two copies outside the server.
- The backend image grows by the PostgreSQL client tools and the Drive libraries.
- `scripts/upload_backup_to_drive.py` and the weekly workflow are removed; the module replaces
  them.

## Supersedes / Superseded by

Supersedes the weekly Drive workflow described in handbook step 4.5 and ARCH §7.5.

---

# ADR-057: Private report overlays and teacher report identities

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 3 (teacher administration), 4.2 (reports)

## Context

Schools need their own report layouts, original PDF back covers, and different principals for
primary and middle grades. Teacher names and signatures must follow class assignments. The public
application and demo must remain generic, and private signature assets must not be served as
unauthenticated branding files.

## Decision

Add nullable `report_name`, deferred `signature_png` (PostgreSQL bytea), and `signature_digest`
columns to the existing `users` identity. The account name remains the fallback when report_name
is empty. Reuse `teaching_assignments` to gather the subject's teachers once per report set;
English main and skills roles assigned to one person produce one signer with both role labels.
No student fields, grade values, authorizations or assignment rules change.

A separate `report_identity_audits` table records the actor, target, old/new report name and old/new
PNG digest in the same transaction. The grade-specific audit table requires student and column
foreign keys and cannot represent this administrative event. Image bytes are never duplicated in
this audit. Audits follow the target account's retention and keep a nullable actor reference.

The admin teacher screen edits the printed name and uploads, previews, replaces or deletes the PNG
through admin-only, same-origin routes. Validate PNG structure, checksums, one frame, at most 1 MiB,
4 million pixels and 4096 pixels per side, then re-encode without metadata. Pillow is already a
WeasyPrint dependency and is now declared directly. Storage stays in the existing school database
and its encrypted backups; no filesystem upload store or new processor is introduced. The public
demo's temporary visitor accounts cannot acquire report identities.

`SCHOOL_BRANDING_DIR/reports/config.json` is an optional versioned private overlay. It chooses
Jinja HTML templates, image assets, original German/French back-cover PDFs, and principal identities
for `primary` (grades 1-4) and `middle` (5-8). Templates use a sandbox with automatic HTML escaping;
asset paths must remain inside the report folder. WeasyPrint continues to allow only data URIs.
PDF covers replace duplex back pages, retaining the original cover content. Invalid cover size or
page count fails explicitly. Default templates and public branding retain their existing appearance.

School deployment repositories keep real names, artwork and templates under their private branding
folder and mount only a generated `branding/public/` directory into the web service. The shared
Caddy configuration additionally serves only `brand.js`, `logo.svg`, and `favicon.svg` under either
branding URL. Template/identity changes affect newly generated reports; existing exported PDFs
remain unchanged. School identity caches reload on API/worker restart.

## Validation and deployment

Migration `e2a91c743b60` follows the existing head and preserves accounts. Tests cover upgrade and
rollback, PNG validation and metadata stripping, authorization and origin checks, identity auditing,
assigned-teacher selection and deduplication, principal selection, sandbox/path boundaries, duplex
cover replacement and generic fallback. Both application images must be released and upgraded
together before a school's overlay can use the feature. Editing repository configuration does not
apply a production migration or publish a release.

---

# ADR-058: Isolated local school playground and explicit operational schedules

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 4.2 (report verification), local development and deployment

## Context

Private branding alone did not provide a usable local school: the published images predated
report identities, the worker was not launched, and the criteria and teacher manifest still
required manual setup. Copied repositories also scheduled resets, backups and deployment before
their credentials or servers existed.

## Decision

A school may keep a separate `compose.local.yaml` and launcher in its private deployment repo.
The launcher builds the current application source, starts isolated PostgreSQL/Redis/API/worker/web
services, applies migrations and seeds an empty playground. Data and uploaded signatures persist
across restarts. A local seed must verify its exact test database and refuse to overwrite existing
work; school criteria are applied only to newly created, ungraded columns.

The private localhost entry point runs in `ENV=test` and offers an account chooser for the seeded
local domain. It uses the existing Redis session and HttpOnly cookie functions, retains role and
origin checks, and refuses other environments or database targets. It is mounted only in the local
Compose profile; the shared application image and production entry point do not contain this
chooser. Only the web port is published, bound to `127.0.0.1`. This is a sample-data playground,
not the production authentication configuration.

Operational workflows require explicit repository enablement variables. CI and security checks
remain automatic. Unconfigured scheduled operations are skipped; manual runs still fail clearly
on missing credentials. Enable keepalive only in the repository that owns the demo. A skipped
backup job does not assert that a backup exists.

## Validation

Verify first startup and migration, idempotent seeding, authenticated admin/teacher screens,
teacher identity editing and persistence, source-grade PDF page counts and principal placement,
private-asset denial, and a queued year export through the real worker. Verify the complete local
stack can stop and restart while retaining identity changes. Operational fixes pass the existing
GitHub CI and dependency audit before merging.

---

# ADR-059: Whole-class rating drafts and explicit rating labels

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 2.4-2.5 (grid and Save All)

## Context

Teachers need to isolate written comments, set every 1-2-3 assessment for one pupil or a
whole class, and see the report-card meanings of those ratings. The old category filter
omitted ungrouped comments, and a full-class rubric can exceed the 500-cell save limit.

## Decision

The notes filter selects text columns explicitly in both table and single-pupil views.
Bulk controls change only scale3 columns for the current class, subject and semester,
across all assessment categories. They update Zustand in one operation, preserve any
existing draft's expected version, and leave numeric scores and comments intact. They do
not call the API until Save. Existing ownership confirmation, optimistic concurrency,
audit entries, and undo remain in the normal save path. Locked semesters expose no bulk controls.

The save request permits up to 2,000 cells so ordinary full-class rubrics fit one audited
save batch and one undo operation. The bound is retained; no schema or grading-scale change
is required. The API contract is regenerated from this validation rule.

Rating labels use the existing localized UI vocabulary: Geliştirilmeli, İyi and Çok iyi in
Turkish, with corresponding German, French and English translations. Primary English adds
faces beside the words. German and French show the words without faces, including locked cells.

## Validation

Browser tests cover notes-only filtering, student and class bulk edits across hidden
categories on desktop and phone, all three values, read-only grids, labels and faces, and
edits made while a save is pending. Draft tests preserve scores, comments and original
versions. Backend tests save 600 rating cells as one audited batch and undo all of them,
and verify oversized requests are still rejected. The existing two-writer collision test
continues to require explicit overwrite confirmation.

---

# ADR-060: Teacher comments in every programme and a compact English grid

**Status:** Partially superseded by ADR-063 (middle-school English comments only)

**Date:** 2026-09-10

**Phase:** 2.1.3, 2.4 (column defaults and grade grid)

**Current reading:** the decision below records the 2026-09-10 choice. ADR-063 removes the
middle-English opinion field and its notes filter. Primary English and German/French comments,
grade-4 L2 rating rules, and the compact angled English grid remain in effect.

## Context

The grade 4 German/French restriction incorrectly excluded text fields along with
numeric scores, leaving those classes without teacher comments. Middle-school English
also lacked a default comment field and paged eleven short score headings across four screens.

## Decision

Grade 4 second-language classes accept scale3 assessments and text comments, without
numeric scores or averages. Every default programme includes a final teacher comment field.
An additive migration supplies missing comment fields in configured subjects of non-archived
years. It preserves existing definitions, disabled comments, saved values and audit history;
it neither reactivates old fields nor deletes fields on rollback. No new table or sensitive
student attribute is needed. Administrators retain the ability to configure text columns.

Teacher notes always appear as the final filter category on desktop and phone. A subject
without an active text field explains how an administrator can add one.

At sufficient width, middle-school English shows all numeric fields followed by comments.
The teacher selected 45-degree headings with matching slanted borders. Narrow screens retain
assessment paging and the existing single-student view. Input ownership, drafts, audited
saves, keyboard navigation and conflict handling use the same components and services.

## Validation

Check migration idempotence and preservation of historical values and archives, comment
creation and editing in the admin API, save/audit/report inclusion, and seed/copy/rollover rules.
Browser checks cover the final notes filter and editing on desktop and phone, all default
English headings in four locales, laptop widths, keyboard navigation and the narrow fallback.
Private deployment checks verify every grade and semester against the school's source rows.

---

# ADR-061: Four or five sentence assessments per laptop page

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 2.4 (grade grid)

At the teacher's request, the three-column capacity in ADR-049 is replaced with up to five
columns for sentence-based assessments. A 184px student column and at least 180px per
assessment allow four columns at 1280px and five at 1366px with the sidebar open. Complete
sentences remain visible in normal case at 14px; smaller screens reduce the column count.
Compact toolbar and header spacing makes room for the grid. Category filters, the final notes
category, bulk rating drafts, keyboard navigation and the existing save path remain available.
The middle-school English overview continues to use the selected 45-degree headings.

Browser checks verify the visible count at laptop widths, every column's reachability and
unclipped text, grade 4 English/German/French labels and faces, paging drafts, notes and saves.

---

# ADR-062: Bounded bulk reads and shared field behavior

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 2-4 maintenance (grade fields, administration, imports and year exports)

## Context

A codebase-wide simplification review found per-row database reads in assignment updates and
imports, full result materialization in year exports, and duplicated field and language-control
logic. Existing route splitting, per-cell draft subscriptions and parallel PDF rendering already
address their respective workloads; those designs remain in place.

## Decision

- Validate every assignment change, then apply the final change for each class/role using one
  existing-assignment lookup. The 40-slot regression case uses 5 SELECTs instead of 44.
- Load a year's enrollment identities and language rows once during import commit. The 40-row
  existing-roster case uses 8 SELECTs instead of 126. Numberless rollover identities are consumed
  only once; ambiguous names still create a new identity instead of merging existing people.
- Write all seven year-export sheets through one streaming writer, fetching at most 1,000 rows
  per batch. Close each result before committing durable progress. Preserve the workbook columns,
  values, formula neutralization and sheet order.
- Share filled-cell lookup between completeness and missing-cell views. Fetch IDs rather than
  grade objects and comment bodies; index assessment IDs by grade and subject once per request.
- Keep label fallback and grade-value selection in `academics/fields.py`, shared by live grids,
  archives and report builders. Optional report labels retain their existing null behavior.
- Share the language switch in the UI package through explicit language/label/callback props.
  Memoize import-draft serialization so search and drag state do not repeatedly sort unchanged edits.

## Consequences and checks

The public API, database schema, permissions, audit/save-conflict rules and printed layouts are
unchanged. Request-local indexes avoid cache-invalidation rules, while streaming exports trade
one full result allocation for bounded row batches. No dependencies are added.

`tests/test_bulk_operations.py` covers query budgets, repeated assignment slots, input validation,
identity preservation, rollover namesakes, a 1,202-student streaming export, and completeness.
`e2e/language-switch.spec.ts` covers all four locales and persisted selection in both apps.
Run these with the complete backend and browser suites; regenerate the client to check contract
drift and run JavaScript lint, typecheck and production builds before merging.

---

# ADR-063: No opinion field in middle-school English

**Status:** Accepted

**Date:** 2026-09-11

**Phase:** 2.1.3, 2.4 and 4.2

The developer confirmed that grades 5-8 English must not include a teacher opinion field.
This restores the handbook's original middle-school English programme and supersedes that
part of ADR-060. Primary English and German/French retain their comments.

Remove the middle-school English default text column and reject its creation or conversion
through the columns API. Copy and rollover use the same programme rule. A new migration
deactivates existing middle-school English text definitions, including synthetic archive years,
without deleting definitions, values, versions or audit records. Grids, report generation and
archive/history views omit the retired opinion fields; audit and workbook exports retain the
underlying historical data. Existing downloaded PDFs remain unchanged.

The teacher grid has no notes filter for this programme and reserves space for the final
angled score heading. Admin forms do not offer text columns for middle-school English.
Tests cover creation, copying, migration idempotence, retained values and absence from reports.

---

# ADR-064: One Vercel project serves the public demo

**Status:** Accepted

**Date:** 2026-09-11

**Phase:** 1.11 / demo hosting

## Context

The demo ran as three Vercel projects: one per SPA and a gateway that owned the public domain and
rewrote `/admin*` and `/` to the two `*.vercel.app` deployments and `/api/*` to Render. Every
browser request crossed two Vercel deployments, the two panels could be on different commits, the
panel cross-links lived in per-project environment variables, and an empty trailing segment in the
gateway rewrite answered 404 for `/admin/`. The school image (ADR-054, ADR-055) already serves both
builds from one Caddy container, so the demo was the only profile with a separate routing layer.

## Decision

Serve the demo from one Vercel project rooted at `infra/vercel`. The workspace package
`@flrc/demo-web` depends on both apps, so Turborepo builds them first; its own build assembles the
teacher output at the site root and the admin output under `admin/`, checks that the admin build
keeps `/admin/` as its asset base, and refuses a bundle that links to a Vite development port. The
project's `vercel.json` sets `trailingSlash: false`, rewrites `/api/:path*` to the Render API, and
falls back to the two `index.html` files for client routes. Production builds default the panel
cross-links to `/admin/` and `/`; `VITE_ADMIN_URL` and `VITE_TEACHER_URL` remain as overrides for
layouts that serve the panels from different origins, such as the two-port CI preview. The per-app
`vercel.json` files and `infra/vercel-gateway` are removed. The `js` CI job builds the same package,
so the assembled layout is checked on every pull request.

## Alternatives considered

- Keep three projects and only fix the trailing-slash rewrite: leaves the double hop, the deploy
  skew, and the environment-variable cross-links.
- A root `vercel.json` with the repository as the root directory: works, but puts hosting
  configuration at the repository root and needs a shell build step; a workspace package keeps it
  under `infra/` and reuses Turborepo ordering.
- Merge the two SPAs into one application: rejected in ADR-022 and unchanged here; they stay
  separate builds.
- Serve the demo from the `flrc-web` image on Render: possible, but a static host is free and the
  image is the school profile's concern.

## Consequences

- One deploy per commit contains both panels; teacher and admin cannot drift apart.
- One hop per request; the `*.vercel.app` targets disappear from configuration.
- The demo and the school image share one path layout, so the ADR-022 routing rules exist in one
  configuration per profile.
- Each deploy builds both apps, roughly twice the previous build time; one preview URL covers both
  panels.
- A broken admin build fails the whole deploy before anything goes live, which is stricter than a
  partial update.
- The public domain must move to the new project and the three old projects must be deleted; until
  then the demo keeps serving the previous layout.

## Supersedes / Superseded by

Amends ADR-022: the two SPAs remain separate builds and the public routing rules are unchanged, but
on the demo they form one deployment unit instead of two deployments behind a gateway. Supersedes
the three-project assembly in handbook Step 1.11.4.

---

# ADR template for future decisions

```md
# ADR-065: Title

**Status:** Proposed | Accepted | Superseded  
**Date:** YYYY-MM-DD  
**Phase:** x.y

## Context

What situation forced a decision?

## Decision

What are we choosing?

## Alternatives considered

- Option A.
- Option B.

## Consequences

- Positive consequence.
- Negative or tradeoff consequence.

## Supersedes / Superseded by

Optional.
```
