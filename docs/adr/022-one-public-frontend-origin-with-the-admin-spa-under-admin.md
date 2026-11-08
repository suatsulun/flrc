# ADR-022: One public frontend origin with the admin SPA under `/admin`

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-02
**Phase:** 1.11 / production deployment

## Context

The teacher and admin SPAs were initially exposed on separate production subdomains. Their
host-only `flrc_session` cookies were therefore independent: moving between panels required a
second login, and logging out on one host did not log out the other. Sharing the cookie by setting
`Domain=flrc.suatsulun.com` would solve that symptom by widening the cookie's authority to sibling
and descendant hosts, but it would also widen the session boundary and make cookie deletion and
subdomain trust part of the security contract.

The applications still need separate builds and deployments so an admin-only failure does not
prevent teachers from entering grades.

## Decision

Expose both independently deployed SPAs through one public origin:

```text
https://flrc.suatsulun.com/          teacher SPA
https://flrc.suatsulun.com/admin     admin SPA
https://flrc.suatsulun.com/api/*     FastAPI proxy
```

Attach the public domain to a small gateway deployment. Route `/admin` and `/admin/*` to the admin
deployment, `/api/*` to Render, and all remaining paths to the teacher deployment. Preserve rule
order so API and admin routes are matched before the teacher catch-all.

Keep `flrc_session` host-only: do not set a cookie `Domain`. Configure the admin Vite build and
TanStack Router with `/admin` as their base path. Production uses one exact Google callback URI,
`https://flrc.suatsulun.com/api/auth/callback`.

The teacher SPA owns the only login screen. An unauthenticated request to `/admin` redirects to
`/login`; successful authentication lands on the teacher dashboard, where admins receive the
“Go to admin panel” link. An authenticated non-admin who manually requests `/admin` returns to the
teacher dashboard. The admin SPA has no login route, and OAuth has no admin return target.

Local development may continue to run the teacher and admin Vite servers on ports 5173 and 5174.
The backend retains both configured origins for local Origin checks; in production
`FRONTEND_ORIGIN` and `ADMIN_ORIGIN` are both `https://flrc.suatsulun.com`.

## Alternatives considered

- Keep separate production hosts and require an independent session on each.
- Use `a.flrc.suatsulun.com` and set the session cookie's `Domain` to
  `flrc.suatsulun.com`.
- Merge teacher and admin into one React application.
- Add a dedicated SSO broker that exchanges short-lived one-time codes between hosts.

## Consequences

- Login, refresh, and logout use one host-only browser session across both panels.
- There is one login and error surface to maintain and translate.
- The session cookie is not exposed to every child host under `flrc.suatsulun.com`.
- Teacher and admin remain separate build and deployment units.
- A gateway deployment and ordered path rewrites become production infrastructure.
- The admin app must remain base-path-safe for routes and static assets.
- Both SPAs share an origin, so origin isolation is not a security boundary between them; backend
  role dependencies remain the authorization boundary.
- Preview deployments may still have different hosts and therefore separate preview sessions;
  the shared-session guarantee applies to the public gateway domain.

## Supersedes / Superseded by

This replaces the separate-production-subdomain topology previously described by ADR-002's
deployment consequence. It does not replace the decision to keep two SPAs or ADR-004's
same-origin `/api/*` proxy.
