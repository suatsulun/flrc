# Development recipes

This maps common changes to their source files and required follow-through; read this when implementing a feature. Apply [conventions](conventions.md), and select checks from [testing](testing.md) rather than running a shared database suite concurrently.

## Add an API endpoint

1. Find the owning feature under `apps/backend/src/flrc/modules/`. Add Pydantic request/response models and a route in that module; reuse `get_session` and the appropriate dependencies in `modules/auth/dependencies.py` (`current_user`, `require_admin`, `require_coordinator_or_admin`, writable year/semester).
2. Choose a unique, stable route function name: `main.py` uses it as the OpenAPI operation ID. Return typed outputs and stable error codes. Validate object scope as well as role; never rely on a frontend guard.
3. If it is a new router, register it in `apps/backend/src/flrc/main.py`; normally add it to `protected_api` so it inherits authentication. Do not put private endpoints alongside the intentionally public health/login routes.
4. Keep writes, auditing, and any undo snapshot in one transaction. Add backend tests covering success, validation, denial, missing objects, and relevant conflict/rollback paths.
5. From root, run `pnpm generate`. `apps/backend/scripts/export_openapi.py` writes `packages/api-client/openapi.json`; `packages/api-client/openapi-ts.config.ts` drives generated SDK/types/Query helpers in `src/`.
6. Migrate all frontend callers to generated operations/types; add translated machine-error handling and query invalidation. Include generated output in the change. Run focused Python/static checks and affected browser coverage.

## Add a migration

1. Change `apps/backend/src/flrc/db/models.py` and read neighboring revisions in `apps/backend/migrations/versions/`. Check whether the data already has a representation; avoid storing unnecessary personal data.
2. Point `DATABASE_URL_DIRECT` at a disposable development database, migrate it to head, then from `apps/backend` run:

   ```sh
   uv run alembic upgrade head
   uv run alembic revision --autogenerate -m "describe schema change"
   ```

3. Read the generated revision: verify `down_revision`, constraint/index names, foreign keys, server defaults, triggers, and any data transformation. Autogenerate is not a substitute for reviewing SQL. Prefer additive-first rollout; never rewrite stored grade history.
4. Implement a deliberate downgrade. Preserve irreversible historical-data protections; a downgrade must not reactivate forbidden grade 5–8 English comments. Explain any intentionally non-reversible data effects.
5. Add assertions to `apps/backend/tests/test_migrations.py` or a focused migration test. On a disposable database exercise upgrade and the appropriate downgrade/re-upgrade; run the serialized migration suite per [testing](testing.md). Never downgrade a school database as a development check.
6. Update affected seed/import/copy/rollover behavior, generated API types if exposed, and [data model](../architecture/data-model.md). A new decision goes in an ADR, not an edit to old revision history.

## Add an admin or teacher page

1. Add a file route under `apps/admin/src/routes/` or `apps/teacher/src/routes/`, following the adjacent `_auth` route convention. Put feature logic/components in its feature directory rather than expanding the route indefinitely. Preserve the admin `/admin/` base and guards in `_auth.tsx`.
2. Load confirmed data through generated Query helpers and the existing query client. Keep filters/navigation in the URL where neighboring routes do; keep unsaved work separate. Define ready, empty, loading, error, and mutation-pending behavior.
3. Add a matching skeleton to admin `src/admin/page-skeletons.tsx` or teacher `src/page-skeletons.tsx`; register its route ID in the corresponding `route-pending.tsx` `PAGE_SKELETONS`. The typed map requires an entry for every signed-in page. Use shared `packages/ui` skeleton/activity components, not a generic spinner replacing the whole screen.
4. Add navigation/role visibility in the relevant app's `src/routes/_auth.tsx`. Match existing `AppShell` navigation and active-state behavior; use document navigation for switching SPAs, preserving existing unsaved-work guards.
5. Add all UI/accessible/error strings in four locale files. Build a card/stacked phone representation and keep the desktop workspace intact; use the [design system](../design/design-system.md).
6. Let TanStack Router's Vite plugin regenerate `routeTree.gen.ts`; do not hand-edit it. Add Playwright checks for the correct role, keyboard flow, loading/error states, desktop 1440 and phone 390×844. Run app typecheck/lint and locale checks.

## Add translation keys

1. Add matching nested keys in `packages/i18n/src/locales/{tr,en,de,fr}.json`. Keep interpolation placeholders equivalent and use the established namespace/key structure.
2. Consume them with `useTranslation()`/`t()`; include button names, form errors, loading announcements, dialog titles, and API failure messages—not just visible headings.
3. For backend machine errors, extend the relevant existing error mapping (admin `src/admin/feedback.ts`, or the affected teacher feature). Do not display raw server text.
4. Run `pnpm i18n:check` and the affected app typecheck. Inspect long German/French labels and phone layout. Use “sütun” for report column in Turkish.

