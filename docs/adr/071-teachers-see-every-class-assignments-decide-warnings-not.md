# ADR-071: Teachers see every class; assignments decide warnings, not access

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-10-20  
**Phase:** 2.x (grid) maintenance

## Context

ADR-044 made teaching assignments a read and write boundary. In practice the school hands out
assignments gradually, covers absent colleagues, and expects any teacher to look at and help with
any class. Teachers without a complete set of assignments saw an empty or partial dashboard, and an
administrator had to act as a data-entry proxy for every missing link.

## Decision

- Every authenticated teacher lists every academic year and receives the full class catalog for
  the selected year: each class and subject that has active columns. `can_write` and `my_roles`
  still mark the teacher's own assignments, and the sidebar lists only those.
- Grid reads, saves, grant requests and undo no longer require a teaching assignment for the class
  or subject.
- Writes keep ADR-027's ownership warning. A save that touches a column whose role is not assigned
  to the teacher is rejected with `outside_assignment_confirmation_required` unless the request sets
  `confirm_outside_assignment`; the confirmed save records a one-hour override grant and links each
  audit entry to it. Semester locks, validation, optimistic concurrency and attribution are
  unchanged.
- Administrative, archive, coordinator, export and audit routes keep their role checks.

## Alternatives considered

- Keep ADR-044 and require complete assignments before term start: blocks cover and late
  assignment, which the school does not want.
- Allow school-wide reads but keep writes assignment-bound: teachers could not help with another
  class without an administrator.

## Consequences

- Any authenticated teacher can read every pupil's names, school numbers and grades, and can change
  any grade after confirming the warning. The audit trail, not the API, is the control against
  misuse.
- Missing assignments no longer hide classes; they only remove the "my assignments" shortcut and
  turn every save in that class into a confirmed out-of-assignment save.

## Supersedes / Superseded by

Supersedes ADR-044. Restores ADR-025's school-wide discovery with ADR-027's confirmation flow.
