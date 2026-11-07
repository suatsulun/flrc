# ADR-036: Automatic rollover after a fully closed year

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-20
**Phase:** 3.x

**Superseded in part by:** ADR-041 (fresh sequential rollover numbers), ADR-066 (no automatic
promotion into grade 1 or grade 5)

## Context

Starting a school year by recreating dozens of class, column, teacher, and student connections is
slow and error-prone. Grades and school numbers, however, must never be copied forward.

## Decision

Archiving a standard `YYYY-YYYY` year after both semesters are locked creates the next consecutive
setup year in the same transaction. It copies class structure, teacher assignments, semester column
templates, and second-language choices. Students in grades 1-7 are enrolled in the next grade with
the same stable student id; grade 8 students graduate and are not enrolled. Grade values, audit
rows, save batches, and old school numbers are not copied. ADR-041 replaced the original empty-number
preparation step with fresh sequential numbers in the target year.

Activation is explicit and requires every promoted enrollment to have a number. Rollover is
idempotent when the target year already exists.

## Consequences

- The next year is available immediately after closing the current one.
- Admins prepare only the information that truly changes: numbers, new arrivals, departures, and
  exceptional class placement.
- Longitudinal history remains connected without mutating an archived year.
