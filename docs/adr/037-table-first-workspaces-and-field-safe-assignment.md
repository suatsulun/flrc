# ADR-037: Table-first workspaces and field-safe assignment

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 2.x-3.x

**Superseded in part by:** ADR-041 (English school-stage ownership), ADR-079 (the admin panel opens
on a dashboard)

## Context

The grade grid is the daily product, but both apps opened on navigation-heavy dashboards. Admin work
split one class across roster, columns, assignments, students, and lifecycle pages. This imposed too
many concepts and clicks on occasional computer users.

## Decision

Both apps open on a table. The teacher grid keeps year/semester, grade, subject, and browser-like
class tabs visible above the cells. The admin class table combines roster numbers, second languages,
column creation/reordering/ownership, class-level teacher assignment, and an add-student row. A
student can be dragged between same-grade class tabs; their stable identity keeps all grade and note
records connected.

Teachers have one persisted `teaching_field`: English, German, or French. English teachers are
eligible for Main and Skills; German and French teachers are eligible only for the matching role.
Both API assignment paths enforce this rule. The assignment page is a teacher-centered drag board;
the same assignments remain editable inline on each class table.

The UI uses native drag events and existing React primitives. No grid or drag dependency is added.

## Consequences

- The core table is visible without navigating through class cards.
- Most yearly administration happens in one mental model and one screen.
- Same-grade moves preserve grades and notes because values belong to stable students and semester
  column definitions, not to a transient class row.
- Assignment mistakes are rejected server-side even if a client bypasses UI filtering.
