# ADR-024: Completed job output is a short-lived Postgres blob

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 4.1

## Context

Render container files are ephemeral, while the school workload is small and must survive worker
restart without adding another student-data processor.

## Decision

Store completed PDF/XLSX bytes in deferred `job_runs.output_blob` columns for 24 hours. Polling
never loads the blob; authorized download explicitly loads it. Purging removes only bytes, not job
history. Preserve the API contract so an object-storage adapter can replace this later.

## Consequences

- Outputs survive worker restart and stay under existing database authorization.
- Database storage temporarily grows with generated artifacts and must be purged.
- Move behind approved object storage if measured volume exceeds the small-school assumption.
