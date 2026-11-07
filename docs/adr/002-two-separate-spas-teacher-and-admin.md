# ADR-002: Two separate SPAs: teacher and admin

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.1

## Context

Teachers and admins use different workflows. The teacher app must remain fast and low-risk. Admin features are broader, more dangerous, and less frequently used.

## Decision

Build `apps/teacher` and `apps/admin` as separate Vite React SPAs.

## Alternatives considered

- One React app with role-based routes.
- Server-rendered admin pages inside FastAPI.
- One Next.js application.

## Consequences

- Smaller teacher bundle.
- Admin bugs are less likely to break teacher grade entry.
- The two builds can deploy independently even when a gateway composes them under one public
  origin.
- Some layout/auth code must be shared through packages instead of one app tree.
