# ADR-039: One-scroll, always-visible table workspaces

[ADR index](README.md)

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
