# ADR-045: Contained table viewports preserve readable columns

[ADR index](README.md)

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
