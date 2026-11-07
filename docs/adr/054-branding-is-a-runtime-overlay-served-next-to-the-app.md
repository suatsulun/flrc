# ADR-054: Branding is a runtime overlay served next to the app

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.3 (public release)

## Context

ADR-034 compiled the school's name and logo into the web builds through `pnpm brand`, which was
right while every deployment was built from a checkout. ADR-053 ships prebuilt generic images, so
a school can no longer rebuild to rebrand, and ADR-040 removed the palette's dependency on the
accent colour, which leaves only the name, logo, favicon, and title as deployment-specific.

## Decision

Each web app serves a `branding/` folder: a blocking `brand.js` that sets `window.__FLRC_BRAND__`
before the app starts, plus `logo.svg` and `favicon.svg`. `@flrc/branding` prefers that runtime
object and falls back to the bundled generic values; `index.html` loads the script and favicon
from that folder, so the admin app resolves them under `/admin/`. `pnpm brand` still generates the
generic folder, the report assets, and the derived HTML, so the demo and a fresh clone stay
consistent and `pnpm brand:check` keeps guarding drift.

The `flrc-web` image serves `/branding/*` and `/admin/branding/*` from a mounted folder with the
generic files as fallback. The API reads `brand.json` and `logo.svg` from `SCHOOL_BRANDING_DIR`,
the same mounted folder, below the explicit `SCHOOL_NAME` and `SCHOOL_LOGO_PATH` overrides and
above the synced assets.

## Alternatives considered

- Keep build-time branding and build per school: rejected with ADR-053's delivery model.
- Fetch a JSON file at runtime from the app: a request before the first render and a visible
  flash of the generic name; a blocking script sets the identity before paint.
- Inline the brand into `index.html` at deploy time: it requires rewriting a built artifact and a
  CSP hash for inline script.

## Consequences

- A school rebrands by replacing three files in one folder; no build, no image change.
- `brand.js` is a five-line contract documented in `branding/README.md`.
- The demo and the school share one code path, so the overlay is exercised on every visit.

## Supersedes / Superseded by

Supersedes ADR-034's compiled-in name and logo. ADR-034's single source folder, `pnpm brand`, and
drift check remain.
