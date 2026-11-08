# ADR-044: Teacher assignments are object-level read and write boundaries

[ADR index](README.md)

**Status:** Superseded by ADR-071

**Date:** 2026-09-04
**Phase:** Security hardening

## Context

The class catalog and grid allowed every authenticated teacher to enumerate every class, student,
school number, subject, and grade. The same broad discovery model let a teacher create an override
grant for a class or subject with which they had no relationship. Auditability recorded misuse but
did not prevent the disclosure or unauthorized grade change.

## Decision

A teacher must hold a teaching assignment for the exact class and subject before the catalog, grid,
save, grant, or undo paths proceed. English `main` and `skills` assignments share the English subject
boundary, so the existing warning and one-hour cross-role collaboration still works within that
class. German and French remain separate subject boundaries. Administrators retain full read/write
authority; coordinators retain school-wide read-only oversight.

## Consequences

- Authenticated teachers cannot enumerate or alter another class, language subject, or academic
  year merely by changing a path/query id.
- Existing same-class English collaboration remains available and audited.
- Missing assignments must be repaired by an administrator instead of being bypassed through an
  override grant.

## Supersedes / Superseded by

Supersedes ADR-025's school-wide teacher discovery decision and narrows ADR-027's collaboration
decision to an already-assigned class and subject. Superseded by ADR-071.
