# ADR-051: Public demo visitors are pseudonymous temporary administrators

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.1 (public demo)

## Context

The public demo must let any Google account, personal or Workspace, try the product as an
administrator, while the school build keeps its fail-closed Workspace-domain, allowlist, and
stable-subject rules (ADR-012, ADR-038). Six NOT NULL foreign keys reference `users` (teaching
assignments, grade `updated_by`, save batches, audit actors, override grants, job requesters), so
a visitor row cannot simply be deleted without destroying audit history. Personal data from
visitors must never accumulate in a shared database that other visitors can browse.

## Decision

A `DEMO_PUBLIC_LOGIN` setting, honoured only when `ENV=demo` and refused at startup anywhere
else, switches the OAuth callback to visitor mode. A verified Google identity becomes an active
admin and coordinator whose email is a random synthetic address in `ALLOWED_GOOGLE_DOMAIN` and
whose name is a generated label. Google's `sub`, email, name, and picture are not stored. A
`demo_visitors` row links the account to an HMAC-SHA256 of the subject keyed by `SESSION_SECRET`,
with an absolute `expires_at` 24 hours after creation.

Repeat logins reuse the account while it has at least one live Redis session; each session's TTL
is capped at the remaining lifetime. Logout ends only that device's session. When the last session
ends, or a login finds an expired or session-less account, the account is scrubbed: sessions
revoked, hash nulled, row deactivated, identity fields replaced by a tombstone. Rows are removed
physically by the demo reset (ADR-052), never by cascading deletes. Visitors cannot modify other
visitor accounts, managed users must still use the configured synthetic domain, and new visitor
accounts are capped per day.

## Alternatives considered

- Store the real email and name for a friendlier UI. Rejected: personal data in a shared,
  browsable database and in provider history.
- Immediate hard delete with cascades through audit tables. Rejected: a demo-only deletion path
  through the school's audit tables.
- Visitor state in Redis only. Rejected: not durable, not covered by the database fixtures, and
  the guardrails would fail open after a cache flush.
- An isolated sandbox per visitor (schema or Neon branch). Rejected: exceeds the free-tier limits
  and adds tenant plumbing the school never needs.

## Consequences

- The demo needs no allowlist row and no bootstrap administrator for visitors; the seeded school
  stays shared.
- School mode is unchanged: the table stays empty, the flag cannot be enabled, and no user is
  ever deleted.
- The 24-hour lifetime is enforced by Redis TTL, so `current_user` gains no extra query.
- A scrubbed tombstone row remains until the nightly reset; it holds no identity data.
- The demo OAuth client's consent screen must be published to production so non-test users may
  sign in.
