# ADR-053: One public application repository, private deployment overlays, released images

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.3 (public release)

## Context

The project must be a portfolio piece anyone can read and a product one school runs, without the
school's branding, secrets, or operations ever entering the public tree and without maintaining
two copies of the application. Both installations must receive every fix without hand-copying
code, and the school must approve each upgrade explicitly.

## Decision

Application code lives in exactly one repository, the public `flrc` repository under the MIT
licence. It contains the code, tests, migrations, generic branding, and both the demo and school
runtime policies. It was created from a reviewed, squashed snapshot of the private development
history; that history stays private and is not published.

A version tag `vX.Y.Z` on the public repository publishes two multi-architecture images to GHCR,
`flrc-backend` and `flrc-web`, and a GitHub Release (`.github/workflows/release.yml`,
[operations/deployment.md](../operations/deployment.md)). The tag must equal the version in
`apps/backend/pyproject.toml`.

A school's private repository holds only a Compose file that pins those image tags, the Caddy
site address, the branding overlay (ADR-054), the environment, and operational documentation.
Dependabot's Compose support opens the upgrade pull request there when a new tag exists; merging
it is the approval, and rolling back is reverting it. The public demo deploys from `main`
automatically and does not wait for a tag.

## Alternatives considered

- Flip the private repository to public with its full history: every past commit message and
  author identity becomes permanent; a reviewed snapshot is safer.
- A git submodule pin plus a build in the private repository: it requires the whole Node, uv, and
  Docker toolchain in every school repository and a cross-repository token for update requests.
- A subtree copy synchronized by a bot: a second physical copy of the application, which is the
  drift the single-repository rule exists to prevent.

## Consequences

- One place to change code; one tag to release; one pull request per school to upgrade.
- MIT is irrevocable for published versions. Copyright remains with the author, so future
  versions can be relicensed only while every contributor has assigned or licensed their work.
- The private repository never builds anything, so it cannot drift from the release it pins.
- GHCR packages inherit the public repository's visibility; a school pulls without credentials.
