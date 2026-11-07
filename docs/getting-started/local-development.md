# Local development

This covers the synthetic local stack and sign-in; read this when installing the repository or diagnosing a local startup failure. All commands start at the repository root unless a directory is specified.

## Prerequisites

| Tool             | Repository requirement                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------- |
| Node.js          | `26.8.1` in `.node-version`; root engine range `>=26 <27`                                   |
| pnpm             | `11.25.0` in `package.json`; engine range `>=11 <12`                                        |
| Python           | `3.13` in `apps/backend/.python-version`; project allows `>=3.13`                           |
| uv               | Python environment/lockfile manager; Dockerfile pins `0.13.6`; no local minimum is declared |
| Docker + Compose | Docker daemon and Compose plugin with `up --wait`; no engine/plugin version is pinned       |
| Services         | Compose supplies PostgreSQL `18-alpine` and Redis `8-alpine`                                |

Install pnpm explicitly into your active Node installation (`npm install --global pnpm@11.25.0`); do not assume Node bundles Corepack. Install WeasyPrint's native libraries/fonts for your OS. The verified container package list is in `apps/backend/Dockerfile`: Pango, PangoFT2, HarfBuzz subset, and DejaVu fonts. PostgreSQL client 18 is also needed for backup work, not ordinary API startup.

## Install and initialize

```sh
pnpm install --frozen-lockfile
pnpm brand
pnpm dev:services
```

`pnpm install` runs `prepare` to install Lefthook. Compose exposes Postgres on `5432`, Redis on `6379`, and persists Postgres in the `pgdata` volume. It creates database `flrc`, not `flrc_test`.

From `apps/backend`:

```sh
uv sync --frozen
cp .env.example .env
uv run alembic upgrade head
uv run flrc seed --my-email admin@example-school.k12.tr
```

Keep `.env` untracked. For a completely synthetic/no-Google environment, keep the example local database/Redis URLs, set `ALLOWED_GOOGLE_DOMAIN=example-school.k12.tr`, and use the test-mode login below. Environment variables override `.env`; settings resolve `.env` relative to the process working directory. See [configuration](../reference/configuration.md) for every setting.

`seed` creates four academic years (three archived, one active), two semesters each, named Hazırlık classes and grade 1–8 classes, synthetic teachers and students, assignments, yearly enrollments/languages, programme-specific report columns, and sample values/comments. Student identities carry across applicable years; the active year's first semester is open and filled, second locked and empty. The source of the deterministic class allocation is `seed_class_plans()` in `apps/backend/src/flrc/cli.py`. Ordinary seed is **not** an upsert; use an empty disposable database. Never run seed/reset against a school database. The smaller destructive `seed-e2e` dataset is for [browser tests](../development/testing.md), not the full demo.

## Run the processes

```sh
pnpm dev
```

This applies branding, waits for Compose services, and runs workspace `dev` scripts through Turbo. Alternatively run each `pnpm --filter @flrc/backend dev`, `pnpm --filter @flrc/teacher dev`, and `pnpm --filter @flrc/admin dev` in separate terminals after starting services.

| Process       | URL / command                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Teacher Vite  | `http://localhost:5173/`                                                                                                  |
| Admin Vite    | `http://localhost:5174/admin/`                                                                                            |
| API           | `http://localhost:8000/api/healthz`; development schema UI `/api/docs`                                                    |
| Celery worker | From `apps/backend`: `uv run celery -A flrc.workers.celery:celery_app worker --pool=solo --concurrency=1 --loglevel=info` |

The root dev command does **not** start Celery. Run the worker with the same database/Redis configuration for multi-class report jobs and year XLSX exports. Browser requests must use each frontend's same-origin `/api` proxy, not call port 8000 directly. See [reports and jobs](../architecture/reports-and-jobs.md).

## Sign in with Google

1. Create a Google Cloud project, configure an OAuth consent screen, and create a **Web application** OAuth client. An External development client in testing needs the intended account in its test-user list; an eligible Workspace project can use an Internal client.
2. Register `http://localhost:5173/api/auth/callback` exactly, with no trailing slash. The callback is built from `FRONTEND_ORIGIN`, not the backend listener address.
3. In `apps/backend/.env`, use `ENV=dev`, set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to the Web application client's credentials and `ALLOWED_GOOGLE_DOMAIN` to the account's Workspace domain; retain frontend/admin origins matching the table above.
4. Seed with `--my-email` matching the actual Workspace account, **only in your local untracked environment**, or use `flrc bootstrap-admin --email ... --name ...` on an empty account setup. Restart the API after setting changes.
5. Open the teacher frontend and choose Google sign-in. Successful OAuth returns to the teacher origin; administrators can switch panels.

Google success alone is insufficient: callback checks verified email, a valid subject, the `hd` claim, matching email domain, an active allowlist row, and the bound Google subject. A consumer Gmail account does not satisfy the normal Workspace-domain path. Never relax these checks to make local login work; use the explicit test path instead.

## Sign in without Google

Use only a synthetic local database. In `apps/backend/.env` set:

```dotenv
ENV=test
E2E_AUTH_SECRET=local-synthetic-login-secret
```

Restart the backend. Open `http://localhost:5173/login`, then run in that page's developer console:

```js
await fetch("/api/test/session", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-e2e-secret": "local-synthetic-login-secret",
  },
  body: JSON.stringify({ email: "admin@example-school.k12.tr" }),
});
location.assign("/");
```

The email must exactly match an existing **active** user. The endpoint creates a Redis session and sets the normal HttpOnly cookie; it does not create users or simulate Google claims. `ENV=test` alone is insufficient: the secret must be nonempty and match the header. Missing user, wrong secret, or disabled secret returns 404; the route is only registered in test mode. Never configure this secret in school deployments. Playwright uses the same path via `e2e/helpers/auth.ts`.

## Regenerate API types

From the root, run `pnpm generate` after changing API request/response models or routes. It exports FastAPI OpenAPI and then runs the client generator; no listening server is needed. Commit generated changes under `packages/api-client` together with the source. See [the endpoint recipe](../development/how-to.md#add-an-api-endpoint).

## Common problems

| Symptom                        | Inspect / fix                                                                                        |
| ------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Docker socket permission error | Ensure daemon access and active group membership; re-login after changing groups                     |
| Port 5432 or 6379 occupied     | Identify the existing service before changing mappings; pytest still hardcodes port 5432             |
| Settings seem ignored          | Run backend commands from `apps/backend`; remove conflicting exported variables; restart the process |
| Google redirect mismatch       | Compare console URI with `FRONTEND_ORIGIN + /api/auth/callback`, including scheme/port               |
| OAuth denied after Google      | Check consent test users, Workspace `hd`, allowlist/active status, then identity binding             |
| Session missing                | Check Redis, cookie host, and frontend proxy; do not mix `localhost` and `127.0.0.1` in browser URLs |
| `bad_origin` on writes         | Match backend origins to frontend origins, without `/admin/` in `ADMIN_ORIGIN`                       |
| Jobs never complete            | Start Celery using the same configuration; inspect persisted job state                               |
| PDF native-library error       | Install the libraries in the backend Dockerfile; do not replace the renderer                         |
| Duplicate rows when seeding    | Ordinary seed expects an empty disposable database; see the CLI warning before resetting             |

For isolated ports and disposable test databases, follow [testing](../development/testing.md). For a realistic school-mode playground, see [self-hosting](../operations/self-hosting.md); it is separate from this development setup.
