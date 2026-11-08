# Frontend architecture

Two React SPAs share the API contract, internationalization and component system. Read this when changing navigation, server-state caching, grade drafts or responsive/loading behavior; the [overview](overview.md) explains their deployment boundary.

## Source map

| Path                                                       | Responsibility                                                                                                                                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `apps/teacher/src/routes`                                  | Login, authenticated shell, initial grid redirect, class/subject grid, class report and card preview                                                   |
| `apps/teacher/src/grid`                                    | Dirty store, save merging, keyboard navigation, desktop table, single-student stepper, assessment filters, bulk ratings and ownership/conflict dialogs |
| `apps/teacher/src/class-report`                            | Class-sheet scope/table, PDF delivery, report-mode switch and PDF leave guard                                                                          |
| `apps/teacher/src/page-skeletons.tsx`, `route-pending.tsx` | Teacher loading shapes and exhaustive route-to-skeleton map                                                                                            |
| `apps/admin/src/routes/_auth`                              | Dashboard, classes, columns, students/history, users, assignments, lifecycle, import, reports, archive, audit and recent changes                       |
| `apps/admin/src/admin`                                     | Shared administrative forms/workspaces, feedback, undo toast, query refresh, focus restoration and pending views                                       |
| `apps/admin/src/dashboard`                                 | Completion, readiness, term/setup problems, jobs and recent-change cards                                                                               |
| `apps/admin/src/imports`, `students`, `reports`, `changes` | Workbook review, student picker, report request/download workflows and undo controls                                                                   |
| `packages/ui/src/components`                               | Shell, dialogs, tables, phone cards, skeletons and reusable UI primitives                                                                              |
| `packages/ui/src/grid/cells.tsx`                           | `ScoreCell`, `Scale3Cell`, `TextCell` and shared cell semantics                                                                                        |
| `packages/ui/src/hooks`, `lib`, `styles`                   | Responsive/theme/prefetch hooks, file delivery/telemetry utilities and semantic theme CSS                                                              |

See the [design system](../design/design-system.md) for visual tokens and [writing/translations](../design/writing-and-translations.md) for copy rules.

## Routing and startup

Both `src/main.tsx` files initialize i18n, configure the generated fetch client's `baseUrl` as `""`, create a QueryClient and mount TanStack Router. API URLs stay same-origin. The admin router has `basepath: "/admin"`; its Vite base must agree.

Routes use `createFileRoute` under `src/routes`. The Vite router plugin generates `routeTree.gen.ts`; do not hand-edit that file. `__root.tsx` defines root composition, `_auth.tsx` is the pathless authenticated layout, and its `beforeLoad` checks the shared session query before rendering. Anonymous admin users are sent to the teacher login with a document navigation; ordinary teachers are sent back to the teacher SPA. The teacher app owns the only login page.

`AppShell` and `PanelSwitchLink` live in `packages/ui`. Panel switching is a full-document transition between separate apps, not a router link inside one tree. Teacher-to-admin navigation is visible only for admins/coordinators; admin-to-teacher navigation and logout consult document-exit/leave guards. Development destinations can use `VITE_ADMIN_URL` and `VITE_TEACHER_URL`; deployed defaults use `/admin/` and `/`.

## State ownership and invalidation

[ADR-014](../adr/014-tanstack-query-for-server-state-zustand-for-dirty-state.md) establishes the boundary: **TanStack Query owns server-confirmed values; Zustand owns unsaved human edits.** Local form/view state remains local.

- Both QueryClients default to `staleTime: 30_000` and one query retry. Generated `...Options`, `...QueryKey` and `...Mutation` factories keep keys/request shapes consistent.
- Loaders and authenticated route guards use the QueryClient supplied in router context. `BoardSwitcher` warms sibling class queries on hover/focus and through `usePrefetchSiblings`.
- `apps/admin/src/admin/use-refresh-queries.ts` invalidates every cached variant of named generated operations by its key head's `_id`, rather than refreshing only the visible year's result.
- Administrative undo can affect multiple features, so successful `undoChange` invalidates all queries. A refused undo refreshes recent-change lists so concurrent changes become visible.
- Jobs use Query polling; persistent status comes from the API, never the browser's memory.

### Teacher grid drafts

`useDirtyStore` in `grid/dirty-store.ts` holds `{studentId,columnId,value,expectedVersion}` under `studentId:columnId`. `clearAll` increments a generation counter. Bulk rating changes only `scale3` cells, waits for Save and preserves the original expected version even after refetch. Changing table/stepper presentation must not discard drafts.

