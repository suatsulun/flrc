# ADR-018: ESLint 10 flat-config baseline

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.2

## Context

The original handbook named ESLint 9, while the current Vite scaffold installed ESLint 10. ESLint 10 is the current stable major, removes the legacy eslintrc system, and is supported by the selected TypeScript and React plugins.

## Decision

Use ESLint 10 with per-package flat configs. Require Node `^22.13.0 || >=24.0.0`, matching ESLint 10's supported Node releases while retaining the project's Node 22 baseline.

## Alternatives considered

- Downgrade the Vite-generated apps to ESLint 9.
- Keep different ESLint majors across workspace packages.
- Replace ESLint with Biome.

## Consequences

- The project follows the current ESLint configuration model and release line.
- Each linted workspace package owns its config and lint dependencies.
- Node 23 and Node releases older than 22.13 are unsupported.
- Plugin upgrades must retain explicit ESLint 10 peer support.
