# ADR-015: Excel importer uses dry-run before commit

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 3.8

## Context

School Excel files are inconsistent, and roster import mistakes can affect many students. Admins need to see consequences before data changes.

## Decision

Implement the importer as dry-run first. Dry-run parses the file, reports exact warnings/errors, shows proposed changes, and returns a hash. Commit requires matching the dry-run hash.

## Alternatives considered

- Direct import on upload.
- Manual copy/paste forms only.
- CSV-only import.

## Consequences

- Safer admin workflow.
- More importer code.
- Better error messages and testability.
- A file identity mismatch is detectable.
