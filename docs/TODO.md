# FL-ReportCard current work and release checklist

Repository review date: **2026-09-15**. Relevant handbook scope: Phase 2 assessment editing,
Phase 3 lifecycle/archive behavior, and Phase 4 reports, backups, and release checks.

## Version and evidence boundary

Root and backend manifests say `1.2.0`, but the local `v1.2.0` tag predates the current source.
ADR-063, year sorting, and PDF batching are committed; Hazırlık and placement changes are reviewed
in [PR #18](https://github.com/suatsulun/flrc/pull/18). Its review also consolidates import identity
matching and closes locked-term/moved-pupil undo authorization gaps. The PR records the exact
reviewed commit and fresh test/scan results. These changes are not proof of a release or deployment.

The implemented baseline below describes source. Production-provider configuration, school-owned
backups, restore evidence, and human acceptance still require the separate release gates below.

## Implemented baseline

- [x] Teacher and admin class tables with year/semester/grade/subject/class navigation.
- [x] Same-grade enrollment moves preserving student identity, grades, and notes.
- [x] Hazırlık classes as grade 0 with named sections, importable and reported like grades 1-4.
- [x] Rollover stops at stage boundaries; the roster import re-attaches Hazırlık and grade 4 pupils by name.
- [x] Year-specific school numbers, fresh sequential numbers on rollover, and activation guards.
- [x] Field/stage-checked assignments and archived-year write protection.
- [x] Versioned grade saves, explicit conflicts, grants, audit, and undo.
- [x] Category filters, notes, whole-pupil/class rating drafts, and a 2,000-cell save bound.
- [x] Four/five sentence columns at laptop widths and the angled middle-English overview.
- [x] Import review with file/review hashes and bounded bulk queries.
- [x] Streaming year workbooks, private report overlays, teacher signatures, and identity audit.
- [x] School backup service with encryption, freshness checks, restore tests, and year archives.
- [x] Authentication hardening, dependency audit, secret scanning, and synthetic regression suites.

## Completed source review

- [x] Review ADR-063 across seed, create/update, list/reorder, copy/rollover, live grid, archive,
      student history, and reports: grades 5-8 English have no comments; primary English and
      German/French retain them. Check translated feedback for `middle_english_no_comments`.
- [x] Review and test migration `82a91f4c6d30` after `7d26cb91a540`: deactivate text definitions,
      preserve values/versions/audits, include archived years, and keep downgrade non-reactivating.
- [x] Verify year lists sort by descending label and student history by ascending label even when
      insertion ids are out of order; check assumptions about nonstandard labels.
- [x] Verify PDF layout batches stay within 16 render units, preserve page order/duplex covers,
      and keep the serial fallback bounded when a process pool is absent or fails.

## Fresh release gates

- [x] Run focused assessment, archive, report, and migration regression tests on the disposable
      local test database; serialize runs because fixtures wipe shared state.
- [x] Run lint, typecheck, tests, and production builds for the reviewed source. Frontend packages
      have no standalone `test` script; root Playwright supplies browser coverage.
- [x] Regenerate the API client and inspect any drift; run branding and i18n checks.
- [x] Run the assessment-grid browser checks and the two-user grade conflict E2E. Verify both
      app origins, a freshly seeded disposable E2E database, four locales, and desktop/phone views.
- [ ] Complete the production-provider security pass for the chosen managed or school-hosted profile.
- [ ] Record a school-owned restore drill and final human acceptance for keyboard entry, printed
      reports, and exceptional semester reopening.
- [ ] Choose the next release version, write its complete migration/rollback notes, and verify
      both images are published before changing private deployment pins.

The [AI handoff](AI-HANDOFF.md) requests review before implementation. All test data is synthetic;
production owners, credentials, deployment state, and backup success must be verified separately.
