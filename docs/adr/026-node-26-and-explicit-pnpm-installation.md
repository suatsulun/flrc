# ADR-026: Node 26 and explicit pnpm installation

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-13
**Phase:** Maintenance

## Context

The workstation and CI moved to Node 26. Node no longer bundles Corepack starting with Node 25,
so changing fnm versions can make a previously available pnpm shim disappear even though the
repository and pnpm store remain intact.

## Decision

Standardize local development and CI on Node 26, record the exact runtime in `.node-version`, and
install pnpm 11 explicitly into the active Node environment. Keep the pnpm major and minimum
version in `package.json` so CI and local tooling use the same supported line.

The legacy static Vercel gateway keeps an isolated Node 24 manifest because Vercel Builds do not
yet offer Node 26. It contains no application code or dependencies; the teacher/admin builds and
all local/CI application checks continue to use the repository's Node 26 baseline.
Because Vercel treats that directory as a standalone project root, its manifest must also repeat
the root `packageManager` pin; the two values move together during pnpm upgrades.

Upgrade dependencies to their latest mutually compatible stable versions. Keep TypeScript on 6.0
until the stable `typescript-eslint` release declares TypeScript 7 support; do not suppress the peer
incompatibility. Migrate TanStack Table to the native v9 API instead of its deprecated legacy hook.

## Consequences

- Switching fnm versions may require installing pnpm for that Node installation.
- CI and local development exercise the same Node major.
- The static Vercel gateway remains deployable until Vercel Builds support Node 26.
- The table no longer triggers the React Compiler incompatibility warning from TanStack Table v8.
- TypeScript 7 remains a tracked follow-up rather than an unsupported forced upgrade.

## Supersedes / Superseded by

Supersedes ADR-018 only for its Node-version baseline; the ESLint 10 flat-config decision remains.
