# ADR-052: The demo resets nightly by restoring a Neon branch from its golden parent

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.2 (public demo)

## Context

Every visitor is an administrator of one shared fictional school (ADR-051), so edits, vandalism,
and tombstoned visitor rows accumulate until something removes them. The demo runs on free
hosting: Render has no cron and sleeps after 15 minutes, Neon Free allows 0.5 GB and a 1 GB-month
change history, and reseeding the 42 MB school inside the application would take minutes over the
network every night.

## Decision

The demo database is a Neon child branch of a pristine, seeded parent. A reset calls Neon's branch
restore with the parent as source, which replaces data and schema in seconds while the branch id,
compute, and connection string stay the same. The API then disposes its connection pool, flushes
every session, visitor tally, and rate-limit key from Redis, and records the local reset date in
Redis, the one store the restore does not overwrite.

The day boundary is midnight in `DEMO_RESET_TIMEZONE` (Europe/Istanbul). A GitHub Actions
schedule requests the reset at that time through `POST /api/ops/demo/reset`, authenticated by
`X-Ops-Token`, and polls `GET /api/ops/demo/status` until the day's reset is recorded.
Independently, the API runs a self-heal loop: at startup and every minute it compares the recorded
date with today and runs a catch-up reset when they differ, so a delayed workflow, an auto-disabled
schedule, or a sleeping instance never leaves yesterday's edits in place. A Redis lock makes resets
single-flight, and a state key makes data routes answer `503 demo_resetting` while the branch is
being replaced. Public `GET /api/demo` lets the login page describe the demo and its next reset
before sign-in; `/api/me` carries the visitor's expiry and the next reset for the in-app banner,
which turns into a warning in the last fifteen minutes.

At startup the demo image migrates and, if empty, seeds the golden parent before migrating its own
branch, so a release can never be reverted by the next reset. The seed creates a synthetic
administrator when none exists, because a visitor-only demo has no allowlisted person.
`DEMO_PUBLIC_LOGIN` refuses to start unless the reset is configured. The OpenAPI export runs under
the demo profile so the generated client documents the demo-only routes.

## Alternatives considered

- In-app truncate and reseed: provider-neutral, but minutes of downtime per night and a full
  rewrite of the dataset into Neon's change history.
- Restore a golden `pg_dump`: a second copy of the fixture to keep in sync, and slower than a
  branch restore.
- A per-request marker check instead of a loop: one Redis round trip on every request for a
  condition that changes once a day.
- Preserve visitor accounts across the reset: more code for no visible benefit; accounts die at
  midnight and the 24-hour rule becomes automatic.

## Consequences

- A reset takes seconds; visitors see a 503 for that moment and are then signed out.
- The path is Neon-specific. The school build never uses it, and another demo host would need a
  different implementation behind the same ops routes.
- Operators create the child branch and set `NEON_*`, `OPS_TOKEN`, `DATABASE_URL_GOLDEN_DIRECT`,
  and the `DEMO_OPS_TOKEN` GitHub secret; [operations/public-demo.md](../operations/public-demo.md)
  is the runbook.
- The demo OAuth consent screen must be published to production before `DEMO_PUBLIC_LOGIN` is
  turned on.
