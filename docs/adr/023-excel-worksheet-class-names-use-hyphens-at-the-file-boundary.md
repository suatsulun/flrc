# ADR-023: Excel worksheet class names use hyphens at the file boundary

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-11
**Phase:** 3.6-3.8

## Context

The domain displays classes as `5/A`, but XLSX forbids `/` in worksheet titles. A fixture that
sets a sheet title to `5/A` cannot be saved by Excel-compatible libraries.

## Decision

Use `5-A` for class-specific worksheet titles and accept both hyphen and slash forms in cell
values/parser input. Normalize every accepted form back to the canonical `5/A` domain display.

## Consequences

- The hostile fixture is valid XLSX and opens in Excel/LibreOffice.
- The UI, API, and database retain slash-delimited class names.
- Import tests permanently cover this boundary normalization.
