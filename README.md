# FL-ReportCard

FL-ReportCard is a school report-card and grade-entry system built for teachers and administrators. It combines a keyboard-friendly teacher workspace with tools for managing school records, generating reports, and keeping important changes auditable.

This project is also a hands-on full-stack learning journey. The repository follows a step-by-step handbook and favors clear, deliberate engineering over hidden magic.

## Product shape

- The teacher workspace opens directly on the grade table, with keyboard entry and visible year,
  semester, grade, subject, and class tabs.
- The admin workspace is also table-first: rosters, yearly school numbers, second languages,
  assessment columns, and assigned teachers live around the same class table.
- Students can move between same-grade class tabs without losing grades or notes.
- Archived years stay browsable, and school numbers are unique per year rather than globally.
- Closing a fully completed year prepares the next year automatically, leaves grades behind, and
  gives promoted students fresh sequential year-scoped school numbers.
- Teachers can filter assessment categories and stage 1-2-3 ratings for a pupil or a whole class
  before saving. Grade 4 German/French use ratings and comments without numeric averages.
- Slow actions keep their button disabled with an in-place spinner, page loads have visible
  progress/skeleton states, and reports announce start, completion, or failure without browser
  alert boxes. Same-grade class tables are prefetched to make tab switching feel immediate.

## Demo

You can visit the public demo at [flrc.suatsulun.com](https://flrc.suatsulun.com).

With public demo login enabled, sign in with a verified Google account to receive a temporary
administrator account for up to 24 hours. The app stores a temporary keyed hash of the Google
subject, plus a synthetic account; it does not persist the Google email, name, picture, or raw
subject. The fictional school is shared with other visitors and resets nightly at midnight
(Istanbul time), removing saved demo changes and ending sessions. See the
[demo identity rules](docs/SECURITY.md#public-demo).

The demo runs on free hosting. During weekday school hours, an automated health check helps keep the backend awake. Outside those hours, the first request may take up to a minute while the service starts. If the login page feels slow at first, please give it a moment and try again.

## Branding it for a school

Everything a school sees (the logo on every screen, the name on every report card,
and the colour of the whole interface) comes from one folder at the root:

```bash
cp ~/their-logo.svg branding/logo.svg   # their logo
$EDITOR branding/brand.json             # their name and accent colour
pnpm brand                              # apply it everywhere
```

There is no second place to remember. See [branding/README.md](branding/README.md).

## Documentation

- [Documentation index](docs/README.md)
- [Current work and release gates](docs/TODO.md)
- [AI review handoff prompt](docs/AI-HANDOFF.md)
- [Builder's Handbook](docs/HANDBOOK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision Log](docs/DECISIONS.md)
- [Privacy Data Map](docs/PRIVACY-DATA-MAP.md)
- [Security Model](docs/SECURITY.md)
- [Operations Runbook](docs/RUNBOOK.md)
- [Branding](branding/README.md)

The handbook explains how the project is built one step at a time. The architecture document covers the reasoning behind the system, while the decision log records important project choices.

## Local development

Use Node from `.node-version` (26.8.1), pnpm from `package.json` (11.25.0), Python 3.13,
uv, and Docker Compose. From the repository root:

```bash
pnpm install --frozen-lockfile
cd apps/backend
uv sync --frozen
```

If `apps/backend/.env` does not exist, copy `.env.example` to `.env`. Configure the local OAuth
client and origins using handbook Steps 0.3 and 1.7-1.10. Run `pnpm dev:services` from the root.
On a new local synthetic database, run `uv run alembic upgrade head` and `uv run flrc seed` from
`apps/backend`, then `pnpm dev` from the root. The teacher app uses `http://localhost:5173`,
admin uses `http://localhost:5174/admin/`, and the API uses port 8000. Worker-backed exports require
a separate worker; see [the backend README](apps/backend/README.md).

Validation commands and test database requirements are documented in the app READMEs and
[AI handoff](docs/AI-HANDOFF.md). The frontend packages currently have no standalone `test` script;
their browser behavior is exercised by the root Playwright suite.

## Repository snapshot: 2026-09-11

The local `v1.2.0` tag is older than the current source; manifests still say `1.2.0`.
Post-tag work includes restored comments, assessment page density, and bounded bulk reads/exports.
The current working tree also contains pending changes that retire grades 5-8 English comments,
order years by their labels, and bound PDF layout batches. These changes are not evidence of a
published release or an applied production migration. See [the release checklist](docs/TODO.md).

## Data privacy

FL-ReportCard is designed for school data, so privacy is treated as part of correctness. This repository, its tests, screenshots, and public demo use synthetic data only. Real student or school data must never be committed to the project.

## Releases and deployments

Application code changes only in this repository. A version tag publishes the `flrc-backend`
and `flrc-web` images; a school's private deployment repository pins those tags, mounts its own
branding, and never carries a copy of the code. See [docs/RELEASING.md](docs/RELEASING.md).

## License

[MIT](LICENSE).

## Optional scheduled operations

CI and security checks run automatically. Operational schedules are opt-in:
set the repository variable `DEMO_KEEPALIVE_ENABLED=true` only on the repository that
owns the hosted demo. Set `DEMO_RESET_ENABLED=true` after adding `DEMO_OPS_TOKEN`
with the demo API's configured operations token. Manual runs still validate the
required secrets and report missing configuration as a failure. An unset flag
means the scheduled job is skipped, not that a reset or backup succeeded.

Legacy copies with `backup.yml` must configure `PG_DUMP_URL`,
`GDRIVE_SERVICE_ACCOUNT_JSON`, and `GDRIVE_BACKUP_FOLDER_ID` before setting
`BACKUP_ENABLED=true`. A copied repository should not duplicate another
repository's demo reset, keepalive, or backup schedule.
