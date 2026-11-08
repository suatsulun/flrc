# ADR-069: Read class-per-sheet roster exports as schools produce them

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-10-19

**Phase:** 4.8 / roster import

## Context

A real school export uses one worksheet per class. It has a merged title row, wrapped headers
such as `OKUL\nNO`, an abbreviated second-language header `2.Y.D.` with values `ALM.` and
`FR.`, and "Kız", "Erkek" and "Toplam" summary rows below each class. Hazırlık sheets are titled
with the bare class name. With every class on its own sheet, a school can exceed fifty sheets.
The importer rejected the workbook at 32 sheets, and missed the wrapped header, the language
abbreviations and two of the summary rows.

## Decision

- Allow up to 100 worksheets. The archive, row and column bounds are unchanged.
- Match headers with whitespace and full stops ignored, and accept `2. Y.D.` as the
  second-language header. Accept `ALM`/`FRA` (with or without a full stop) as German/French.
- A row with neither a school number nor a text name is not a student row, so summary rows are
  skipped whatever their label. A row with a name but no valid number is still an error.
- In a workbook where at least one worksheet title names a class (`5-A`, `Hazırlık-Bulut`), a bare
  title such as `Güneş` names a Hazırlık class. This narrows ADR-065, which required the prefix
  for every title. A workbook with no class-titled sheet still requires it, so a lone "Liste"
  sheet never becomes a class. A class column, where present, always overrides the title.

## Alternatives considered

- Asking schools to rename sheets and headers: the export comes from the school's own system and
  is re-exported every year.
- Substring footer words such as "kız": these also occur inside real surnames.

## Consequences

The school's export imports without editing. In a class-per-sheet workbook, an unrelated sheet
that has a student table but no class column becomes a Hazırlık class named after the sheet. The
import preview lists every class before commit, so this is visible and can be corrected.

## Supersedes / Superseded by

Narrows ADR-065 (worksheet titles).
