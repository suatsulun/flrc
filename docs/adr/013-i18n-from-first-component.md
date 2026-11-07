# ADR-013: i18n from first component

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.10 / 2.1 / 4.4

## Context

The app requires Turkish and may require English, German, and French for UI/report contexts. Retrofitting i18n after building the UI would be tedious and error-prone.

## Decision

Use i18next and react-i18next from the beginning. API errors use machine codes, and the frontend
localizes fixed display text. Report column and group labels are localized database records because
administrators can customize them without deploying code.

The deterministic column seed catalog uses stable semantic identifiers for readability, but those
identifiers are not frontend i18n keys and are not persisted as display text. Seeding resolves each
identifier to complete Turkish, English, German, and French values stored in
`ColumnDefinition.labels` or `group_labels`. Turkish remains the required runtime fallback. Seed
translations require review by fluent school staff before production use.

## Alternatives considered

- Hardcoded Turkish strings first, translate later.
- Store report-label translations in `packages/i18n` and persist only a translation key.
- Seed Turkish into all locale fields and postpone every report-label translation until launch.
- react-intl.
- Lingui.

## Consequences

- More setup early.
- UI strings stay disciplined.
- Reports and app chrome can localize separately.
- Schools can change report wording without a frontend deploy.
- Seed identifiers can be renamed without changing persisted label semantics.
- Custom columns may temporarily fall back to Turkish until all locale values are supplied.
