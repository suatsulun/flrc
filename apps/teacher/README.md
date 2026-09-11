# FL-ReportCard teacher

The React teacher SPA opens directly on the grade table, with year, semester, grade, subject,
and class navigation. The desktop grid and phone stepper share unsaved edits, ownership checks,
audited saves, conflict handling, and undo. Relevant handbook steps: 1.10 and Phase 2.

## Run locally

Start the API and development services as described in the [root README](../../README.md).
From the repository root:

```bash
pnpm --filter @flrc/teacher dev
```

Open `http://localhost:5173`. The `/api` proxy targets `http://localhost:8000`; set
`VITE_API_TARGET` for a separate API. Backend `FRONTEND_ORIGIN` must match the browser origin.
The teacher app owns the login page; the API performs Google OAuth and creates Redis sessions.

## Where to work

- `src/routes/`: route guards and the selected academic context.
- `src/grid/grid-table.tsx`, `stepper.tsx`: desktop and single-pupil views.
- `src/grid/assessment-filter.ts`, `assessment-filters.tsx`: categories and teacher notes.
- `src/grid/dirty-store.ts`: unsaved cells and pupil/class rating drafts in Zustand.
- `../../packages/ui/`: shared presentational controls and design tokens.
- `../../packages/api-client/` and `../../packages/i18n/`: generated contract and UI translations.

TanStack Query owns server-confirmed values; Zustand owns what the teacher has typed but has not
saved. Category/page changes must preserve drafts. Bulk 1-2-3 controls edit ratings only and wait
for Save; one request permits at most 2,000 cells. Conflicts require explicit resolution.

Sentence assessments fit four columns at 1280px and five at 1366px with the sidebar open.
At sufficient width, middle-school English uses an overview with 45-degree headings.
The pending ADR-063 changes show its eleven default score columns without teacher notes on
desktop or phone. Primary English and German/French retain comments.

## Check

```bash
pnpm --filter @flrc/teacher lint
pnpm --filter @flrc/teacher typecheck
pnpm --filter @flrc/teacher build
```

There is no teacher `test` script. Browser coverage lives at the root, particularly
`e2e/assessment-grid.spec.ts`, `e2e/conflict.spec.ts`, and `e2e/responsiveness.spec.ts`.
Use the synthetic test stack documented in `playwright.config.ts` and CI, with both
`E2E_BASE_URL` and `E2E_ADMIN_BASE_URL` set for isolated ports. Playwright does not launch servers.
The two-user conflict test must continue using independent authenticated contexts.
See the [AI handoff](../../docs/AI-HANDOFF.md) before reviewing the pending changes.
