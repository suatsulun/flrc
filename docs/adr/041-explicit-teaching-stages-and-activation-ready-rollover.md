# ADR-041: Explicit teaching stages and activation-ready rollover

[ADR index](README.md)

**Status:** Partially superseded by ADR-070 (rollover numbers count from 1 in each school stage)

**Date:** 2026-08-21
**Phase:** 3.x

## Context

`teaching_field=english` could not distinguish the twelve primary teachers from the twelve
middle-school teachers. The assignment UI therefore could not filter unassigned English teachers
reliably, and the API could prevent a German/Main mismatch but not a primary/middle mismatch.
Separately, automatic rollover created valid promoted enrollments with blank school numbers, so a
generated next year immediately failed its own activation guard.

## Decision

English users have a required `teaching_stage` of `primary` (grades 1-4) or `middle` (grades 5-8);
German and French users have no stage. Both individual and bulk assignment writes enforce the
field/stage combination. The assignment board filters All, Primary, Middle, German, and French.

Rollover never copies an archived school number. It assigns promoted students new sequential
numbers beginning at 1 in deterministic class/name order. A migration fills only missing numbers in
already-created setup years, preserving any values an administrator entered. Activation keeps its
missing-number guard. The same migration repairs duplicate open-semester states and adds a partial
unique index so at most one semester per year can be open.

## Consequences

- The generated 2027-2028 setup year is activation-ready without hundreds of manual edits.
- Reusing a number in a later year remains safe because uniqueness is scoped to the year.
- Primary/middle assignment mistakes fail at the API even if the UI filter is bypassed.
- Admin user creation and editing now include an English school-level choice.
- Translation integrity is checked automatically across all four locale bundles and literal UI keys.
