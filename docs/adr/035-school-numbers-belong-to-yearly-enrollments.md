# ADR-035: School numbers belong to yearly enrollments

[ADR index](README.md)

**Status:** Partially superseded by ADR-070 (numbers are unique per year and school stage)

**Date:** 2026-08-20
**Phase:** 3.x

## Context

`students.school_number` was globally unique. That modeled a reusable administrative number as if
it were a permanent identity: student 200 in 2026-2027 prevented a different student from receiving
200 in 2030-2031, and changing a continuing student's number would rewrite what archive screens
showed for earlier years.

## Decision

`students.id` is the permanent person identity. `enrollments.school_number` is the number for one
academic year, unique on `(year_id, school_number)`. A setup-year enrollment may temporarily have no
number; activation fails until every enrollment has one. All grids, reports, exports, searches, and
archive views resolve the number through the enrollment for the displayed year.

## Alternatives considered

- Keep a non-unique last-known number on `students`: easy to misuse and wrong for archives.
- Create a separate number-history table: it duplicates the year link already owned by enrollment.
- Encode the year into the number: it changes the school's actual identifier and its printed form.

## Consequences

- A number can be reused safely in different years without an archive conflict.
- One student can keep the same identity while receiving a different number each year.
- Import matches a promoted, numberless enrollment by normalized name before creating a new person.
- Downgrading to the old schema cannot represent reused numbers and therefore restores deterministic
  unique ids rather than pretending the old model can preserve the new meaning.
