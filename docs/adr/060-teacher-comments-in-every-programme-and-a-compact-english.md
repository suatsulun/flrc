# ADR-060: Teacher comments in every programme and a compact English grid

[ADR index](README.md)

**Status:** Partially superseded by ADR-063 (middle-school English comments only)

**Date:** 2026-09-10

**Phase:** 2.1.3, 2.4 (column defaults and grade grid)

**Current reading:** the decision below records the 2026-09-10 choice. ADR-063 removes the
middle-English opinion field and its notes filter. Primary English and German/French comments,
grade-4 L2 rating rules, and the compact angled English grid remain in effect.

## Context

The grade 4 German/French restriction incorrectly excluded text fields along with
numeric scores, leaving those classes without teacher comments. Middle-school English
also lacked a default comment field and paged eleven short score headings across four screens.

## Decision

Grade 4 second-language classes accept scale3 assessments and text comments, without
numeric scores or averages. Every default programme includes a final teacher comment field.
An additive migration supplies missing comment fields in configured subjects of non-archived
years. It preserves existing definitions, disabled comments, saved values and audit history;
it neither reactivates old fields nor deletes fields on rollback. No new table or sensitive
student attribute is needed. Administrators retain the ability to configure text columns.

Teacher notes always appear as the final filter category on desktop and phone. A subject
without an active text field explains how an administrator can add one.

At sufficient width, middle-school English shows all numeric fields followed by comments.
The teacher selected 45-degree headings with matching slanted borders. Narrow screens retain
assessment paging and the existing single-student view. Input ownership, drafts, audited
saves, keyboard navigation and conflict handling use the same components and services.

## Validation

Check migration idempotence and preservation of historical values and archives, comment
creation and editing in the admin API, save/audit/report inclusion, and seed/copy/rollover rules.
Browser checks cover the final notes filter and editing on desktop and phone, all default
English headings in four locales, laptop widths, keyboard navigation and the narrow fallback.
Private deployment checks verify every grade and semester against the school's source rows.
