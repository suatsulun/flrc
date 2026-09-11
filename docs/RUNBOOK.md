# Production launch and operations runbook

Production public origin: `https://flrc.school.k12.tr` (replace this documented placeholder with the school-approved host before launch). Named owners must be filled in before real data: school controller, technical operator, Workspace administrator, and incident lead.

Relevant handbook steps: 4.5 and 4.8-4.11. This is a procedure, not a launch record. The
2026-09-11 source snapshot and pending validation are in [TODO.md](TODO.md). For a school VM,
follow [SELF-HOSTING.md](SELF-HOSTING.md) and its Caddy/Compose services; Cloudflare/Render steps
below apply only to the managed profile.

## T-7 days

- Confirm Neon, Upstash, Google Drive, Cloudflare, Render, GitHub, Sentry, and OAuth projects are school-controlled and region/processor choices are approved.
- Review [SECURITY.md](./SECURITY.md), enable Cloudflare “Always Use HTTPS,” and confirm the
  encrypted `GATEWAY_SECRET` binding matches Render without printing either value.
- Review [PRIVACY-DATA-MAP.md](./PRIVACY-DATA-MAP.md) with the controller.
- Complete and record a fresh restore in [RESTORE-DRILLS.md](./RESTORE-DRILLS.md).
- Print all four synthetic report sets (primary English, middle English, German, French) on the
  school printer; check duplex pairing, private cover replacement, and stage-specific signers.
- Have one coordinator and one admin complete acceptance checks. Freeze non-blocking schema changes.

## T-1 day

Run from repository root:

```bash
pnpm generate
pnpm turbo run lint typecheck test build
cd apps/backend
uv run alembic current
uv run alembic heads
```

Run code checks on the development/CI test environment: pytest wipes the fixed local `flrc_test`
database. Inspect the target deployment's `alembic current` separately, using its operator context;
local output does not prove production is migrated. `current` and the release's `heads` must
agree after migration. Tag the reviewed release only after CI is green.

For school-hosted backup, run `docker compose run --rm backup flrc backup run` from the private
deployment directory and record the successful filename/checksum. There is no root backup
workflow in this application repository. Verify secret presence in provider dashboards without
printing values. Confirm the production-only absence of the test endpoint:

```bash
curl -i https://flrc.school.k12.tr/api/test/session
# Expected: 404
```

Also run the anonymous boundary checks from [SECURITY.md](./SECURITY.md). `/api/me` must return
401 through the public gateway, the direct Render API must return 404, OpenAPI/docs must return
404, and an unsafe request without Origin must return 403.

## Launch window

1. Announce the pilot window and take a pre-launch backup.
2. Run `uv run alembic upgrade head` once using the direct database URL.
3. If this is the first launch, create the sole bootstrap allowlist entry:
   `uv run flrc bootstrap-admin --email <school-email> --name "<administrator name>"`.
4. Deploy API, worker, teacher SPA, admin SPA, then the fixed-origin gateway.
5. Verify `GET /api/healthz` returns 204 with an empty body and worker `GET /health` returns 200.
6. Sign in with an allowlisted school account; verify `/api/me`, shared `/admin` navigation,
   logout, and login. Verify a school-domain account absent from the allowlist is denied.
7. Save one approved pilot grade, exercise one deliberate conflict, lock/reject a write,
   generate/download one report, and trigger one backup.
8. In a synthetic or disposable year, verify that a reused school number is accepted in a different
   year, archived tables show the original number, and a setup year cannot activate with missing
   promoted-student numbers.
9. Verify the admin class table, same-grade drag move, teacher-field assignment guard, and
   light/dark themes with an occasional computer user.
10. For a release containing ADR-063, verify grades 5-8 English omit comments in grids, archives,
    history, and newly generated PDFs, while audit/workbook exports preserve the retained records.
    Verify primary English and German/French comments still work.
11. Open first to pilot teachers, then broader staff.

Abort immediately for cross-user data, silent grade overwrite, locked/archive mutation, importer preview/commit divergence, wrong-student reports, non-allowlisted OAuth access, or migration revision disagreement.

## Rollback

Redeploy the previous known-good API/worker image and frontend releases. Do not reflexively downgrade a production schema. Prefer a forward fix. If a destructive change occurred, restore the pre-launch dump into a new database, verify it, and switch credentials under the [incident runbook](./INCIDENT-RUNBOOK.md).

For the pending `82a91f4c6d30` migration, an Alembic downgrade does not reactivate retired
middle-English fields. An older image cannot by itself restore their active flags. Preserve the
rows and plan a reviewed forward correction if reversal is required; do not bulk-enable columns
that an administrator may have independently disabled.

## First school week (daily)

Check API health/error rate, worker failures, Redis health, database storage/connections, and last successful Drive backup. In Postgres, inspect machine-only job state:

```sql
select id, kind, status, created_at, started_at
from job_runs
where status in ('queued','running')
  and created_at < now() - interval '30 minutes'
order by id;

select id, kind, error_code, created_at
from job_runs
where status='failed'
order by id desc
limit 20;
```

Spot-check structured logs for the absence of names, email, school numbers, grades, cookies,
gateway secrets, and request bodies.

## Recurring work

- Monthly: dependency/container update, `flrc purge-job-outputs`, access-role review, missing assignments, completeness anomalies.
- Before year close: confirm both semesters are locked, store the audit export, then verify the
  automatically created next year and its fresh sequential student numbers. Resolve any missing
  or school-approved replacement numbers only in the setup year; never rewrite the archived year.
- Quarterly or per school policy: scratch restore drill, incident tabletop, privacy/retention review, OAuth and service-account access review.

`/api/healthz` is public and intentionally returns 204 with an empty body. School mode also permits
OAuth start/callback, the origin-protected logout endpoint, and static login assets without a
session. Demo-only exceptions are listed in [SECURITY.md](SECURITY.md). Never expose student
payloads in an operations endpoint.
