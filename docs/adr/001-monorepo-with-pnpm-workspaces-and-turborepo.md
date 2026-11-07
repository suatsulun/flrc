# ADR-001: Monorepo with pnpm workspaces and Turborepo

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.1

## Context

The project contains two React SPAs, one Python backend, generated TypeScript client code, shared UI components, shared i18n bundles, E2E tests, and documentation. These parts must change together.

## Decision

Use one repository with pnpm workspaces and Turborepo. TypeScript packages under `packages/*` are consumed as source. The Python API participates in the Turbo graph through an `apps/backend/package.json` shim that delegates to `uv`.

## Alternatives considered

- Separate frontend/backend repos.
- Nx monorepo.
- npm workspaces without Turborepo.
- A single app folder without packages.

## Consequences

- One PR can change API schema, generated client, UI, and tests together.
- CI can validate the whole project from one root command.
- The repo teaches modern full-stack monorepo practice.
- Tooling setup is slightly more complex on day zero.
