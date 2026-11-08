# ADR-076: Field names can be edited after creation

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** 2.x (grid and columns) maintenance

## Context

ADR-072 made a field's name its subject-language label and kept names fixed after creation, so a
typo meant deleting the field, which is impossible without losing its place once grades exist.

## Decision

- `PATCH /api/columns/{id}` accepts an optional `name`, stripped and non-empty like
  `ColumnCreate.name`. It is stored under the field's subject language (`SUBJECT_LOCALE`); the
  Turkish wording, group names and other labels stay as created.
- The same rule as other column edits applies (`editable_semester`): the open semester of the
  active year or any semester of a setup year; locked semesters and archived years answer
  `409 semester_locked`.
- Grades stay attached because they reference the field id. A rename is recorded as
  `field.edit` and can be undone (ADR-075).

## Alternatives considered

- Rename every stored label: the Turkish wording printed on bilingual cards would follow a name
  typed in another language.
- Keep names fixed: a typo stays on every printed card for the year.

## Consequences

Printed cards show the new name from the next generated PDF. Changing a type that needs Turkish
wording still requires recreating the field with it.

## Supersedes / Superseded by

Supersedes ADR-072's "Names cannot be edited after creation" bullet; its Turkish-wording checks
for type changes and copies remain.
