# Development conventions

This defines the rules for changing the application; read this when implementing or reviewing code. Feature explanations live in [architecture](../architecture/overview.md), and executable check instructions live in [testing](testing.md).

## Style and ownership

- Keep changes focused and follow the existing feature-first layout. Reuse helpers before introducing another convention or dependency.
- TypeScript is strict. Avoid `any`; narrow unknown boundary input. Use generated `@flrc/api-client` request/response types rather than copying shapes.
- Use React function components, TanStack Router routes/guards, Tailwind v4 CSS-first styling, and owned shared components from `packages/ui`. Do not introduce a v3 `tailwind.config.js`.
- TanStack Query owns server-confirmed state; Zustand owns unsaved human input, especially dirty grade cells. Do not put server cache into Zustand or lose unsaved grid edits in transient component state ([ADR-014](../adr/014-tanstack-query-for-server-state-zustand-for-dirty-state.md)).
- Python targets 3.13; use typed SQLAlchemy `Mapped`, `mapped_column`, and `select`, Pydantic boundary models, FastAPI security dependencies, and explicit transactional services. Ruff line length is 100; rule families are `E`, `F`, `I`, `UP`, `B`. Mypy checks `src/flrc`.
- Prettier owns supported web/config/docs formatting; ESLint flat configs own frontend linting. Lefthook checks staged formatting/lint, not the entire definition of done.

## API contract

FastAPI is the contract source. Paths are under `/api`, browsers call the same-origin proxy, and route function names become operation IDs via `_operation_id()` in `apps/backend/src/flrc/main.py`. Keep those names stable and unique. Return machine-readable errors such as `HTTPException(409, {"code": "undo_blocked", ...})`; translate them in the UI. Use existing error extraction/localization helpers instead of exposing raw server exceptions.

Run `pnpm generate` after contract changes and commit the OpenAPI snapshot and generated client together. Never hand-edit generated types to disguise backend disagreement. Preserve permissions, null/empty semantics, status codes, and callers when changing a contract.

## Database and history safety

- Every schema change uses Alembic. Prefer additive changes first; plan deployment compatibility before removing a column/constraint. Read autogeneration, implement a deliberate downgrade, and add migration tests. Never casually rewrite an applied revision.
- Migrations use `DATABASE_URL_DIRECT` (or the explicit `FLRC_MIGRATIONS_URL` override); the app uses `DATABASE_URL`. Never run schema DDL through a transaction pooler.
- Never rewrite grades/audit history to make a roster change work. `Student.id` is stable identity; class/year membership and school number live on `Enrollment`. Numbers are unique per year **and stage**; `stage` is database-derived, not application-assigned.
- Preserve compare-and-set grade versions, cell-level conflicts, save batches, and audit entries. Silent overwrite is data loss. Admin actions and grade-save undo are separate mechanisms.
- Use existing lock helpers and the global order in [ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md): account rows in ID order before years, classes, assignments and admin actions (`administration/account_locks.py`; `lock_for_admin` when an administrator write must recheck the acting administrator); year before class (`lock_class()`) and before the pupil's yearly enrollment rows, which lock in ID order (`writable_class_year()`, then `lock_enrollments()`); fields a grade save writes key-share in ID order before grade rows. Do not invert these orders in an undo path.
- Rollover copies structure/identity, not grades or audits. Respect programme rules in `academics/programme.py`, including grade 4 German/French ratings without numeric averages and no grade 5–8 English comments. Historical values remain preserved.

See [data model](../architecture/data-model.md), [ADR-070](../adr/070-school-numbers-are-unique-per-stage.md), and [ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md).

## Privacy and dependencies

Use synthetic data only in fixtures, logs, telemetry, screenshots, issues, commit messages, and public examples. Do not include actual school identities, personnel, signatures, domains, private deployment repositories, or credentials. Do not add unnecessary personal fields or a new third-party processor without an explicit decision. Keep student names out of job payloads; use IDs. Follow [security](../security/security-model.md) and [privacy boundaries](../security/privacy-data-map.md).

Before adding a dependency, explain the gap in the current stack, student-data exposure, operational/runtime cost, touched lockfiles, and tests. Use pnpm/uv to change lockfiles; do not manually patch them. Avoid avoidable work and unbounded database/external calls in hot paths.

## Generated and forbidden files

Do not manually change `packages/api-client/src/generated/` (the handwritten `src/session.ts` and `src/index.ts` stay editable), `routeTree.gen.ts`, `dist/`, or package-manager lockfiles. Fix source and regenerate. `pnpm brand` owns `branding/generated/`, app HTML title/theme values, public favicons, and report assets under `apps/backend/src/flrc/modules/reports/assets/`; change branding sources or the deployment overlay instead. Do not commit `.env`, caches, artifacts, real imported workbooks, or private report overlays. Applied migrations are historical inputs, not cleanup targets.

## Git and completion

Use focused conventional commits (`feat(api): ...`, `fix(web): ...`, `test(importer): ...`, `docs: ...`). No AI attribution, generated-by comments, or unrelated churn. Use a branch/PR as described in [CONTRIBUTING.md](../../CONTRIBUTING.md).

A change is ready only when:

- Behavior is implemented end to end; every affected caller, permission boundary, failure path, test, generated contract, and relevant doc is updated.
- Regression tests reproduce the bug before the fix where practical; report actual checks and any unexercised prerequisite.
- UI is checked at desktop width **1440** and phone **390×844**, including long localized text, keyboard interaction, empty/error/loading states, and desktop regression. Phones get card/stacked layouts, not desktop tables with sideways scrolling ([ADR-082](../adr/082-phones-get-card-layouts-not-sideways-scrolling-tables.md)).
- New routes have matching route-pending skeleton entries and loading shapes; background refresh preserves usable content ([ADR-081](../adr/081-everything-that-loads-shows-a-skeleton-shaped-like-its.md)).
- User-facing strings, API error translations, accessible labels, and interpolation keys exist in **tr/en/de/fr**. Turkish report-column wording is “sütun” (column), not “alan”.
- An architectural decision/change of invariant has an [ADR](../adr/README.md); no stale alternative instructions remain.
- Relevant checks and final-head CI pass; review findings are resolved. Never describe an unrun check as passing.
