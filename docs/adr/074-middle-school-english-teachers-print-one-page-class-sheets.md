# ADR-074: Middle-school English teachers print one-page class sheets for parent meetings

[ADR index](README.md)

**Status:** Accepted; amended by ADR-077 (class sheets use the 30/min single-report limit and named files)  
**Date:** 2026-11-06  
**Phase:** 4.x (reports)

## Context

At parent-teacher meetings middle-school English teachers talk through several classes. The grade
grid pages its columns and cannot be printed, and the report-card sets are per-student documents
limited to coordinators and administrators. These teachers asked for one table per class with every
field, opened from the class they are looking at, printed on a single sheet of paper per class.
Other subjects and grades do not need it.

## Decision

- Class reports cover English in grades 5 to 8 only. The API refuses other classes with
  `class_report_middle_english_only`, and the teacher app shows the sidebar entry only to teachers
  assigned to a middle-school English class. Either English assignment (main or skills) counts,
  whether or not that role owns any of the semester's fields: the class catalog reports every role
  as `assigned_roles`, while a subject's `my_roles` keeps describing field ownership.
- The report lives at `/class-report/{class}` beside the grade grid and reuses its year, semester
  and class pickers, narrowed to grades 5 to 8. The sidebar entry opens the report of the class on
  screen; while a report is open the sidebar shortcuts open reports of the teacher's classes.
- One builder (`modules/reports/class_sheet.py`) produces the sheet for the preview
  (`GET /api/classes/{class_id}/sheet`) and the PDF (`GET /api/reports/class-sheets`), so screen
  and paper share columns and order. Grades 5 to 8 English have no notes (ADR-063), so a sheet is
  one row per student, and text fields never reach it.
- Each class prints on one A4 landscape page. The builder sizes rows (and their type) from the
  class size; names, group headings and the title stay on one line, field headings and the
  masthead details are clipped at a fixed height, and with many fields the name column narrows
  and grade type shrinks so every grade stays whole. Up to 34 students fit on the page. "All my
  classes" prints one page per class in one file; empty classes are left out.
- Rows alternate in shade, and the preview marks the student the teacher clicks or reaches with the
  arrow keys.
- Reads follow ADR-071: any signed-in teacher may preview or print any middle-school English class.
  The PDF shares the report routes' per-account rate limit; the preview is as cheap as a grid read
  and is not limited.
- Printed labels follow the teacher's interface language; field names stay in English (ADR-072).
  Every page footer says it is the teacher's copy listing the whole class.

## Alternatives considered

- Every subject and grade: German/French and primary English carry long checklist sentences and
  notes that cannot fit one page per class, and those teachers did not ask for it.
- Print the grid page with browser print CSS: its paging and sticky controls do not survive
  printing, and page fitting and Turkish glyphs would depend on each browser.
- Render the preview from the grid response: quicker to build, but the layout rules would be
  implemented twice and could drift from the PDF.

## Consequences

- A printout lists every pupil of a class with their grades. It is meant for the teacher's own
  reading; showing it to a parent shows them other pupils' records. Per-pupil conference slips
  would be a separate document.
- A class larger than 34 pupils continues on a second page rather than shrinking type below 7.5 pt.
- PDF responses are not stored server-side; downloaded files fall under the school's own retention
  practice, like other direct PDFs.

## Supersedes / Superseded by

Builds on ADR-063, ADR-071 and ADR-072.
