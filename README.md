# FL-ReportCard

FL-ReportCard is a grade-entry and report-card system for schools. Teachers enter grades in a
keyboard-first grid that also works on a phone; administrators manage years, classes, students,
teachers and assessment columns, and print report cards. Every grade change is audited.

- **Teacher app:** grade grid per class and subject (desktop table or one-student stepper on a
  phone), 1-2-3 skill ratings and comments, conflict-safe saving with undo, class reports for
  parent meetings, report-card previews.
- **Admin app:** dashboard of term progress and setup issues, class workspaces (rosters, school
  numbers, second languages, columns, assigned teachers), teaching assignments, academic-year
  lifecycle and rollover, student import, teachers and access, report-card centre with background
  PDF jobs, audit history, seven-day undo of admin changes, archive of closed years.
- **Backend:** FastAPI, Postgres, Redis sessions, Celery worker for PDFs and exports, Google
  sign-in, nightly encrypted backups for school installations.

The user interface is Turkish-first and also available in English, German and French.

## Try the public demo

Open **[flrc.suatsulun.com/demo](https://flrc.suatsulun.com/demo)** and sign in with any Google
account. You get a temporary administrator account (up to 24 hours) in a fictional school with four
years of synthetic classes, students and grades, and you can switch between the admin and teacher
panels. Everyone shares the same fictional school, and it resets to its original state every night
at 00:00 (Europe/Istanbul). The demo runs on free hosting, so the first request after a quiet
period can take up to a minute. Use fictional data only.

What to try and how the demo handles your data:
[docs/getting-started/using-the-demo.md](docs/getting-started/using-the-demo.md).

## Run it locally

You need Node (version in [`.node-version`](.node-version)), pnpm (version in `package.json`'s
`packageManager`), Python 3.13 with [uv](https://docs.astral.sh/uv/), and Docker with Compose.

```bash
pnpm install --frozen-lockfile
(cd apps/backend && uv sync --frozen && { [ -f .env ] || cp .env.example .env; })
pnpm dev:services                      # Postgres and Redis in Docker
(cd apps/backend && uv run alembic upgrade head && uv run flrc seed --my-email you@yourschool.k12.tr)
pnpm dev                               # teacher, admin and API with live reload
```

Then open the teacher app at <http://localhost:5173> and the admin app at
<http://localhost:5174/admin/> (the API runs on port 8000). Signing in needs either a Google OAuth
client for local development, or the test sign-in that works without Google. PDF and export jobs
need the Celery worker as well. All of this, including environment variables, the worker and
common problems, is in
**[docs/getting-started/local-development.md](docs/getting-started/local-development.md)**.

Checks before you push: [docs/development/testing.md](docs/development/testing.md).

## Running it for a school

Each school runs its own installation from the released `flrc-backend` and `flrc-web` images or
from source, with its name, logo, report templates and signatures in a private deployment
repository. Nothing school-specific lives in this public repository. Start with
[docs/operations/self-hosting.md](docs/operations/self-hosting.md) and
[docs/operations/deployment.md](docs/operations/deployment.md).

## Documentation

Everything is in **[docs/](docs/README.md)**: getting started, architecture, design system,
development conventions and testing, operations, security, reference material and the
[architecture decision records](docs/adr/README.md). Coding agents start at
[AGENTS.md](AGENTS.md); contributors at [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository layout

```text
apps/teacher     React app for teachers
apps/admin       React app for administrators (served under /admin/)
apps/backend     FastAPI API, Celery worker, CLI, migrations and tests
packages/ui      Shared design system and components
packages/api-client  TypeScript client generated from the API's OpenAPI document
packages/i18n    Translations (tr, en, de, fr)
e2e              Playwright browser tests
branding         Generic application branding and the rebranding tool
infra            Compose, web server and hosting definitions
docs             Documentation
```

## Privacy

FL-ReportCard handles children's school records. This repository, its tests, screenshots and the
public demo contain synthetic data only; real student or school data must never be committed. See
[docs/security/privacy-data-map.md](docs/security/privacy-data-map.md).

## License

[MIT](LICENSE).
