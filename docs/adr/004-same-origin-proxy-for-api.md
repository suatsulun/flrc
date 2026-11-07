# ADR-004: Same-origin proxy for `/api/*`

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.10 / deployment

## Context

Cross-site cookies and browser auth flows are easy to misconfigure. The app needs secure sessions without storing tokens in localStorage.

## Decision

The browser calls `/api/*` on the frontend origin. Vercel or Cloudflare Pages proxies those requests to the Render API service.

## Alternatives considered

- SPA calls Render API URL directly.
- JWTs stored in localStorage.
- Full CORS setup with cross-site cookies.

## Consequences

- Cookies are first-party from the browser's point of view.
- `SameSite=Lax` is practical.
- CSRF protection is simpler.
- Frontend environment configuration is smaller.
- Hosting rewrites/functions become part of the deployment contract.
