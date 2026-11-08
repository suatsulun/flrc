# ADR-034: A single root `branding/` folder, applied by `pnpm brand`

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

ADR-033 made branding configuration rather than code, but it left four separate
swap points across three packages: two `public/school-logo.svg` files, a
`VITE_SCHOOL_NAME` build variable, a logo inside the reports package, and a
`SCHOOL_NAME` backend variable. Rebranding meant remembering all four, and
forgetting one produced a half-branded product, the worst possible state in which
to show a prospective school. Nothing made a partial rebrand visible.

## Decision

One folder at the repository root, `branding/`, holds `brand.json` (name, short
name, accent colour) and `logo.svg`, plus an optional `favicon.svg`. It is also a
workspace package, `@flrc/branding`, so the web apps import the name and the logo
directly: the bundler fingerprints the logo and resolves it correctly under the
admin app's `/admin/` base, and there is no copy to drift.

`pnpm brand` (`scripts/branding.mjs`) feeds the three kinds of consumer that
cannot import a module: `index.html`, the CSS palette, and the Python backend
(whose Docker image only copies `src/`). Its output is committed so a fresh clone
works untouched, `predev`/`prebuild` run it automatically, and `pnpm brand:check`
fails CI when a derived file has drifted.

The palette is derived from the **hue** of `accentColor` only. `theme.css` reads
`--brand-hue` and keeps the lightness and chroma that were checked for contrast,
so any school colour still yields white-on-primary above 4.5:1. Status colours
(success, warning, destructive) deliberately do not rotate: they carry meaning,
not brand.

Environment variables survive as per-deployment overrides for the multi-school
case; for a single school they stay unset.

## Alternatives considered

- Keep the four swap points and document them: documentation does not stop a
  partial rebrand reaching production.
- Have the backend read the repo-root folder at runtime: the Docker build context
  is `apps/backend`, so the root folder is not in the image. Changing the build
  context to fix a branding concern is the wrong trade.
- Derive the palette from the school's exact colour: this cannot guarantee
  readable button labels for a pale or very dark brand colour.
- Generate a TypeScript module for the name: unnecessary once `branding/` is a
  workspace package that can be imported directly.

## Consequences

- A full rebrand is: replace `logo.svg`, edit `brand.json`, run `pnpm brand`.
- `pnpm brand` prints the derived hue, the resulting primary, and its contrast
  ratio, so the result is inspectable without opening the app.
- A school's exact corporate colour is matched by hue, not reproduced exactly.
  That is a deliberate accessibility trade, documented in `branding/README.md`.
- Derived files are committed, so a rebrand is a reviewable diff, but they must
  never be hand-edited.
- The front-end name and logo are compiled in, so several schools need several
  builds.

## Supersedes / Superseded by

Supersedes ADR-033. Extends ADR-029 (the token system) and ADR-032 (the report
template), both of which now read their brand values from here.
