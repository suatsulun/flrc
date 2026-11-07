# ADR-043: Plan-aware GitHub security gates

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-24
**Phase:** 4.10 / operations

## Context

CodeQL SARIF upload and dependency review require GitHub Advanced Security for this private
repository. Running those actions without the entitlement made every push and pull request red even
though the actions could not perform a scan. The repository's independent JavaScript and Python
locked-dependency audit remained available and green.

## Decision

The locked-dependency audit remains unconditional. CodeQL and dependency review run for public
repositories or when the repository variable `GHAS_ENABLED` is exactly `true`. Operators set that
variable only after enabling GitHub Advanced Security. Dependabot ignores TypeScript 7 until both
typescript-eslint and the OpenAPI generator support it, and it does not change the Python 3.13 base
image to 3.14 without an explicit runtime migration.

## Alternatives considered

- Leave the unsupported actions red: rejected because failure no longer meant a code or dependency
  problem.
- Disable all security automation: rejected because the lockfile audits and Dependabot work on the
  current plan.
- Upload local CodeQL output without GitHub Advanced Security: rejected because private-repository
  CodeQL use is entitlement-bound, not only an upload configuration problem.

## Consequences

- Security workflow results distinguish actionable findings from unavailable paid capabilities.
- The repository retains always-on production dependency audits on its current plan.
- Enabling GitHub Advanced Security requires one explicit repository variable before the additional
  gates become required.
