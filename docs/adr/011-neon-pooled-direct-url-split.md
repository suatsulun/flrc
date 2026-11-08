# ADR-011: Neon pooled/direct URL split

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.5 and deployment

## Context

Neon provides pooled and direct connection URLs. Transaction poolers are useful for app traffic but problematic for DDL and some migration operations.

## Decision

Use the pooled URL for normal app connections and the direct URL for Alembic migrations, backups, and restore operations.

## Alternatives considered

- Use pooled URL everywhere.
- Use direct URL everywhere.
- Host Postgres manually.

## Consequences

- Migrations are more reliable.
- App traffic benefits from pooling.
- Configuration has two database URLs that must not be confused.
