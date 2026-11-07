# ADR-065: Hazırlık classes are grade 0 with named sections

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-09-15  
**Phase:** 2-4 (classes, imports, reports and the demo seed)

## Context

The primary school runs Hazırlık (preparatory) classes in the year before grade 1. They are not
lettered like `1/A`: each carries a name such as Bulut, Yıldız or Güneş, and the names have
different lengths. These pupils receive the same English progress report as grades 1 to 4, and the
school lists the classes before grade 1.

Nothing in the system could hold them. Two check constraints bounded `grade_level` to 1 through 8,
the importer accepted only a digit followed by one letter, admin and import validation uppercased a
section of at most eight characters, and every class label was assembled as `grade/section` in
eleven backend sites and several admin screens.

## Decision

- Store Hazırlık as `grade_level = 0`. Both check constraints and the Pydantic bounds allow 0 to 8,
  and ordering by grade level puts Hazırlık first with no special case.
- A Hazırlık section is a name, spelled in Turkish title case (`Yıldız`), up to 32 characters. A
  numbered grade keeps its uppercase letter. `normalize_section` owns that rule and `class_label`
  renders `Bulut` for grade 0 and `5/A` otherwise; both live in
  `flrc.modules.academics.class_names`, and `@flrc/i18n` carries the same pair for the SPAs.
- The importer reads `Bulut`, `Hazırlık Bulut` or `Hazırlık/Bulut` from a class cell, and split
  "Sınıf" and "Şube" columns compose to the same form. A worksheet title must carry the `Hazırlık`
  prefix (`Hazırlık-Bulut`, hyphenated per ADR-023) so that a sheet called "Students" never turns
  into a class.
- The elementary English report set spans grades 0 to 4. A Hazırlık cover reads "Hazırlık Sınıfı"
  and "Preparatory Class" where a numbered grade would appear.
- Machine keys stay structural. The admin import screens key classes as `0/Bulut` and show
  `classLabel()`; an import preview row carries `original_grade_level` and `original_section` as
  fields, with `original_class` kept as the display label.
- The demo seed adds three Hazırlık classes per year (Bulut, Yıldız, Güneş) so the demo shows them.
- The year rollover does not promote Hazırlık pupils. Which grade-1 section a child joins is a
  placement decision the school makes, so the next year's roster import places them and keeps
  their identity by name (ADR-066).

## Alternatives considered

- A nullable grade level or a separate stage column: every grade-keyed query, ordering rule and
  column scope would need a special case, while 0 is bounded and ordered for free.
- Displaying `Hazırlık/Bulut`: the school calls the class "Bulut"; the prefix would exist only in
  software.
- Accepting bare names in worksheet titles: too easy to turn a sheet called "Liste" into a class.
- Storing a formatted class name: rejected in ADR-021 and still unnecessary.

## Consequences

- Migration `3c7f1a9d2b64` relaxes both constraints. Its downgrade restores the old range and fails
  while Hazırlık rows exist, which is the intended guard against silent data loss.
- The section limit grows from 8 to 32 characters for every grade, and the import preview contract
  gains two fields.
- The assessment programme needs no change: grade 0 is primary, keeps teacher comments and the
  smiley scale, and has no second language.
- Workbook rows and reviewed class moves enforce the same grade-4 minimum for second languages
  as the admin roster forms. A move below grade 4 must also clear the language.
- Hazırlık pupils are absent from the rolled-over year until the roster import places them
  (ADR-066).
- The demo grows to 55 classes and 1,210 pupils per year.

## Supersedes / Superseded by

Extends ADR-021 (slash display names) and ADR-023 (hyphenated worksheet titles) to named classes.
