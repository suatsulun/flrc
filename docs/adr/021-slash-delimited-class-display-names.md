# ADR-021: Slash-delimited class display names

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-01
**Phase:** 1.7

## Context

Class names combine a numeric grade level and an alphabetic section. The handbook originally
rendered these labels with a hyphen, such as `5-A`, while the school's preferred convention is a
slash, such as `5/A`.

## Decision

Use `/` as the canonical display delimiter for class names in API responses, user interfaces,
reports, fixtures, and documentation. Import parsing may continue to accept `-` as a legacy or
hostile-input delimiter, but normalized output uses `/`.

## Alternatives considered

- Keep the handbook's original `5-A` format.
- Store a formatted class name in the database.
- Allow each interface to choose its own delimiter.

## Consequences

- Class labels are displayed consistently as `5/A` throughout the product.
- Grade level and section remain separate database fields; this is only a presentation rule.
- Import tests retain coverage for noncanonical hyphenated input.
