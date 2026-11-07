# ADR-031: Keyboard-first grade grid

[ADR index](README.md)

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
shows the unsaved count, the keyboard hints, and Save. Movement does its own scrolling, because the
browser reveals a focused cell only at the window edges: a cell even partly behind the frozen header
or the bar jumps to the middle of the rows between them.

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
