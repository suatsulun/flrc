# Infrastructure

Deployment orchestration belongs here; application-specific Dockerfiles stay beside the
applications they build.

Layout:

```text
infra/
├── compose/
│   └── compose.dev.yaml           (local PostgreSQL + Redis)
├── school-template/               (starting content of a school's private deployment repo:
│   ├── compose.yaml                pinned images, API/worker/backup/web, DB/Redis, migration job)
│   ├── .env.example
│   ├── branding/
│   └── .github/                   (Dependabot bumps, SSH deploy, backup freshness check)
├── hetzner/
│   └── cloud-init.yaml            (server first boot: Docker, firewall, updates, users)
├── web/
│   ├── Dockerfile                 (flrc-web: Caddy + both SPAs + /api proxy + branding)
│   └── Caddyfile
├── cloudflare/                    (managed school gateway)
├── vercel/                        (public demo: one Vercel project serving both SPAs and the
│                                   /api rewrite; see its README)
└── render/
    └── render.yaml
```

The school-hosted runbook is [docs/SELF-HOSTING.md](../docs/SELF-HOSTING.md).

The development Compose file runs PostgreSQL 18 and Redis 8. The school template defines the
current VM topology with published images. Managed and self-hosted deployments share application
settings; provider configuration remains specific to each profile. Relevant handbook steps:
1.4, 1.11, and 4.5/4.9.

As of the 2026-09-11 source review, template image pins use 1.2.0. The current HEAD and uncommitted
changes extend the local 1.2.0 tag; see [release notes and gates](../docs/RELEASING.md). Inspect the
pending `82a91f4c6d30` migration before the next release. Editing docs or source does not apply it
to a database, restart a server, or publish an image.

## Public demo web project

The demo web tier is the single Vercel project described in [infra/vercel/README.md](vercel/README.md)
(ADR-064): Root Directory `infra/vercel`, both SPAs assembled into one output, `/api/*` rewritten
to the Render API, and the public domain attached to that project alone. Production builds link
the panels to `/admin/` and `/`, so no cross-link environment variables are needed.

## Demo database migrations

The Vercel demo uses `ENV=demo` on its Render API service. Its default Docker command runs
`bin/start-api.sh`, which applies `alembic upgrade head` to the explicitly configured
`DATABASE_URL_DIRECT` before starting the API. Set that URL to the same demo Neon branch as
`DATABASE_URL`, using the direct endpoint and the asyncpg URL format (`?ssl=require`). This
updates existing data; a failed migration prevents the new API from starting.

After migrations, `flrc seed --demo` loads the same fictional school as the local seed: four
academic years, 52 classes and 1,144 enrollments per year, 28 teachers, grades, and report comments.
It runs only when there are no academic years or students and exactly one active admin from
`ALLOWED_GOOGLE_DOMAIN`, with the middle-school English teaching profile. That existing account
receives the seed's teaching assignments; its identity, Google login binding, and roles are kept.
This mode does not create another admin or change the existing admin's email.

Restarts skip an existing dataset, preserving demo edits. Seeding uses one transaction and a
database lock so concurrent starts cannot create duplicate datasets; a failed seed rolls back and
prevents startup. If the initial admin is missing or ambiguous, the API starts without seeding and
logs the reason. For a new demo, provision the admin with `flrc bootstrap-admin`, then restart the API.
`flrc seed --demo` refuses to run outside `ENV=demo`.

Leave Render's Docker Command override empty to use the image default. Other environments run
migrations as an explicit deployment step. The school blueprint below remains `ENV=school`;
do not attach the Vercel demo to that blueprint's environment settings.

## Demo visitor accounts

`DEMO_PUBLIC_LOGIN=true` (accepted only with `ENV=demo`) lets any verified Google account sign in
as a temporary administrator of the shared synthetic school (ADR-051). Keep
`ALLOWED_GOOGLE_DOMAIN` on the synthetic seed domain, `example-school.k12.tr`: visitor accounts
and any users they create use it, so no real address is stored. Set `SESSION_TTL_SECONDS=86400`
so one session may last the full 24-hour visitor lifetime, and optionally
`DEMO_VISITOR_LIMIT_PER_DAY` (default 500). The demo OAuth client's consent screen must be
published to production first; Google's Testing status admits only listed test users. With the
flag set, the API refuses to start unless the nightly reset below is configured, because visitor
edits would otherwise accumulate until a manual `flrc reset` and reseed.

## Nightly demo reset

The demo database is a Neon child branch of a pristine, seeded parent (ADR-052). At local
midnight the branch is restored from that parent in seconds; the branch id, compute, and
connection strings do not change.

1. In the Neon project, keep `main` as the golden branch and create a child branch named `demo`
   with `main` as its parent. Note the project id and both branch ids from the console URLs or
   `neonctl branches list`. Create a project-scoped API key.
2. On the Render API service set `DATABASE_URL` and `DATABASE_URL_DIRECT` to the `demo` branch
   (pooled and direct), `DATABASE_URL_GOLDEN_DIRECT` to the direct URL of `main`, the four
   `NEON_*` values, and an `OPS_TOKEN` from `openssl rand -base64 48`. `DEMO_RESET_TIMEZONE`
   defaults to `Europe/Istanbul`.
3. Add the same token as the `DEMO_OPS_TOKEN` repository secret. The `demo-reset.yml` workflow
   posts to `/api/ops/demo/reset` at 00:00 Istanbul time and polls `/api/ops/demo/status` until
   the day's reset is recorded. Manual runs use `workflow_dispatch`.
4. On start, the API migrates and, if empty, seeds `main`, then migrates `demo`. The in-process
   self-heal loop notices that no reset is recorded for today and performs the first restore
   within a minute; it does the same after a missed schedule or a cold start.
5. Publish the demo OAuth consent screen, then set `DEMO_PUBLIC_LOGIN=true`.

During a reset, every data route answers `503 demo_resetting` for a few seconds, all sessions are
revoked, and visitors sign in again afterwards. The reset date, lock, and last error live in
Redis under `demo:reset:*`; `GET /api/ops/demo/status` with the `X-Ops-Token` header shows them.
Neither the ops token nor the Neon key ever reaches logs or telemetry.

Scheduled reset and keepalive workflows require `DEMO_RESET_ENABLED=true` and
`DEMO_KEEPALIVE_ENABLED=true`, respectively, in the repository that owns the demo. A skipped
workflow does not prove the operation ran. School backup scheduling lives in the private Compose
deployment; this repository has no root `backup.yml` workflow.

## Managed school boundary

`cloudflare/worker.js` is the only public path router for school production. It redirects HTTP to
HTTPS, adds security headers, disables browser caching for API/navigation responses, and overwrites
`X-Flrc-Gateway` with its encrypted `GATEWAY_SECRET` binding before proxying `/api/*`. The API
in `ENV=school` refuses every non-health request that does not carry the matching secret.

Never place the secret in `wrangler.toml`. Use `wrangler secret put GATEWAY_SECRET` and store
the same value in Render's encrypted environment. See [the security model](../docs/SECURITY.md)
before deploying.
