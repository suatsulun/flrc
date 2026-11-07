# ADR-047: Paged import review with validated class moves

[ADR index](README.md)

**Status:** Partially superseded by ADR-070 (review moves address rows by stage-scoped row key)

**Date:** 2026-09-08
**Phase:** 3.8

## Context

The import committed the full workbook but displayed only its first 100 students. Administrators
could not inspect later classes or correct class placement before finalizing the import.

## Decision

The stateless dry-run endpoint accepts bounded offset pages and searches/filters the full parsed
roster before slicing. It returns full-workbook counts, matching row counts, a next offset, and class
counts. Scrolling loads the next page; filters never narrow the committed import.

Admins can stage class moves using drag-and-drop or a row's class selector. Each move must reference
a school number in the original file and a class in that file or the selected year. Both endpoints
validate the same override list; names, identities, and languages remain owned by the parser. A
review digest binds the original file hash, year, and sorted moves. Commit rejects stale or missing
review digests when moves exist. Existing file-only clients remain compatible.

TanStack Query owns reviewed pages. A per-review Zustand store owns unsaved moves and undo history.
Changing the file/year discards that draft. Commit success replaces the editor with a result and
invalidates the affected server caches. Errors retain the draft for review and retry.

## Consequences

- All students can be reviewed without rendering the entire school at once.
- Class changes remain preview-only until one transactional commit.
- Each page/filter request resends and reparses the bounded workbook; no server-side upload cache,
  new processor, persistent draft, or schema migration is introduced.
