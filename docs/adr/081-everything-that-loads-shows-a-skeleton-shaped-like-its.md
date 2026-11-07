# ADR-081: Everything that loads shows a skeleton shaped like its content

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** Product-wide UX (admin and teacher)

## Context

ADR-042 gave both shells a floating "Loading…" pill with a spinner and most pages one generic
skeleton (a title, a bar, three tiles, a block) whatever their real layout. The first app load and
every lazily loaded route showed a full-screen spinner with no shell around it. Several regions
loaded with no placeholder at all: dashboard cards showed "no jobs" before the jobs list arrived,
dialogs and tables printed a bare "Loading…" line, the report centre's class pickers sat empty and
the teacher's class tabs appeared only once the catalogue answered. Switching a year, class or
subject on the class workspace, assignment board and archive replaced the whole page, pickers
included, with the generic skeleton. The school asked for YouTube-style loading: never a blank page
or a lone spinner.

## Decision

- `packages/ui/src/components/skeleton.tsx` holds the shared blocks, built from existing tokens:
  text lines, page header, stat row, card with header, table (standalone and rows inside an
  existing `<tbody>`), form fields, divided list, tab bar (`Segmented`), toolbar
  (`AcademicContextBar`, filter bars) and the teacher grade grid. Each app composes them into one
  skeleton per page in `page-skeletons.tsx`.
- A page shows its skeleton until its first data arrives. A region that loads on its own shows its
  own skeleton while the rest stays usable: each dashboard card (the summary cards, Recent changes
  and Jobs separately), the class workspace's teacher row and roster, report-kind class pickers,
  the downloads list, the student picker's suggestions, the missing-grades and copy-fields dialogs,
  and the next page of Recent changes, the audit log and student search ("Load more").
- Changing the year, class or subject keeps the page header and pickers on screen; only the
  dependent region turns into its skeleton.
- The router's pending component (`route-pending.tsx`) picks the skeleton by route id from a map
  typed against the generated route tree, so a new route fails the type check until it has one.
  While a page's code loads it shows that page's skeleton inside the shell; before the session is
  known (the first app load) it draws `AppShellSkeleton` — the real school mark, the sidebar and
  top bar as placeholders, honouring the stored collapsed states — around the target page's
  skeleton. Sign-in gets its own centred skeleton without a shell.
- Skeleton blocks are `aria-hidden` and stop pulsing under reduced motion. Each page has one polite
  status: the shell's `PageActivity` is now visually hidden and always mounted (announced reliably),
  and a route pending view or a modal dialog with no listening status renders `LoadingStatus`.
- Spinners remain only on buttons (ADR-042's `pending` contract) and on running background jobs.
- `FullScreenLoading` and the generic `PageSkeleton` are removed.

## Alternatives considered

- One generic skeleton for every page: cheaper, but the layout still jumps on arrival and the
  owner saw it as a blank page.
- `placeholderData` to keep the previous year's data while the next loads: shows stale numbers
  under the new year's pickers and hides that anything is loading.
- Splitting the dashboard request so every summary card loads separately: more requests for no
  visible gain, since one read already answers in a fixed number of queries (ADR-079).

## Consequences

- Loading never changes the page's shape, and pickers keep focus while their data reloads.
- Screen-reader users hear one "Loading…" per page instead of a spinner they cannot see.
- Every new page or route needs a skeleton; the route map's type enforces the route half.
- Skeleton components duplicate a little layout knowledge from the pages; a page redesign should
  update its skeleton in the same change.

## Supersedes / Superseded by

Supersedes ADR-042's shell activity indicator and "stable skeletons" sentence; ADR-042's button,
toast, dialog and prefetch decisions stand.
