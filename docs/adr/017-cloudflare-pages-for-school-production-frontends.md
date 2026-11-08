# ADR-017: Cloudflare Pages for school production frontends

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 4.10

## Context

The school production deployment should be stable, cheap, and compatible with static SPA hosting plus `/api` proxying. Vercel Hobby is suitable for personal demo use but not the cleanest school production story.

## Decision

Use Cloudflare Pages for school production frontends. Use Vercel only for the demo if desired.

## Alternatives considered

- Vercel for production.
- Render static sites.
- Self-hosted frontend server.
- One FastAPI server serving static assets.

## Consequences

- Production frontend hosting is free/static and school-appropriate.
- Pages Functions may be needed for `/api/*` proxying.
- Deployment introduces another platform to learn.
