# ADR-010: Jinja2 + WeasyPrint for PDFs

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 4.2

## Context

Report cards are visual, bilingual, and print-sensitive. The developer already knows HTML/CSS, and the project should reuse those skills.

## Decision

Render report contexts through Jinja2 templates and convert HTML/CSS to PDF with WeasyPrint.

## Alternatives considered

- ReportLab.
- Headless Chromium print-to-PDF.
- LaTeX.
- Typst.

## Consequences

- Report layouts are authored in HTML/CSS.
- Docker must include WeasyPrint system dependencies.
- Page sizing and print CSS become part of the test surface.
- Typst remains a possible future experiment, not the main path.
