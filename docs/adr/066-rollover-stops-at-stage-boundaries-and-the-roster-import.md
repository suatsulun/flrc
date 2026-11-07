# ADR-066: Rollover stops at stage boundaries and the roster import places pupils by name

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-09-15  
**Phase:** 3.x (lifecycle) and imports

## Context

ADR-036 promotes every grade 1 to 7 pupil into next year's class with the same section letter. The
school does not work that way at its two stage entries. Pupils leaving Hazırlık (ADR-065) and pupils
leaving grade 4 are placed into grade 1 and grade 5 sections by the school, together with the new
pupils who join at those points, so a child's section last year says nothing about next year.

If the rollover simply left those pupils out, the next roster import would find no enrollment for
them and create a new person for each row, splitting one child's history across two identities.

## Decision

- `carries_over(grade_level)` in `academics/programme.py` decides who moves automatically: grades
  1 to 3 and 5 to 7 keep their section, Hazırlık (grade 0) and grade 4 wait for placement, and grade
  8 graduates. The rollover enrolls only pupils who carry over.
- The roster import treats last year's pupils from a placement grade who have no enrollment in the
  target year as awaiting placement. A row that matches none of the year's school numbers or
  numberless enrollments, but matches exactly one awaiting pupil by normalised name, reuses that
  identity. The preview shows the row as `placed` plus `new_enrollment`, counts it under
  `placed_students`, and the commit creates the enrollment on the existing student. Two awaiting
  pupils with the same name match nothing and become new students, the rule ADR-041 already applies
  to numberless enrollments.
- Only the year immediately before the target year feeds the pool. That is the year the rollover
  came from, so graduates and pupils who left in other grades are never matched.

### Review clarification (2026-09-15)

Both preview and commit use the same identity matcher. A placement candidate must come from the
exact preceding calendar year and the corresponding stage: Hazırlık to grade 1, or grade 4 to
grade 5. A missing preceding year produces no candidates; a nonstandard year label disables
automatic placement matching.

Name matching must be unique on both sides: the existing candidates and the unmatched workbook
rows. Two incoming namesakes are new identities, rather than giving the first row an existing
pupil's history. This also tightens ADR-041's numberless-enrollment matching. Existing school
numbers still take precedence. Candidate lookup remains bounded to two queries per matching pass.

## Alternatives considered

- Keep promoting 4 to 5 by section letter and let the admin move pupils afterwards: every grade-5
  class would start wrong, and the new pupils would still arrive through the import.
- Enroll placement pupils without a class: `enrollments.class_id` is not nullable and every screen
  assumes a class, so a holding class would leak into reports and the assignment matrix.
- Match awaiting pupils across all earlier years: a graduate's namesake could inherit an
  identity.

## Consequences

- After a year closes, Hazırlık and grade 4 pupils are absent from the new year until the roster
  import runs. The activation guard for missing numbers is unaffected, since they have no enrollment.
- Identity and history stay whole across both stage boundaries, and the admin can filter the
  `placed` rows in the review before committing.
- The lifecycle page and the docs describe the two waiting cohorts.

## Supersedes / Superseded by

Supersedes in part ADR-036 (promotion scope) and ADR-065 (which had left Hazırlık pupils to arrive as
new pupils).
