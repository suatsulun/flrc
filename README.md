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
- Slow actions keep their button disabled with an in-place spinner, page loads have visible
  progress/skeleton states, and reports announce start, completion, or failure without browser
  alert boxes. Same-grade class tables are prefetched to make tab switching feel immediate.

## Demo

You can visit the public demo at [flrc.suatsulun.com](https://flrc.suatsulun.com).

Sign in with any Google account. You receive a temporary administrator account for up to 24 hours, and nothing about your Google account is stored. The fictional school is shared with other visitors and resets every night at midnight (Istanbul time), so unsaved edits are lost then.

The demo runs on free hosting. During weekday school hours, an automated health check helps keep the backend awake. Outside those hours, the first request may take up to a minute while the service starts. If the login page feels slow at first, please give it a moment and try again.

## Branding it for a school

Everything a school sees — the logo on every screen, the name on every report card,
and the colour of the whole interface — comes from one folder at the root:

```bash
cp ~/their-logo.svg branding/logo.svg   # their logo
$EDITOR branding/brand.json             # their name and accent colour
pnpm brand                              # apply it everywhere
```

There is no second place to remember. See [branding/README.md](branding/README.md).

## Documentation

- [Builder's Handbook](docs/HANDBOOK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision Log](docs/DECISIONS.md)
- [Privacy Data Map](docs/PRIVACY-DATA-MAP.md)
- [Security Model](docs/SECURITY.md)
- [Operations Runbook](docs/RUNBOOK.md)
- [Branding](branding/README.md)

The handbook explains how the project is built one step at a time. The architecture document covers the reasoning behind the system, while the decision log records important project choices.

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
set repository variable `DEMO_KEEPALIVE_ENABLED=true` only on the repository that
owns the hosted demo. Set `DEMO_RESET_ENABLED=true` after adding `DEMO_OPS_TOKEN`
with the demo API's configured operations token. Manual runs still validate the
required secrets and report missing configuration as a failure. An unset flag
means the scheduled job is skipped, not that a reset or backup succeeded.

Legacy copies with `backup.yml` must configure `PG_DUMP_URL`,
`GDRIVE_SERVICE_ACCOUNT_JSON`, and `GDRIVE_BACKUP_FOLDER_ID` before setting
`BACKUP_ENABLED=true`. A copied repository should not duplicate another
repository's demo reset, keepalive, or backup schedule.
