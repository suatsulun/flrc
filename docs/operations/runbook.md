# Routine operations

This document is the recurring checklist for a school operator. Read this during normal service operation or launch preparation; use [Deployment](deployment.md) for updates and [Incident response](incident-response.md) for suspected compromise or data corruption.

## Before accepting real data

- School controller, technical operator and incident lead are assigned privately; hosting, OAuth, backup and telemetry accounts are school-approved.
- Confirm the [security startup/deployment invariants](../security/security-model.md) and controller-approved [retention policy](../security/privacy-data-map.md).
- Complete a real [backup and isolated restore drill](backups-and-restore.md), including private report asset recovery.
- Follow [first-school provisioning](self-hosting.md#first-deploy-and-first-administrator), then verify a registered Google login and denial of an unregistered account.
- With synthetic/disposable records, verify conflict rejection, locked/archive immutability, importer preview/commit agreement, preview/PDF ordering, stage-specific signers and physical printer/duplex output. Never seed a live school to make this check easier.

## Daily health and queue inspection

Run in the private deployment directory:

```bash
docker compose ps
docker compose logs --since 1h api worker backup web
docker system df
```

Public `/api/healthz` is an empty 204; worker `/health` is 200. Check API errors, worker health, Redis availability, database connections/storage, disk space and the latest successful backup/restore status. Health endpoints do not prove grade correctness or job completion. Confirm new frontend shells are revalidated while hashed assets are cached; Caddy config handles this distinction.

Use aggregate/machine-only job inspection rather than opening blob contents:

```sql
select id, kind, status, created_at, started_at
from job_runs
where status in ('queued', 'running')
  and created_at < now() - interval '30 minutes'
order by id;

select id, kind, error_code, created_at
from job_runs
where status = 'failed'
order by id desc
limit 20;
```

A queued job may indicate a sleeping/stopped worker or unavailable broker; check worker and Redis before requesting another full-school PDF. A failed multipart report must not expose incomplete downloads. Do not manually mark jobs successful or retry destructive work by editing database rows.

## Scheduled maintenance

| Cadence               | Action                                                                                                                                                             |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Nightly               | Backup sidecar purges expired undo/job outputs, encrypts/uploads dump and checks archived-year bundles. Monitor its recorded result, not just the container state. |
| Monthly               | Review access roles/inactive accounts, assignments, dependency/container updates, disk growth and backup restore-test results.                                     |
| Each semester         | Human isolated restore drill; report/printer checks after template changes.                                                                                        |
| Before year close     | Confirm both semesters locked, take/store approved exports, review rollover into the next setup year and school numbers without rewriting archived enrollments.    |
| Per controller policy | Retention purge, Drive membership review, credential/access review and incident tabletop.                                                                          |

Without the backup scheduler, arrange explicit periodic maintenance:

```bash
docker compose exec api flrc purge-admin-actions
docker compose exec api flrc purge-job-outputs
```

Expired records can remain physically present until maintenance runs. See [Privacy data map](../security/privacy-data-map.md) for retention effects.

## Common failures

| Symptom                                  | Inspect / action                                                                                                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| School API returns 404 through gateway   | Matching `GATEWAY_SECRET`, API proxy route and deployed environment; do not disable the gateway check.                                                                         |
| School mutation returns 403 `bad_origin` | Exact public `Origin` and same-origin browser path; do not loosen CSRF for operator convenience.                                                                               |
| Google login rejected                    | Workspace `hd`, verified email/domain, active allowlist, bound Google subject, client callback/audience/policy. Never reset a subject binding without verifying the new owner. |
| 429                                      | Honour `Retry-After`; independent per-operation budgets are in [Security model](../security/security-model.md).                                                                |
| 503 `security_service_unavailable`       | Redis-backed security counters in school mode fail closed. Restore Redis rather than bypassing them.                                                                           |
| Report failure after overlay edit        | Check required assets, paths, layout and matching branding revision; restart report processes after applying the fix.                                                          |
| Undo conflict                            | Later data no longer matches the action snapshot; review current state instead of forcing a database rollback.                                                                 |
| Backup alert                             | Check status error and Drive/key/disk permissions; retain old copies while diagnosing.                                                                                         |

## Secret changes

Edit the server secret store/environment and recreate affected services so environment changes load. A plain container restart does not reload changed Compose environment values. Rotate `GATEWAY_SECRET` on web and API together; that does not revoke sessions. Rotate `SESSION_SECRET` to invalidate signed cookies; for incident-wide session cleanup also remove the application's session/index keys under a controlled Redis window. Never print credentials in logs or tickets.

Stop access and escalate immediately for cross-user disclosure, silent overwrites, locked/archive mutation, wrong-pupil reports, non-allowlisted school access or unexpected migration disagreement. Preserve ids/timestamps/revisions, not personal record contents.
