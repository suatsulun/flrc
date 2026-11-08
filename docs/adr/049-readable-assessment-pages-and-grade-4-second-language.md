# ADR-049: Readable assessment pages and Grade 4 second-language rubrics

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-08
**Phase:** 2.1, 2.4, 3.6, 4.1

## Context

Fitting every teacher assessment on screen (ADR-039) broke long criterion labels into tiny
fragments. The school also clarified that Grade 4 German and French use only the 1-2-3 rubric:
no numeric exam/homework columns, teacher-comment columns, or score average.

## Decision

The teacher grid shows up to three assessments at a time, reducing to two or one as the available
width narrows. Category buttons filter the assessments; previous/next controls expose every
column in its configured order. Full sentence headings use normal case and readable type, with
ownership notices on their own line. Student names remain visible, and a scale legend explains
1-2-3. The document remains the only scrolling surface. Switching assessment pages or categories
does not navigate away from the class or clear the Zustand draft; Save still drains every dirty
cell, including hidden columns, through the existing version/conflict and ownership checks.

`academics/programme.py` defines Grade 4 second-language type eligibility. Creation and updates
reject non-scale columns and score-average flags. Copying into Grade 4 includes only eligible
rubrics. Seed and academic-year rollover use the same rule, while Grade 4 English and Grades 5-8
second languages retain their existing column types.

Alembic data migration `f4b82d903e61` disables existing Grade 4 German/French score and text
columns and clears average flags in active/setup years. It preserves column identities, saved
values, audit history, and archived years. Grid reads and report builders already select active
columns, so both reflect the correction. Downgrading does not automatically resurrect disabled
columns; any restoration is deliberate. No schema fields or dependencies are added.

This focused teacher view supersedes ADR-045's bounded teacher-grid viewport: pagination keeps
columns readable while student rows follow the page scroll. Captions and readable controls remain;
the admin class table still uses the contained viewport.

## Consequences

- Teachers can read complete criteria, with an extra category/page action to reach other columns.
- Normal page scrolling and the phone stepper remain available.
- Old saved data is retained; current Grade 4 second-language assessments and reports use scale3.
- Archived reports retain the configuration under which they were issued.

## Supersedes

ADR-039's requirement that every teacher assessment be visible simultaneously. Its single
vertical scroll rule and the admin workspace behavior remain in place.
