# Review handoff (2026-09-15)

Follow `AGENTS.md`, then the handbook and architecture. Preserve local edits and inspect
`git status` before starting. [PR #18](https://github.com/suatsulun/flrc/pull/18) contains the
Hazırlık and school-stage placement work, follow-up fixes, and current validation results.

The follow-up review focuses on shared import identity matching, exact previous-year/stage
boundaries, duplicate names, migration rollback protection, and undo authorization after semester
or roster changes. Synthetic backend and browser regressions cover these cases. The security
review is recorded in `SECURITY-AUDIT.md`; older audit sections are historical.

Use `TODO.md` for release work still requiring production evidence. Run backend tests serially
against disposable `flrc_test`; use a separate freshly seeded database for Playwright. Do not
treat a green repository test run as a school deployment or restore drill.
