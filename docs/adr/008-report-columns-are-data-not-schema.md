# ADR-008: Report columns are data, not schema

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 2.1

## Context

Schools may need different report-card columns by year, subject, language, or term. Changing SQL schema for each report-card adjustment would be brittle.

## Decision

Store report columns as data. The implemented table is named `column_definitions`; the earlier
design called it `report_columns`. The grid and reports render from those definitions.

## Alternatives considered

- Hardcoded columns in frontend.
- SQL column per report-card field.
- JSON blob per student.

## Consequences

- Admins can configure columns without migrations.
- The frontend can render typed cells from server-provided definitions.
- The backend must validate values against column definitions on every save.
- Report generation must respect column ordering and localization.
