# ADR-032: One report-card template, with page geometry as data

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-08-17
**Phase:** 4.x

## Context

`bilingual.html`, `middle.html`, and `progress.html` were three ~70-line templates that had each
drifted: only one showed an average, only two rendered group headings, and each repeated its own
copy of the same CSS. Visually, all three were a grey boxed grid with every cell outlined, closer
to a spreadsheet printout than a school record. Nothing on the page identified the school.

## Decision

One `templates/report.html`. What differs between the four sets is page geometry, which lives in
`LAYOUTS` in `render.py` as a `PageLayout` (page size, margin, type size, block rhythm, signature
geometry). A change to the school's report card can no longer land on some sets and miss others.

The design is an official school record: a serif masthead with the school's logo at top-left,
hairline rules instead of boxed cells, group headings as small-caps rules, values right-aligned in
tabular figures, comments in a full-width block, a signature line, and a running footer carrying the
student's name via `string-set`. Blue appears only as an accent.

Two supporting decisions:

- Grouping happens in Python (`group_fields`), not in the template, because Jinja's `groupby` sorts
  its input and would silently reorder the columns the school arranged.
- The logo is embedded as a data URI, so the same markup works for WeasyPrint and for a standalone
  HTML preview.

## Alternatives considered

- Keep three templates and restyle each: this guarantees they drift again.
- A Jinja base template with `{% block %}` overrides: blocks inside the per-card `{% for %}` loop
  need `scoped` and read worse than passing geometry as data.
- A modern branded card with a filled header band: striking on screen, but it uses far more toner
  and reads less like an official record.
- Two-column compact layout: it saves paper but is tight for long comments.

## Consequences

- Each student still fits one page in all three geometries, which is asserted by rendering the
  synthetic sets and counting pages.
- A5 elementary is the tight one: its block rhythm and signature are deliberately smaller, and an
  unusually long column set will still flow to a second page.
- `templates/` is in `.prettierignore` because Prettier parses Jinja as plain HTML and reflows
  `{# … #}` and `{% … %}` in ways that damage the template.

## Supersedes / Superseded by

Supersedes the three-template layout from ADR-028. ADR-028's one-renderer-pass-per-set decision is
unchanged.
