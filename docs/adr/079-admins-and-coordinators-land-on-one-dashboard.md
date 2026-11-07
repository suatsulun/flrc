# ADR-079: Admins and coordinators land on one dashboard

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** Product-wide UX (admin)

## Context

ADR-037 opened the admin panel on the class table, while coordinators landed on a list of links
and had a separate coordinator page with completion figures. Neither told an admin where the year
stood or what to do next: the next lifecycle step, the classes still missing grades and who owns
them, the setup gaps that later break report cards, and the background files waiting to be
downloaded each lived on a different screen or nowhere. Several backend reads also had no UI: the
missing-grade drill-down, the whole-year student search, and the audit log's teacher, student and
date filters.

## Decision

- `/` is a dashboard for admins and coordinators alike, backed by one read,
  `GET /api/dashboard` (admins and coordinators; teachers 403). It describes the active year, else
  the newest year in setup, else nothing:
  - **Term status and next step.** One code with the facts behind it: `create_year`;
    `activate_year` with blockers (pupils without a school number, the only activation guard);
    `collect_grades` while the open semester is incomplete, with its completion percentage;
    `advance_semester` / `lock_semester` once it is complete; `close_year` when both semesters are
    locked. A semester without any field is not complete.
  - **Completion** of the open semester (else the last one) per class and subject, with a
    drill-down dialog listing each empty cell's pupil, field, owner role and assigned teacher
    (`/api/coordinator/classes/{id}/missing` now returns those names), linked to the class table.
  - **Setup problems** with counts and the first 50 concrete items each: roles without a teacher,
    classes without fields for a subject, assigned teachers without a report name or a signature,
    pupils without a school number, and pupils in second-language grades without a second
    language. A class needs English main and skills teachers always, and a German or French
    teacher and fields once it has a pupil taking that language; the overview's
    `missing_assignments` uses the same rule instead of four roles per class.
  - **Report readiness** per card kind: classes in the card's grades with at least one pupil on
    that card, how many are complete, and the share of the printed fields entered. The
    middle-school English card counts each pupil's own German or French score fields too, since it
    prints them.
  - **Downloads**: recent background report and export jobs with progress, expiry and a download
    link.
- The coordinator page is merged into the dashboard and `/coordinator` redirects to `/`. The
  navigation lists the dashboard first for everyone and adds **Öğrenciler**.
- `/students` is a whole-year student search (name or number, cursor paging) that opens a pupil's
  history or their class. The class table accepts `?year=&grade=&class=&subject=` so other pages
  can link straight to a class, and it keeps those choices in the URL.
- The audit page filters by teacher, student and a range of whole days, and its CSV export carries
  the same filters.

## Alternatives considered

- Keep opening on the class table and add a separate dashboard link: the daily table stays one
  click away in the navigation, while the landing page is where the year's state belongs.
- Assemble the dashboard in the browser from the existing endpoints: about ten requests per visit
  and the next-step rules duplicated in the client.
- Expect a German or French teacher for every class in grade 4 or above: classes without such
  pupils would always show a false gap.

## Consequences

- Admins open on the year's state rather than a table; the class table is one click away.
- Coordinators see the same read-only picture; links to admin-only screens are hidden for them.
- The dashboard grid leaves room for more cards, such as recent changes with undo.
- One request computes completeness, problems and readiness for the whole school with a fixed
  number of queries; item lists are capped so a large gap cannot inflate the response.

## Supersedes / Superseded by

Supersedes ADR-037's decision that the admin panel opens on a table.
