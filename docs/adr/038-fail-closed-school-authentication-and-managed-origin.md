# ADR-038: Fail-closed school authentication and managed-origin isolation

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 4.8

## Context

Per-endpoint dependencies, a domain hint, and frontend guards are individually insufficient for
children's school data. A future route can omit a dependency, Google Workspace email addresses can
be reassigned, a managed API origin can bypass gateway controls, and a deployment can accidentally
start with HTTP or placeholder secrets.

## Decision

Include every data router beneath one central `current_user` dependency while retaining the
narrower endpoint role checks. In school mode:

- accept only verified Google identities whose exact `hd` and email domain match;
- require an active pre-created admin allowlist row;
- bind that row on first login to Google's stable `sub` and reject later mismatches;
- use an eight-hour absolute Redis session and a host-only `__Host-` cookie;
- require exact Origin on unsafe requests, explicit trusted hosts, HTTPS, body limits, no-store
  responses, and disabled OpenAPI/docs;
- require a secret header injected by the Cloudflare gateway at every non-health API path;
- refuse application startup when any production invariant is missing or weakened.

The health response and OAuth handshake remain the only public backend surface. Static browser
assets remain public by necessity and contain no school data or credentials.

## Consequences

- A forgotten local dependency on a new data route still fails closed.
- A reassigned email cannot inherit the previous Google identity's access without an explicit
  deactivate/reset/reactivate admin action.
- Direct requests to the managed API origin cannot reach OAuth or data routes.
- Rotating the gateway secret requires coordinated Cloudflare and API deployment.
- There is still no truthful claim of absolute security; provider configuration, MFA, monitoring,
  updates, and incident response remain launch requirements.