Column labels stored as data are different from UI chrome: preserve subject-language names using `academics/fields.py` and shared i18n label helpers. See [writing and translations](../design/writing-and-translations.md).

## Change reports or add a column type

Ordinary report columns are data, not new database columns ([ADR-008](../adr/008-report-columns-are-data-not-schema.md)). Create/edit them through the existing admin column API/UI; do not add one SQL column per assessment.

For a genuinely new **value type**, trace and update the complete type boundary:

1. `db/models.py` constraints/storage and a new migration if storage changes.
2. `modules/academics/programme.py` eligibility; `columns.py` validation/snapshots; `fields.py` value/label conversion; `modules/grades/router.py` value validation, save/conflict/undo serialization; archive/audit/export consumers.
3. Deterministic `cli.py` seed and E2E fixtures; copy/rollover paths must not introduce disallowed programmes.
4. Teacher grid editors/dirty state and shared UI cells, admin column forms, all locale labels, generated API contract.
5. Report DTOs/builders in `modules/reports/models.py` and `builder.py`, templates under `templates/`, renderer/packaging as required. Do not patch generated assets or private identities into public templates.
6. Add tests for allowed/disallowed combinations, null/zero/boundaries, historical reads, conflict/undo, and PDF content/page geometry for affected report kinds.

For presentation-only reports, keep data builder → HTML template → renderer separate; preserve ordered page mapping, per-class bounded rendering, private overlay containment, short-lived job output, and background execution for larger sets. Consult [reports and jobs](../architecture/reports-and-jobs.md) before changing limits, packaging, or job behavior.

## Add an undoable admin action

1. Read [ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md), `modules/changes/service.py`, `undo.py`, and a similar administration endpoint. Admin undo is not grade-save undo.
2. Add a stable `ActionKind` identifier. Acquire the existing entity locks **before** reading its before-state; preserve account-before-action/assignment, year-before-class, and ordered enrollment locks.
3. Apply the write and call `record_action()` in the same transaction, storing the minimum complete `undo_data` snapshot and display parameters. Use `changed_values()` for patches; do not make unchanged attributes part of a destructive restore. Return `action_id` through `ActionWrite`/`with_action()` or the response model.
4. Register an inverse handler with `@handles(...)` in `changes/undo.py`. Check that current state matches the action's after-state and that restoration is valid **today** using existing business-rule helpers. Raise `UndoBlocked(reason, ...)` on conflict; never partially restore or overwrite later work.
5. Extend `lock_action_accounts()` for any new action referencing accounts, and account-erasure scrubbing in `administration/users.py` when snapshots contain account personal data. Queue required session revocations through `UndoContext.revoke_user_ids`; the router revokes after commit.
6. Use admin `src/admin/undo-toast.ts` `useNotifyDone()` with the returned action ID; update `src/changes/` rendering/translations and query invalidation. Add all four locales for action summaries, changed attributes, and refusal reasons.
7. Test action/write atomicity, success, conflict with newer edits, missing/deleted targets, expiry, repeat undo, authorization, and rollback leaving **all** state unchanged. Retention is centralized at seven days; do not add a competing timer. Permanent account erasure is deliberately not undoable.

## Write an E2E spec

1. Add `e2e/<feature>.spec.ts`; import Playwright `test`/`expect` and `authenticatedContext` from `e2e/helpers/auth.ts` for synthetic users in `seed-e2e`.
2. Import `teacherOrigin`/`adminOrigin` from `e2e/helpers/origins.ts`; never hardcode a port. Each identity needs its own browser context. Close contexts you create.
3. Prefer role/name/label selectors and assert user-observable effects. If mocking an API, match the actual generated contract and mock every request the page requires (including shared catalogs/dashboard calls). Do not mask a broken persistence path with a mock when testing persistence.
4. Include denied/boundary cases and phone viewport where touched. Use delayed responses for skeleton tests and separate 1440 desktop checks. Preserve two independent users for conflict scenarios.
5. Run against the isolated stack in [testing](testing.md#browser-e2e-isolated-application-stack), with `workers=1` and a fresh `seed-e2e` before each suite run. Never make a new spec depend on another spec's mutation.

## Record an ADR

Read [the ADR index](../adr/README.md) and copy the structure of `docs/adr/template.md`. Create the next unused numbered `docs/adr/NNN-slug.md`; do not renumber historical decisions. State context, decision, alternatives, consequences, and links to the source/docs it affects. Update the ADR index and the owning topical documentation. Supersede/link an older decision explicitly instead of silently rewriting history. Record a real trade-off or changed invariant, not a chronological implementation diary.
