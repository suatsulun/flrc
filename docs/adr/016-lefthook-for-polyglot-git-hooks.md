# ADR-016: Lefthook for polyglot git hooks

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.2

## Context

The repo contains TypeScript and Python. Pre-commit checks should not be JS-only or Python-only.

## Decision

Use Lefthook to run Prettier/ESLint for TS and Ruff for Python on staged files.

## Alternatives considered

- Husky + lint-staged.
- Python `pre-commit` framework.
- No hooks, CI only.

## Consequences

- One hook tool covers the repo.
- Bad formatting is caught before commit.
- New clones need hook installation through the package prepare script.
