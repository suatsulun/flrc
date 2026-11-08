# ADR-020: PostgreSQL 18 baseline

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.4

## Context

The handbook originally pinned PostgreSQL 17. PostgreSQL 18 is now the current supported major,
the official `postgres:18-alpine` image is available, and Neon supports PostgreSQL 18 projects.
The project has no durable development data or applied migrations yet, so changing the baseline
now avoids a later major-version migration.

PostgreSQL 18's official container changed its data-directory layout: its version-specific
`PGDATA` lives below `/var/lib/postgresql`, unlike PostgreSQL 17 and earlier images that commonly
mounted `/var/lib/postgresql/data`.

References: [PostgreSQL version policy](https://www.postgresql.org/support/versioning/),
[official PostgreSQL container](https://hub.docker.com/_/postgres/), and
[Neon PostgreSQL 18 support](https://neon.com/docs/changelog/2026-02-27).

## Decision

Use PostgreSQL 18 for local development, CI, managed deployment, and the school-hosted profile.
Use the `postgres:18-alpine` major tag for development so compatible minor security and bug-fix
releases are received. Mount the named database volume at `/var/lib/postgresql`.

## Alternatives considered

- Keep PostgreSQL 17 until its end-of-life.
- Use PostgreSQL 18 locally but leave managed and CI environments on 17.
- Pin a complete PostgreSQL 18 minor and Alpine patch tag.

## Consequences

- Local, CI, Neon, and self-hosted database majors should remain aligned.
- Existing PostgreSQL 17 Docker volumes cannot be reused directly; disposable development volumes
  are recreated, while any future real upgrade requires `pg_dump`/`pg_restore` or `pg_upgrade`.
- Production changes must continue to use Alembic migrations regardless of database major.
- Minor releases can advance under the `postgres:18-alpine` development tag without silently
  crossing another major version.
