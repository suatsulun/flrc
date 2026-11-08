# ADR-059: Whole-class rating drafts and explicit rating labels

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 2.4-2.5 (grid and Save All)

## Context

Teachers need to isolate written comments, set every 1-2-3 assessment for one pupil or a
whole class, and see the report-card meanings of those ratings. The old category filter
omitted ungrouped comments, and a full-class rubric can exceed the 500-cell save limit.

## Decision

The notes filter selects text columns explicitly in both table and single-pupil views.
Bulk controls change only scale3 columns for the current class, subject and semester,
across all assessment categories. They update Zustand in one operation, preserve any
existing draft's expected version, and leave numeric scores and comments intact. They do
not call the API until Save. Existing ownership confirmation, optimistic concurrency,
audit entries, and undo remain in the normal save path. Locked semesters expose no bulk controls.

The save request permits up to 2,000 cells so ordinary full-class rubrics fit one audited
save batch and one undo operation. The bound is retained; no schema or grading-scale change
is required. The API contract is regenerated from this validation rule.

Rating labels use the existing localized UI vocabulary: Geliştirilmeli, İyi and Çok iyi in
Turkish, with corresponding German, French and English translations. Primary English adds
faces beside the words. German and French show the words without faces, including locked cells.

## Validation

Browser tests cover notes-only filtering, student and class bulk edits across hidden
categories on desktop and phone, all three values, read-only grids, labels and faces, and
edits made while a save is pending. Draft tests preserve scores, comments and original
versions. Backend tests save 600 rating cells as one audited batch and undo all of them,
and verify oversized requests are still rejected. The existing two-writer collision test
continues to require explicit overwrite confirmation.
