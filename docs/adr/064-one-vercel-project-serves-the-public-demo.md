# ADR-064: One Vercel project serves the public demo

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-11

**Phase:** 1.11 / demo hosting

## Context

The demo ran as three Vercel projects: one per SPA and a gateway that owned the public domain and
rewrote `/admin*` and `/` to the two `*.vercel.app` deployments and `/api/*` to Render. Every
browser request crossed two Vercel deployments, the two panels could be on different commits, the
panel cross-links lived in per-project environment variables, and an empty trailing segment in the
gateway rewrite answered 404 for `/admin/`. The school image (ADR-054, ADR-055) already serves both
builds from one Caddy container, so the demo was the only profile with a separate routing layer.

## Decision

Serve the demo from one Vercel project rooted at `infra/vercel`. The workspace package
`@flrc/demo-web` depends on both apps, so Turborepo builds them first; its own build assembles the
teacher output at the site root and the admin output under `admin/`, checks that the admin build
keeps `/admin/` as its asset base, and refuses a bundle that links to a Vite development port. The
project's `vercel.json` sets `trailingSlash: false`, rewrites `/api/:path*` to the Render API, and
falls back to the two `index.html` files for client routes. Production builds default the panel
cross-links to `/admin/` and `/`; `VITE_ADMIN_URL` (a URL or path) and `VITE_TEACHER_URL` (an
origin or path resolved against the current origin) remain as overrides for layouts that serve the panels from
different origins, such as the two-port CI preview. The school web image drops its build arguments
for them, which also fixes its admin build joining `/` and `/login` into a protocol-relative URL.
The per-app
`vercel.json` files and `infra/vercel-gateway` are removed. The `js` CI job builds the same package,
so the assembled layout is checked on every pull request.

## Alternatives considered

- Keep three projects and only fix the trailing-slash rewrite: leaves the double hop, the deploy
  skew, and the environment-variable cross-links.
- A root `vercel.json` with the repository as the root directory: works, but puts hosting
  configuration at the repository root and needs a shell build step; a workspace package keeps it
  under `infra/` and reuses Turborepo ordering.
- Merge the two SPAs into one application: rejected in ADR-022 and unchanged here; they stay
  separate builds.
- Serve the demo from the `flrc-web` image on Render: possible, but a static host is free and the
  image is the school profile's concern.

## Consequences

- One deploy per commit contains both panels; teacher and admin cannot drift apart.
- One hop per request; the `*.vercel.app` targets disappear from configuration.
- The demo and the school image share one path layout, so the ADR-022 routing rules exist in one
  configuration per profile.
- Each deploy builds both apps, roughly twice the previous build time; one preview URL covers both
  panels.
- A broken admin build fails the whole deploy before anything goes live, which is stricter than a
  partial update.
- The public domain must move to the new project and the three old projects must be deleted; until
  then the demo keeps serving the previous layout.

## Supersedes / Superseded by

Amends ADR-022: the two SPAs remain separate builds and the public routing rules are unchanged, but
on the demo they form one deployment unit instead of two deployments behind a gateway. Supersedes
the three-project assembly in handbook Step 1.11.4.
