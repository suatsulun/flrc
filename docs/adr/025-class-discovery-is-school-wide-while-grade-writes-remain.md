# ADR-025: Class discovery is school-wide while grade writes remain ownership-aware

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 2.1-2.7

## Context

An assignment-only teacher dashboard hid most of the school and exposed invalid seeded role links,
such as a primary French assignment where no French grid exists. Teachers need to review any active
class, while accidental edits outside their responsibility must remain visible, deliberate, and
auditable.

## Decision

Every authenticated teacher receives an active-year class catalog derived from configured column
definitions and real roster membership rather than from their assignments alone. The catalog marks
the teacher's own responsibilities but permits navigation to every valid class and subject grid.

Non-owned cells accept local drafts. Saving those drafts requires an explicit ownership warning. A
teacher receives the existing one-hour audited override grant before the save; an administrator must
explicitly confirm use of administrator authority. The API continues to reject unowned writes that
have neither assignment, active grant, nor administrator authority.

## Consequences

- Teachers can review the complete active school without false empty-class links.
- Assignment ownership remains visible without becoming a read-access boundary.
- Cross-assignment saves are deliberate and remain attributable in the audit trail.
- The class catalog reports only class/subject combinations that have active columns.
