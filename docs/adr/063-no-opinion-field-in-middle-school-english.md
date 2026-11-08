# ADR-063: No opinion field in middle-school English

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-11

**Phase:** 2.1.3, 2.4 and 4.2

The developer confirmed that grades 5-8 English must not include a teacher opinion field.
This restores the handbook's original middle-school English programme and supersedes that
part of ADR-060. Primary English and German/French retain their comments.

Remove the middle-school English default text column and reject its creation or conversion
through the columns API. Copy and rollover use the same programme rule. A new migration
deactivates existing middle-school English text definitions, including synthetic archive years,
without deleting definitions, values, versions or audit records. Grids, report generation and
archive/history views omit the retired opinion fields; audit and workbook exports retain the
underlying historical data. Existing downloaded PDFs remain unchanged.

The teacher grid has no notes filter for this programme and reserves space for the final
angled score heading. Admin forms do not offer text columns for middle-school English.
Tests cover creation, copying, migration idempotence, retained values and absence from reports.
