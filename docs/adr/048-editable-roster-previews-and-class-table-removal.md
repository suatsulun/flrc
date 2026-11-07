# ADR-048: Editable roster previews and class-table removal

[ADR index](README.md)

**Status:** Partially superseded by ADR-070 (exclusions and language changes use row keys)

**Date:** 2026-09-08
**Phase:** 2.1, 3.4, 3.8

## Context

Administrators need to add or exclude students and clear German/French selections before importing.
The left grade selector changed only destination buttons, leaving the roster unfiltered. Class
tables exposed student creation and column arrows but lacked removal and direct column placement.

## Decision

Extend ADR-047 with a typed `roster_edits` object containing additions, excluded school numbers, and
language changes. Both preview and commit validate these operations against the reparsed workbook
and the selected year's classes. The review digest binds every operation. Additions cannot overwrite
a differently named enrolled student. Exclusions skip import rows and never delete saved enrollments.
All operations share per-review Zustand undo history; TanStack Query retains reviewed server data.
The left grade selector filters the roster and resets an individual class selection.

A Remove tab in class tables lists both students and assessment columns for the current context.
Removing a student deletes only the selected year's enrollment and language choice after a UI
confirmation, retaining the stable student identity, other enrollments, grade values, and grade audit
entries. The API is admin-only, locks the year, rejects archived years and stale class membership,
and logs only actor/student/class/year IDs. Retained grades are no longer part of that year's active
roster; removal is not erasure of the student record.

Assessment columns can be removed for English, German, and French using the existing
delete-or-disable behavior. Columns with grades stay stored and become inactive. The UI explains
that definitions are shared by all classes of the chosen grade/subject/semester. Native header
dragging saves the complete definition order; left/right arrows remain available. The API rejects
duplicate, incomplete, and mixed-scope reorder requests.

Use one backend programme constant for the Grade 4 start of L2, reconciling the existing seed/workbook
with roster editing's outdated Grade 5 threshold. Clearing a selection is allowed in any grade.

## Consequences

- Preview changes remain reversible until commit and cannot bypass parser or server validation.
- Removing an already enrolled student is a separate, explicit class-table action.
- No schema migration, third-party processor, or new dependency is needed.
- The original workbook is unchanged; selecting it again starts a fresh review.

## Supersedes

ADR-047's restriction of draft operations to class moves only. The paged import roster uses the
page scroll rather than ADR-045's bounded viewport so its sentinel loads rows at the end of the
visible roster. Preview parsing is limited to 60 requests per minute per account, separately from
the unchanged 10-per-minute commit limit; edits and page requests cannot consume the commit budget.
