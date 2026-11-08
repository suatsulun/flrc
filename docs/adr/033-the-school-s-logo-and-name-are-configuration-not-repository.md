# ADR-033: The school's logo and name are configuration, not repository content

[ADR index](README.md)

**Status:** Superseded by ADR-034

**Date:** 2026-08-17
**Phase:** 4.x

## Context

The school's logo has to appear top-left on every screen and on every printed report card, but this
repository is not where the school's branding belongs; it arrives later in the school's own private
repository.

## Decision

Four swap points, none of which require a code change:

| What        | Where                                                                      | How                                  |
| ----------- | -------------------------------------------------------------------------- | ------------------------------------ |
| Web logo    | `apps/teacher/public/school-logo.svg`, `apps/admin/public/school-logo.svg` | replace the file                     |
| Web name    | `VITE_SCHOOL_NAME`                                                         | deploy environment                   |
| Report logo | `modules/reports/assets/school-logo.svg`, or `SCHOOL_LOGO_PATH`            | replace the file, or point elsewhere |
| Report name | `SCHOOL_NAME`                                                              | deploy environment                   |

Each app resolves its logo through `import.meta.env.BASE_URL` so the URL stays correct under the
admin app's `/admin/` base and resolves from deep client routes. `SchoolLogo` falls back to a neutral
monogram if the file is missing or fails to load, so a checkout without branding never shows a broken
image. The committed files are placeholders carrying a comment that says so.

## Alternatives considered

- Import the logo as a bundled module: a build-time dependency on a file the public repo must not
  contain.
- Serve the logo from an API endpoint: it adds a request and a backend route for a static asset.
- Hardcode and let the private repo patch the component: a merge conflict on every UI change.

## Consequences

- The private repository overlays files and sets two environment variables; it never forks a
  component.
- The placeholder is visible in the public demo, which is intended.
- `VITE_SCHOOL_NAME` is baked at build time, so changing it needs a rebuild.

## Supersedes / Superseded by

Superseded by ADR-034, which keeps this decision's substance but collapses the four
swap points into one root folder.
