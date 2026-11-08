# ADR-006: Synthetic demo data only

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.6 and all demos

## Context

The project handles children's school data. Real data in source control, demos, tests, logs, or screenshots would be unacceptable.

## Decision

Use deterministic `Faker(tr_TR)` seed data for all demos, tests, and screenshots. Never commit real student or teacher data.

## Alternatives considered

- Anonymized real data.
- Small hand-written examples based on real rosters.
- No demo data.

## Consequences

- Portfolio screenshots are safe.
- Tests are reproducible.
- Some fake data may not match every real school edge case.
- Importer fixtures must also be synthetic.
