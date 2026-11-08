# ADR-027: Grade responsibility warns but does not block collaboration

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-08-17
**Phase:** 2.4-2.7 maintenance

## Context

The role-level ownership check prevented teachers from saving notes owned by another teaching role,
and an unassigned role could make those notes effectively admin-only. The school needs any teacher
to be able to help with any note while making out-of-responsibility edits deliberate and visible.

## Decision

Keep ownership at the column's assigned role: main teachers are warned for skills-owned notes and
skills teachers are warned for main-owned notes. Ownership controls the warning, not ultimate write
authority. Every authenticated teacher may confirm an out-of-assignment save, including when the
role currently has no assigned owner.

The save request carries an explicit `confirm_outside_assignment` flag. The API records a short-lived
override grant for each confirmed foreign role and links the resulting audit entries to it. Active
grants do not hide future warnings in the grid, so each save outside the teacher's responsibility is
deliberate. Optimistic concurrency, semester locks, validation, undo, and actor attribution remain
unchanged.

## Consequences

- Teachers can complete any report-card field without an administrator acting as a data-entry proxy.
- Assigned and foreign fields remain visually distinct, and foreign saves require confirmation.
- Missing teaching assignments no longer block urgent grade entry, but remain visible admin work.
- Direct API writes without ownership, an active grant, or explicit confirmation are rejected.
- Amendment 2026-11-07: administrators save any column without confirmation (the API never asked
  them), so the grid API marks every column `owned_by_you` for them and the grid shows them no
  ownership warning or dialog. This replaces ADR-025's administrator confirmation; the warning now
  appears exactly where a save asks for confirmation. Teachers and coordinators are unchanged.

## Supersedes / Superseded by

Supersedes ADR-025 only where it treated the grant as a separate prerequisite and rejected saves for
unassigned roles.
