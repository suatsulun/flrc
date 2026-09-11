# FL-ReportCard backend

The backend is one Python project with several process entry points: the FastAPI web API,
Celery workers, maintenance commands, imports, and report generation.

Application source lives in `src/flrc`. Business features live together under
`src/flrc/modules`; shared configuration and infrastructure stay outside feature modules.

School deployments are intentionally fail-closed. Read
[the security model](../../docs/SECURITY.md) before setting `ENV=school`; the API will refuse
to start until HTTPS origins, Google Workspace identity, trusted hosts, gateway isolation, and
strong secrets are configured.

## Development entry points

Relevant handbook steps: 1.3-1.9, 2.1-2.9, Phase 3, and Phase 4. Use Python 3.13 and uv;
run backend commands from this directory so `.env` and `alembic.ini` resolve correctly.

```bash
uv sync --frozen
uv run fastapi dev src/flrc/main.py
```

For a new local synthetic database, start the root development Compose services and apply
`uv run alembic upgrade head` before `uv run flrc seed`. Never reset or seed a school database.
To process year-export jobs, run a separate worker using the same database and Redis settings:

```bash
uv run celery -A flrc.workers.celery:celery_app worker --pool=solo --concurrency=1 --loglevel=info
```

PDF sets use `GET /api/reports/pdf`; whole-year XLSX exports use Celery and durable `job_runs`.
WeasyPrint needs the native libraries installed by `Dockerfile`. Missing native dependencies are
an environment failure, not a reason to substitute a different renderer.

## Source map

- `src/flrc/db/models.py`: sixteen mapped tables, including demo visitors and report identity audit.
- `src/flrc/modules/academics/programme.py`: assessment type rules for column editing, seed, and
  copies.
- `src/flrc/modules/grades/`: permissions, versioned saves, grants, and undo.
- `src/flrc/modules/administration/` and `src/flrc/modules/imports/`: enrollment identity,
  lifecycle, and roster review.
- `src/flrc/modules/reports/`: data builder, private overlays, HTML/PDF rendering.
- `src/flrc/modules/backup/`: encrypted school-owned backups and restore checks.
- `migrations/versions/` and `tests/`: schema history and synthetic regression coverage.

The 2026-09-11 working tree adds migration `82a91f4c6d30` after `7d26cb91a540` to deactivate
grades 5-8 English text columns while retaining values and audit history. Its downgrade does not
reactivate columns. This file's presence does not establish that any database has been migrated.

## Check

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/flrc
uv run alembic heads
```

Pytest uses the fixed local database `flrc_test` on port 5432, migrates it, and deletes its rows
between tests. `tests/test_migrations.py` also downgrades it to base. Create that disposable database
first and ensure no other test session is using it; changing `DATABASE_URL` alone does not redirect
the fixture. With that prerequisite satisfied, run `uv run pytest -q` or the focused paths in
[the AI handoff](../../docs/AI-HANDOFF.md). Redis is also needed by relevant integration tests.

From the repository root, `pnpm generate` exports OpenAPI and regenerates the TypeScript client.
Do not edit the generated contract by hand. See [the release checklist](../../docs/TODO.md) for
checks still pending against the current work.
