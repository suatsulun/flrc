# ADR-062: Bounded bulk reads and shared field behavior

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 2-4 maintenance (grade fields, administration, imports and year exports)

## Context

A codebase-wide simplification review found per-row database reads in assignment updates and
imports, full result materialization in year exports, and duplicated field and language-control
logic. Existing route splitting, per-cell draft subscriptions and parallel PDF rendering already
address their respective workloads; those designs remain in place.

## Decision

- Validate every assignment change, then apply the final change for each class/role using one
  existing-assignment lookup. The 40-slot regression case uses 5 SELECTs instead of 44.
- Load a year's enrollment identities and language rows once during import commit. The 40-row
  existing-roster case uses 8 SELECTs instead of 126. Numberless rollover identities are consumed
  only once; ambiguous names still create a new identity instead of merging existing people.
- Write all seven year-export sheets through one streaming writer, fetching at most 1,000 rows
  per batch. Close each result before committing durable progress. Preserve the workbook columns,
  values, formula neutralization and sheet order.
- Share filled-cell lookup between completeness and missing-cell views. Fetch IDs rather than
  grade objects and comment bodies; index assessment IDs by grade and subject once per request.
- Keep label fallback and grade-value selection in `academics/fields.py`, shared by live grids,
  archives and report builders. Optional report labels retain their existing null behavior.
- Share the language switch in the UI package through explicit language/label/callback props.
  Memoize import-draft serialization so search and drag state do not repeatedly sort unchanged edits.

## Consequences and checks

The public API, database schema, permissions, audit/save-conflict rules and printed layouts are
unchanged. Request-local indexes avoid cache-invalidation rules, while streaming exports trade
one full result allocation for bounded row batches. No dependencies are added.

`tests/test_bulk_operations.py` covers query budgets, repeated assignment slots, input validation,
identity preservation, rollover namesakes, a 1,202-student streaming export, and completeness.
`e2e/language-switch.spec.ts` covers all four locales and persisted selection in both apps.
Run these with the complete backend and browser suites; regenerate the client to check contract
drift and run JavaScript lint, typecheck and production builds before merging.
