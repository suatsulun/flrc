# ADR-012: Google OAuth plus explicit allowlist

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.7 / 3.2

## Context

The school already has Google Workspace accounts. The app should not store passwords. Domain membership alone is not a full authorization policy.

## Decision

Use Google OAuth/OIDC for identity, verify the hosted-domain claim, then require a matching active teacher allowlist entry.

## Alternatives considered

- Email/password accounts.
- Google OAuth domain only.
- Magic links.
- External auth provider such as Auth0/Firebase/Clerk.

## Consequences

- No password storage.
- Admins can deactivate specific teachers.
- Production needs a school-owned OAuth client.
- Demo and school OAuth clients must remain separate.
