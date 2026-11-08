# Operating the public demo

This document describes the public demo's hosting, pseudonymous visitors and reset baseline. Read this when maintaining the demo; visitors should start with [Using the demo](../getting-started/using-the-demo.md). Never apply these reset/seed procedures to a school's database.

## Hosting pieces

| Piece        | Repository contract                                                                                                                                                                           |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public web   | One Vercel project, Root Directory `infra/vercel`; `vercel.json` builds `@flrc/demo-web`, serves teacher at `/`, admin at `/admin`, landing at `/demo`, and proxies `/api/*` to the demo API. |
| Assembly     | `infra/vercel/assemble.mjs` combines both SPA outputs and static landing/privacy/terms pages. It checks the admin asset base and rejects bundled development panel URLs.                      |
| API / worker | Backend Docker image on Render; worker command `./bin/start-worker-web.sh`, API health `/api/healthz`, worker health `/health`. Free instances can cold-start.                                |
| Database     | Neon live demo child branch restored from a separate pristine golden branch. Application pooled URL and direct migration/seed URL target the live branch.                                     |
| Redis        | Session store, visitor/rate counters, reset lock/status and Celery broker; use a namespace isolated from school data.                                                                         |
| Identity     | Google Web OAuth callback at the public frontend origin's `/api/auth/callback`.                                                                                                               |

The intended public landing URL is [https://flrc.suatsulun.com/demo](https://flrc.suatsulun.com/demo). Provider deployment state is not encoded in these docs. `infra/render/render.yaml` defaults to **ENV=school**, so it cannot be imported unchanged as demo configuration. The demo follows the public application repository rather than private school assets ([ADR-064](../adr/064-one-vercel-project-serves-the-public-demo.md)).

Leave production panel URL overrides unset: builds default to `/admin/` and `/`. Set both backend frontend/admin origins to the single public origin. Never send visitors to Vite localhost URLs or a separate admin origin.

## Demo settings

See `apps/backend/src/flrc/config.py` and [Configuration](../reference/configuration.md) for the full settings contract.

| Setting                                        | Demo requirement                                                                        |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| `ENV`                                          | `demo` for API and worker                                                               |
| `DEMO_PUBLIC_LOGIN`                            | `true` for verified Google visitors                                                     |
| `ALLOWED_GOOGLE_DOMAIN`                        | Synthetic domain for generated local accounts; not a visitor's real email domain        |
| `SESSION_SECRET`                               | Stable private signing/HMAC secret; never the development default                       |
| `SESSION_TTL_SECONDS`                          | Between 900 and 86400 with public visitors; use 86400 for a full-day session budget     |
| `DEMO_VISITOR_LIMIT_PER_DAY`                   | Default 500 new visitor-account attempts                                                |
| `NEON_API_KEY`, `NEON_PROJECT_ID`              | Credential scoped to the demo project and its project id                                |
| `NEON_DEMO_BRANCH_ID`, `NEON_GOLDEN_BRANCH_ID` | Distinct live and pristine branch ids; never a school branch                            |
| `DEMO_RESET_TIMEZONE`                          | Default `Europe/Istanbul`                                                               |
| `OPS_TOKEN`                                    | Private random operations token, at least 32 characters with sufficient diversity       |
| `DATABASE_URL_GOLDEN_DIRECT`                   | Startup-script variable for migrating/seeding the golden branch; not a `Settings` field |

Public login is refused outside `ENV=demo` and requires all four Neon settings. Partial Neon reset configuration is refused. The [visitor model](../adr/051-public-demo-visitors-are-pseudonymous-temporary.md) grants temporary admin/coordinator roles, protects other visitor accounts, and restricts managed accounts to the synthetic domain. Sessions are bounded by both configured session TTL and the account's 24-hour absolute lifetime. The daily visitor counter currently uses UTC dates; the reset schedule uses Istanbul time. Counter-store failure is fail-open in demo mode, unlike school operation-limit failures.

## Golden baseline and nightly reset

[ADR-052](../adr/052-the-demo-resets-nightly-by-restoring-a-neon-branch-from-its.md) replaces repeated destructive row-by-row reseeding with branch restore.

`apps/backend/bin/start-api.sh` in demo mode:

- requires the live `DATABASE_URL_DIRECT`;
- when `DATABASE_URL_GOLDEN_DIRECT` is set, migrates the golden branch, runs `flrc seed --demo` against it, then migrates the live branch;
- otherwise migrates/seeds the live branch itself. `seed --demo` only populates an empty academic database; it **does not refresh existing populated data**.

The API lifespan starts `modules/demo/reset.py:self_heal_loop`. It checks every 60 seconds whether today's reset is missing, retries failed resets after ten minutes, and catches up after a cold start. A Redis lock/state marker has a 15-minute TTL. While restoring, non-exempt API data requests receive 503 `demo_resetting` with `Retry-After: 10`.

A reset restores the live branch from the **current golden head**, waits for Neon operations/database readiness, disposes the API connection pool, removes session/index/visitor/rate-counter keys and records the successful local date. It does not flush all Redis keys or promise to cancel previously queued Celery work. Avoid baseline maintenance while reports are running.

## Automation and operations endpoints

| Workflow                           | Trigger / enable flag                                                                                                        | Credentials / result                                                                                                                            |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `.github/workflows/demo-reset.yml` | 00:00 `Europe/Istanbul`; scheduled only with `DEMO_RESET_ENABLED=true`; manual dispatch bypasses flag                        | Secret `DEMO_OPS_TOKEN` must match API `OPS_TOKEN`. POST reset accepts 202 or 409 (already busy), then polls status for idle with today's date. |
| `.github/workflows/keepalive.yml`  | Every 10 minutes, weekdays 05:00–14:59 UTC; scheduled only with `DEMO_KEEPALIVE_ENABLED=true`; manual dispatch bypasses flag | Calls the API's empty health endpoint; no secret. Does not guarantee the worker stays awake.                                                    |

Demo-only `POST /api/ops/demo/reset` and `GET /api/ops/demo/status` require `X-Ops-Token`. These token-authenticated operations bypass browser Origin checks. Public `GET /api/demo` exposes next reset/lifetime information, not operations state or credentials; it returns `null` outside demo mode. Never publish operations tokens in a browser build or shell transcript.

## Refresh the baseline

1. Plan a demo maintenance window and stop new activity/worker processing while replacing the baseline. Verify project and branch ids are demo-only and retain a recoverable previous golden branch.
2. Upgrade the golden branch schema using the intended application revision and direct URL. If only migrations are needed, keep the existing synthetic academic data; the seed command will skip it.
3. For a completely fresh seed, prepare a new **empty dedicated golden branch/database**, migrate it, and run `ENV=demo` / `flrc seed --demo` with its direct database URL and synthetic domain. Do not run `flrc reset` against a populated branch merely because its name looks familiar. Review synthetic records and programme coverage before adopting it.
4. Configure the chosen golden branch id and its direct startup URL consistently; keep the live branch URL pointing to the child, not the golden parent. Redeploy compatible API/worker versions.
5. Request an operations reset, inspect status for today's successful date/no error, then verify a fresh Google visitor, both panels, representative grade grids and a class PDF (the demo refuses background report sets). Resume the worker and public access after review.

If the baseline was accidentally edited with real data, contain the demo immediately and follow [Incident response](incident-response.md); a future nightly reset is not sufficient disclosure handling.
