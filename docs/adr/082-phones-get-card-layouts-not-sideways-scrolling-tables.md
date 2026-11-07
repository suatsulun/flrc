# ADR-082: Phones get card layouts, not sideways-scrolling tables

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-08  
**Phase:** Product-wide UX (admin and teacher)

## Context

A measured pass over every page at 390×844 found the wide tables hiding most of their columns
off-screen (Öğretmenler ve erişim 65%, Denetim geçmişi 70%, the completion summary 55%, Sınıf
raporu 66%, Sınıf tabloları 81%, Arşiv 89%), so status and actions needed sideways swiping. The
assignment board was drag-only, 9,045 px tall, and told phone users to drag from a list "on the
right". Segmented chips, semester switches and icon buttons were under 32 px. The school asked for
the whole site to be easy to use on a phone and chose the patterns below.

## Decision

- One phone threshold for layout: below `md` (768 px, `PHONE_MEDIA_QUERY` in
  `packages/ui/src/hooks/use-is-phone.ts`). Tablets and desktops keep their tables, widths and drag
  unchanged. The teacher grade grid keeps its own earlier 640 px switch to its one-student stepper.
- List tables (teachers, audit history, the completion summary) render as cards on phones
  (`phone-card-list.tsx`): identity and status, then settings, then full-width actions. Every
  action of a desktop row exists on its card.
- Grade tables (class report, archive, class workspace roster) open as one card per student
  (`student-grade-cards.tsx`) with a "Kartlar / Tablo" switch. The choice is kept per browser
  (`flrc-grade-phone-view`), shared by all grade tables and followed across tabs. Table mode on a
  phone pins the identifying columns while the rest scrolls. Roster cards hold only what the
  workspace edits (selection, school number, second language); grades are entered in the teacher
  app, so no empty sütun rows are listed. Students move on phones through the existing selection
  toolbar and confirmation, not by dragging.
- The assignment board on phones collapses each teacher to one row and assigns by tapping: "Sınıf
  ekle" opens a picker of eligible classes whose ticks make the same save as a desktop drop (same
  rules, toasts, Undo and Recent changes). The picker stays open while a save runs.
- Controls that phones tap reach 40 px below `md` (`max-md:` sizes on `Segmented`, small and icon
  `Button`s, `NativeSelect`, the checkbox hit area, the theme toggle); desktop density is unchanged.
- Pages whose form controls differ between the layouts mount only the active one, so no hidden
  duplicate inputs exist. Phone skeletons follow the card layouts (ADR-081).

## Alternatives considered

- Keep tables and pin the first column everywhere: less work, but every list still needs swiping
  to reach status and actions.
- Grade tables as tables only, with pinned names and tighter cells: best for comparing students,
  still sideways swiping; kept as the optional "Tablo" view instead.
- A class-by-class assignment list with dropdowns on phones: simpler, but a different mental model
  from the desktop board.

## Consequences

- Nothing on the listed pages scrolls sideways on a 390 px phone by default; long lists scroll
  vertically instead (the archive of a class with many rating statements is long).
- Pages with a phone card layout carry two renderings; a change to a row's controls must update
  both, which shared per-row render helpers keep in one place.
- E2E specs cover each phone layout at 390×844 alongside the desktop assertions.
