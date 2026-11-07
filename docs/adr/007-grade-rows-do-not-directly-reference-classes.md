# ADR-007: Grade rows do not directly reference classes

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.5 / 2.6

## Context

Students can move classes. Historical report values should remain tied to the student/year/column context without becoming inconsistent when class membership changes.

## Decision

Represent class membership through `enrollments`. Grade values do not store a direct `class_id` as their core identity.

## Alternatives considered

- Store `class_id` on every grade value.
- Store one grade table per class.
- Snapshot full class context into every grade row.

## Consequences

- Class moves do not corrupt grade identity.
- Queries must join through enrollment/year context where class filtering is needed.
- The data model separates historical membership from cell values.
