# ADR-005: Server-side sessions over JWTs

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.7

## Context

The school must be able to revoke a teacher's access immediately. Browser-stored tokens increase theft risk and make logout/revocation harder.

## Decision

Use server-side sessions. The browser stores only a signed `HttpOnly` session id cookie. Session
data lives in Redis with an absolute TTL of at most eight hours.

## Alternatives considered

- JWT access tokens in localStorage.
- JWTs in cookies.
- Third-party auth session provider.

## Consequences

- Departed teachers can be revoked by deleting Redis sessions.
- The browser never sees OAuth tokens.
- Redis availability matters for active sessions.
- Session middleware and CSRF checks must be implemented carefully.
