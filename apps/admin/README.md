# FL-ReportCard admin

The React admin SPA manages class rosters, year-scoped school numbers, second languages,
assessment columns, teacher assignments, imports, lifecycle transitions, and report identities.
It shares UI, generated API types, branding, and four locale bundles with the teacher app.
Relevant handbook steps: 2.1-2.2, Phase 3, and 4.4.

## Run locally

Start the API and development services as described in the [root README](../../README.md).
From the repository root:

```bash
pnpm --filter @flrc/admin dev
```

Open `http://localhost:5174/admin/`. Vite and TanStack Router retain the `/admin/` base.
The `/api` proxy targets `http://localhost:8000`; set `VITE_API_TARGET` for an isolated API.
Configure the backend `ADMIN_ORIGIN` to match the app origin, without the `/admin/` path.
School deployments serve both apps on one public origin and share a host-only session cookie.

## Where to work

- `src/routes/_auth/`: authenticated pages, including the columns editor and lifecycle screens.
- `src/admin/`: reusable roster, class, column, import, and teacher controls.
- `src/admin/ClassAddColumn.tsx` and `src/routes/_auth/columns.tsx`: both column-creation surfaces.
- `../../packages/api-client/`: generated request/response types; regenerate through `pnpm generate`.
- `../../packages/ui/` and `../../packages/i18n/`: shared controls and translated UI text.

Preserve stable student identity when moving enrollments. Columns are shared across a
grade/subject/semester. Grade 4 German/French permit ratings and comments without numeric scores
or averages. The pending ADR-063 changes remove text-column creation for grades 5-8 English;
backend validation remains authoritative for both forms. Archived years reject mutations.

## Check

```bash
pnpm --filter @flrc/admin lint
pnpm --filter @flrc/admin typecheck
pnpm --filter @flrc/admin build
```

There is no admin `test` script. Relevant browser specs include `e2e/admin-workspace.spec.ts`,
`e2e/roster-editing.spec.ts`, `e2e/import-review.spec.ts`, `e2e/lifecycle-assignments.spec.ts`,
and `e2e/teacher-report-identity.spec.ts`. Follow `playwright.config.ts` and CI for the isolated,
synthetic test stack; Playwright does not start it automatically. Do not run shared seeded-database
specs concurrently. The [AI handoff](../../docs/AI-HANDOFF.md) records current review priorities.
