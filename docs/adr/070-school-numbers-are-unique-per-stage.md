# ADR-070: School numbers are unique per stage

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-10-19  
**Phase:** 3.x (rosters and lifecycle) and imports

## Context

ADR-035 made a school number unique within one academic year. Schools number their primary pupils
(Hazırlık to grade 4) and their middle-school pupils (grades 5 to 8) independently, so a grade 4
pupil and a grade 5 pupil can legitimately hold the same number in the same year. The year-wide
constraint rejected such a roster: the parser reported `duplicate_conflict`, identity matching keyed
on the number alone could attach a primary row to a middle-school pupil, and import review edits
addressed workbook rows by number only.

## Decision

- `stage_for_grade` in `academics/programme.py` is the single grade-to-stage rule: grades 0 to 4
  are `primary` and grades 5 to 8 are `middle`, from `MIDDLE_START_GRADE`.
- `enrollments.stage` is derived by database triggers from the enrollment's class on insert, on a
  class change, and when a class's grade crosses the 4/5 boundary; application writes cannot set
  it. The named constraint `uq_enrollments_year_id_stage_school_number` replaces the
  `(year_id, school_number)` constraint. Positive numbers, numberless setup enrollments and the
  activation guard are unchanged.
- Manual creation and number edits, roster moves and class grade edits reject a number already
  held in the target year and stage with `409 duplicate_school_number`. A move or class edit that
  would carry a pupil onto a taken number in the other stage is refused as a whole; nobody is
  renumbered. Constraint violations from concurrent writes are reported the same way.
- The roster import identifies every row by `row_key`, `<stage>:<number>` of the class the row
  came from. The parser compares duplicates by row key, so `duplicate_identical` and
  `duplicate_conflict` apply only within one stage. Existing enrollments match by stage and
  number, so a number held in the other stage never suppresses a name placement (ADR-066).
- Review class moves and language changes name a `row_key`; exclusions are `removed_row_keys`.
  Number-only edits are rejected. A move never changes the row key, even across stages, so later
  edits in the same review address the moved row by its source key. Manual additions keep
  `school_number` plus their class, and derive their row key from that class. The review digest
  and preview pages order rows by stage, then number (`middle` before `primary`).
- After all edits, two rows holding one number in the same stage, or a row landing on a number
  that a different enrolled pupil holds in that stage, fail both preview and commit with
  `409 duplicate_school_number`; nothing is written.
- Rollover still assigns fresh sequential numbers, now counting from 1 in each stage. Demo seed
  numbering is unchanged, because year-wide distinct numbers remain valid.
- The year workbook's Grades and Audit sheets export `stage` beside `school_number`, so an
  exported number stays unambiguous without the class.

## Alternatives considered

- Keep year-wide uniqueness and ask the school to renumber: the numbers are the school's own
  identifiers and appear on its documents.
- Set the stage only when inserting an enrollment: class moves and class grade edits would leave it
  stale, and a unique constraint cannot join to `school_classes`.
- Address review rows by destination stage and number: a cross-stage move would turn one pupil's
  row into another pupil's identity.
- Re-match a row by its destination number when its source key finds nobody: this silently
  attaches a row to a different pupil, and persistent row lineage across imports is a separate
  feature.

## Consequences

- A primary and a middle-school pupil may share a number within one year; a number search can
  return both. A number alone no longer identifies a pupil within a year; identify a pupil by
  student id, or by number together with its stage or class.
- Import review clients send row keys; the generated API client changes with the contract.
- A row key identifies a workbook row only within one review. Once a cross-stage move is committed,
  replaying it with the same file returns `duplicate_school_number`, and the file row without the
  move would import as a different pupil. Correct the class in the workbook before importing it
  again.
- A schema downgrade fails while two pupils of different stages share a number in one year,
  rather than renumbering anyone.

## Supersedes / Superseded by

Partially supersedes ADR-035 (uniqueness scope), ADR-041 (one rollover number sequence), ADR-047
(move identity) and ADR-048 (exclusion and language-change identity).
