# FL-ReportCard release checklist

The handbook remains the build history and source of teaching detail. This file tracks only work
that is still relevant to the current table-first release.

## Table-first academic workspace

- [x] Open the teacher app directly on a usable grade table.
- [x] Keep academic year, semester, grade, subject, and class tabs above the teacher grid.
- [x] Combine admin roster, class tabs, yearly numbers, languages, column controls, and class teacher
      assignments in one table workspace.
- [x] Add same-grade drag-and-drop class moves that preserve stable student identity, grades, and
      notes.
- [x] Add a teacher-centered assignment board with All, Primary, Middle, German, and French filters,
      plus field and school-stage guards.
- [x] Use a lower-glare light and dark palette shared by both apps.

## Academic-year correctness

- [x] Move school numbers from students to year-specific enrollments.
- [x] Allow the same number to be reused by different students in different academic years.
- [x] Keep continuing students connected through a stable student id when their number changes.
- [x] Create the next consecutive setup year after both semesters are locked and the current year is
      archived.
- [x] Copy class structure, teacher assignments, column templates, promoted grade 1–7 enrollments,
      and second-language choices.
- [x] Never copy grades, audit history, or old school numbers into the next year; assign fresh
      sequential year-scoped numbers.
- [x] Block activation if any setup-year enrollment is still missing a school number.

## Release gate

- [x] Apply the complete Alembic chain from zero on a disposable database.
- [x] Run repository lint, typecheck, test, and production-build tasks under the shared heavy-job
      lock.
- [x] Run the two-user grade conflict E2E test.
- [x] Run the Chromium admin-table E2E for year context, sorted inline student creation, class-tab
      dragging, column creation, and both themes.
- [x] Exercise 20 simultaneous grid readers and enforce teacher/column field compatibility in API
      regression tests.
- [x] Enumerate every API data route and prove anonymous requests fail closed.
- [x] Enforce verified Workspace claims, admin pre-registration, stable Google identity binding,
      secure absolute sessions, HTTPS, trusted hosts, private gateway origin, and no-store API
      responses.
- [x] Add the always-on locked-dependency audit and weekly Dependabot coverage; enable CodeQL and
      dependency review with `GHAS_ENABLED=true` when the repository plan provides GitHub Advanced
      Security.
- [ ] Complete the production-provider security pass: Internal OAuth where available, exact
      callback, MFA, encrypted gateway secret on both sides, Cloudflare Always Use HTTPS, and
      Render inbound restrictions where the selected plan permits them.
- [ ] Complete the final human acceptance pass for keyboard grid entry and exceptional semester
      reopening before production release.
- [ ] Verify the production deployment migration and rollback notes before release.

All test and screenshot data must remain synthetic.
