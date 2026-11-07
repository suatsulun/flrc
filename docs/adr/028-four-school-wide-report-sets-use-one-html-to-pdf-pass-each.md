# ADR-028: Four school-wide report sets use one HTML-to-PDF pass each

[ADR index](README.md)

**Status:** Partially superseded by ADR-077 (sets larger than one class are background jobs with polling and ZIP formats)
**Date:** 2026-08-17
**Phase:** 4.2-4.4 maintenance

## Context

Rendering one PDF per student through WeasyPrint, committing progress after each card, zipping the
files, waking a Celery worker, and polling the job made school-wide reports disproportionately slow.
The required outputs are four PDFs: elementary English, middle-school English, German, and French.

## Decision

Build each report set in a bounded number of database queries, render all matching classes through
Jinja2 as one HTML document, and convert that complete document to one PDF in a single WeasyPrint
pass. Return the PDF from an authenticated, non-cacheable endpoint. Elementary English uses grades
1-4, middle-school English uses grades 5-8, and German/French include every applicable class and
student selected into that language.

Remove the per-student PDF worker loop, ZIP assembly, and report-job polling from the normal report
flow. Keep WeasyPrint only as the final HTML-to-PDF stage, invoked once per complete set. Keep Celery
and durable `job_runs` for whole-year XLSX exports, which remain genuinely asynchronous work.

## Consequences

- Four actions cover the full school instead of requiring class-by-class selection.
- Hundreds of renderer startups become one renderer pass per requested PDF set.
- Report output is a real PDF but is no longer stored as a 24-hour ZIP bundle.
- The school's printer must be included in print-layout checks.

## Supersedes / Superseded by

Supersedes ADR-010's per-student batch shape and ADR-024's report ZIP storage. Jinja2 and WeasyPrint
remain the rendering layers; ADR-024 still applies to XLSX exports.