`useSaveGrid` snapshots submitted drafts and their generation in mutation context. `mergeSavedGrid` merges applied cells into the submitted grid's Query cache and leaves newer edits intact; generation checks stop late responses from repopulating a discarded grid. Applied cells invalidate the class-sheet operation. Conflicts remain explicit: the user chooses whether to force their values or discard conflict drafts/refetch. Rejected cells are not silently cleared. Backend semantics are in [backend](backend.md#transaction-and-concurrency-rules).

The grid route (`routes/_auth/classes.$classId.$subject.tsx`) defaults to the one-student stepper below **640px** (`STEPPER_MEDIA_QUERY = "(max-width: 639px)"`). Users can explicitly choose “Tablo” (table) or “Tek öğrenci” (single student). This breakpoint is deliberately distinct from the general phone-layout breakpoint. Shared cells, dirty state, save/undo and ownership confirmation work in both presentations. Category/page changes retain drafts; leaving or discarding uses the existing guards.

## Generated API contract

FastAPI/OpenAPI is authoritative. From the repository root, `pnpm generate` first runs the backend's schema export, then `@flrc/api-client` generation. `packages/api-client/openapi-ts.config.ts` consumes `openapi.json` and writes `src/generated` with the fetch client and TanStack Query plugin. The generated operation IDs derive from Python route names. Change the endpoint/schema, export and regenerate; never patch generated types to make a caller compile. Handwritten shared session options live outside `src/generated`.

## Loading-state contract

[ADR-081](../adr/081-everything-that-loads-shows-a-skeleton-shaped-like-its.md) requires the loading UI to resemble the destination, not a generic spinner or an empty-data message. Router defaults show pending UI after 150ms and keep it for at least 300ms.

| App     | Route map                                    | Shapes                                                                                                                                                  |
| ------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Teacher | `src/route-pending.tsx:PAGE_SKELETONS`       | Grid for start/class routes; class report; card preview; separate login skeleton                                                                        |
| Admin   | `src/admin/route-pending.tsx:PAGE_SKELETONS` | Dashboard (including coordinator alias), classes, columns, students/history, users, assignments, lifecycle, import, audit, changes, reports and archive |

The map type is `Record<PageRouteId, ComponentType>` derived from `FileRoutesById`, excluding layout/root routes. Adding a signed-in page therefore requires adding its skeleton mapping. Initial session loading renders `AppShellSkeleton` around the target shape; in-shell navigation renders the page shape without replacing the established shell. `LoadingStatus` announces activity; decorative skeleton content is hidden from assistive technology. Data subsections also have their own skeletons—route pending does not cover later queries.

## Phone layouts

[ADR-082](../adr/082-phones-get-card-layouts-not-sideways-scrolling-tables.md) uses cards instead of forcing wide administrative/report tables sideways. Shared pieces are `PhoneCardList`, `StudentGradeCards` and responsive skeletons.

`PHONE_MEDIA_QUERY` in `packages/ui/src/hooks/use-is-phone.ts` is `(max-width: 767px)`, matching the shell's `md` sidebar/drawer boundary. Prefer CSS (`md:hidden` / `hidden md:block`) for presentational swaps. Use `useIsPhone` only when mounting both layouts would duplicate controls/forms; it subscribes to shared `matchMedia` lists through `useSyncExternalStore`. Do not reuse this 768px boundary for the teacher's separate 640px default-stepper decision.

## Feedback and translation

Both apps use Sonner. The teacher MutationCache supplies generic translated action-failure feedback. Admin MutationCache uses `errorMessage`; mutations with inline error ownership opt out using `meta: { silentError: true }`. `useNotifyDone` displays a 12-second Undo action when a response includes `action_id`; the full undo window remains available through the changes screen. This UI action invokes the [administrative undo API](backend.md#administrative-undo-and-dashboard), not grade-batch undo.

`packages/i18n/src/index.ts:initI18n` initializes the `common` namespace, browser language detection, TR/EN/DE/FR resources and Turkish fallback. Regional languages resolve to base languages (`en-GB` → `en`); `languageChanged` synchronizes `<html lang>`. Database-backed column labels and subject-language naming are not UI translation keys. Stable API error codes are translated on the client. School vocabulary is in the [glossary](../reference/glossary.md).
