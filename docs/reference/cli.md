# CLI and package scripts

This lists maintenance commands and root package scripts; read this when choosing a repository command or checking whether it mutates data. Backend source is `apps/backend/src/flrc/cli.py` and `modules/backup/cli.py`; run `uv run flrc ...` from `apps/backend` so `.env` and project configuration resolve correctly.

## Maintenance commands

Typer exposes options in kebab-case. Run `uv run flrc --help` or `uv run flrc <command> --help` for runtime help. Arguments below are positional only where marked; other parameters are options.

| Command               | Arguments / options                                                                                      | Effect and boundary                                                                                                                                                                                                                                                                            |
| --------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `seed`                | `--seed-value INTEGER` (42), `--my-email TEXT` (`you@yourschool.k12.tr`), `--demo` / `--no-demo` (false) | Creates the full deterministic fictional school; normal mode adds an administrator and is not idempotent. See [seed contents](../getting-started/local-development.md#install-and-initialize). Never use on school data.                                                                       |
| `seed --demo`         | Same options                                                                                             | Requires `ENV=demo`; fills empty academic data using its existing eligible admin or creates a synthetic seed admin. Advisory lock serializes starts; skips when academic/student data exists or the existing-admin prerequisites do not match.                                                 |
| `seed-e2e`            | None                                                                                                     | **Deletes application rows** then creates the small deterministic synthetic E2E school, users, classes, terms, columns and values. Reseed before each browser suite; never point at a school database.                                                                                         |
| `reset`               | None                                                                                                     | **Deletes all application rows** in child-before-parent order; does not downgrade schema or clear Redis. Docstring says dev-only, but the implementation has **no ENV guard or confirmation prompt**.                                                                                          |
| `bootstrap-admin`     | Required `--email TEXT`, `--name TEXT`                                                                   | Creates/reactivates the first allowlisted admin. Email is normalized and must match configured domain; stripped name needs two characters. Refuses when another active admin exists; repeating for the sole existing active admin is a no-op. Later accounts belong in authenticated admin UI. |
| `make-import-fixture` | `--out PATH` (`tests/fixtures/roster-hostile.xlsx`)                                                      | Writes a synthetic hostile roster workbook for importer tests; overwrites the chosen output file through the fixture writer.                                                                                                                                                                   |
| `purge-job-outputs`   | None                                                                                                     | Removes expired persisted outputs and incomplete report-set parts through job service maintenance.                                                                                                                                                                                             |
| `purge-admin-actions` | None                                                                                                     | Deletes expired seven-day admin-undo rows/snapshots/kept images; not grade audit-history deletion. Backup scheduler also performs this maintenance.                                                                                                                                            |

No command listed as destructive should be assumed protected by API startup validation. Confirm the target database before running reset, seed, or maintenance commands. Ordinary seed and E2E seed are different datasets, not interchangeable tests of production readiness.

## `flrc backup`

| Subcommand     | Arguments                                     | Effect                                                                                                                               |
| -------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `keygen`       | None                                          | Prints `BACKUP_AGE_RECIPIENT` and secret `BACKUP_AGE_IDENTITY`; protect terminal/output history and store identity securely          |
| `run`          | None                                          | Dumps, encrypts, uploads, prunes retained dumps, and records status                                                                  |
| `restore-test` | None                                          | Downloads newest dump, verifies/decrypts/restores into a scratch database, checks it, prints JSON outcome; requires private identity |
| `archives`     | None                                          | Uploads bundles for archived academic years that have no bundle yet                                                                  |
| `archive-year` | Required positional `LABEL`, e.g. `2026-2027` | Builds/uploads a year's bundle even if one exists already                                                                            |
| `schedule`     | None                                          | Long-running sidecar loop; nightly maintenance/backup at configured local time, monthly restore tests and year archives              |
| `status`       | None                                          | Prints the local backup status file as JSON                                                                                          |

Store-using commands require `GDRIVE_SERVICE_ACCOUNT_JSON`, `GDRIVE_BACKUP_FOLDER_ID`, and `BACKUP_AGE_RECIPIENT`. `restore-test` additionally requires `BACKUP_AGE_IDENTITY`. `status`/`keygen` do not require a Drive store. These commands need operational prerequisites such as PostgreSQL client 18 and scratch-database privileges; follow [backups and restore](../operations/backups-and-restore.md), not a production trial-and-error sequence.

## Root pnpm scripts

| Script (`pnpm <name>`) | Expansion / effect                                                                               |
| ---------------------- | ------------------------------------------------------------------------------------------------ |
| `dev`                  | `dev:services` then `dev:apps`; starts local infrastructure and workspace servers                |
| `predev`               | Applies branding with `node scripts/branding.mjs`                                                |
| `dev:services`         | `docker compose -f infra/compose/compose.dev.yaml up -d --wait`                                  |
| `dev:apps`             | `turbo run dev`; does not start Celery                                                           |
| `build`                | `turbo run build`                                                                                |
| `prebuild`             | Applies branding before builds                                                                   |
| `lint`                 | `turbo run lint`                                                                                 |
| `typecheck`            | `turbo run typecheck`                                                                            |
| `format`               | `prettier --write .`; **rewrites** supported files repository-wide                               |
| `format:check`         | `prettier --check .`                                                                             |
| `test`                 | `turbo run test`; includes destructive shared-database backend pytest, not frontend unit tests   |
| `e2e`                  | `playwright test`; needs running seeded stack                                                    |
| `e2e:ui`               | `playwright test --ui`; same stack prerequisites                                                 |
| `generate`             | Backend OpenAPI export, then `@flrc/api-client` `openapi-ts`; rewrites generated contract/client |
| `prepare`              | `lefthook install`; installs git hooks during dependency setup                                   |
| `brand`                | `node scripts/branding.mjs`; writes generated branding outputs                                   |
| `brand:check`          | Branding generator `--check`; verifies drift without writing                                     |
| `brand:test`           | Node test runner for `scripts/branding.test.mjs`                                                 |
| `i18n:check`           | `node scripts/check-i18n.mjs`                                                                    |
| `telemetry:test`       | Node test runner for `scripts/telemetry.test.mjs`                                                |

Lifecycle entries `predev`/`prebuild` are defined alongside their target scripts. Use the existing root commands for complete setup instead of assuming a filtered Vite start also syncs branding or starts services.

## Focused package commands

Use `pnpm --filter @flrc/<package> <script>`. Teacher/admin support `dev`, `build`, `lint`, `preview`, and `typecheck`; neither defines `test`. Backend maps `dev` to `uv run fastapi dev src/flrc/main.py`, lint to Ruff check/format check, typecheck to mypy, test to pytest, and generate to the OpenAPI export script. UI supports lint/typecheck; i18n supports typecheck/test (locale checking); API client supports typecheck/generate.

Turbo caches ordinary tasks, orders build/typecheck/test after dependency builds, and treats dev as persistent/uncached and generation as uncached (`turbo.json`). Do not use cached task output as proof that a live database or browser stack was exercised. See [testing](../development/testing.md) for serial database runs and isolated browser ports.
