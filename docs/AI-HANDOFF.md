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

## Public demo checkpoint (2026-09-21)

Relevant scope: handbook Step 1.11, Phase 4 reports, and ADR-051/052/064. These checks cover
the public demo, not a deployment of real school data.

- The active application repository is `suatsulun/flrc`; `suatsulun/fl-reportcard` is archived.
  Private 3Mart branding, report assets, and local launchers belong in `suatsulun/3Mart-flrc`.
- [The public demo](https://flrc.suatsulun.com/demo) serves both panels through one Vercel
  project and uses Render, Neon, and Upstash. Google publication and a real visitor sign-in
  were confirmed after public visitor mode was enabled.
- The golden baseline contains archived 2023–24, 2024–25, and 2025–26 plus active 2026–27:
  52 classes and 1,144 enrollments per year, 1,804 linked synthetic students, 28 synthetic
  staff, 181,048 grade values, and 8,932 comments. Past semesters are locked; the current
  first semester is filled and open, and the second is prepared.
- Daily restore is enabled at 00:00 Europe/Istanbul, with catch-up after a missed run or
  cold start. The [reset drill](https://github.com/suatsulun/flrc/actions/runs/35589267844)
  removed a temporary year and export job while restoring baseline counts. Visitor changes
  and sessions are discarded on reset. See [the reset runbook](../infra/README.md#nightly-demo-reset).
- [PR #19](https://github.com/suatsulun/flrc/pull/19) deployed the demo homepage, privacy
  policy, and terms. [PR #20](https://github.com/suatsulun/flrc/pull/20) deployed year,
  semester, and class selection for PDF printing; the free demo requires a class selection.
  Its required CI passed, including 245 backend tests and 63 browser tests.
- All four PDF types were rendered and visually checked locally, and a live worker produced
  a valid seven-sheet year workbook. Production PDF download after Google sign-in has not
  been directly observed. Local class rendering took 3.9 seconds for 22 students; this is
  not a performance measurement of the hosted free service.
- The school playground builds the sibling application checkout and keeps its own persistent
  data and private branding. Start it from `flrc-school-deploy` with `./scripts/local.sh` and
  open `http://localhost:8080/api/local/login`. Its separate Google-login profile still needs
  the downloaded local OAuth client JSON. The private repository README contains both workflows.

Provider resource IDs, operator state, and local credential paths are recorded only in the
private deployment repository's `docs/SETUP-CHECKPOINT.md`. Credentials remain outside Git.
PR #18 remains open; the public demo runs main without those Hazırlık changes.
