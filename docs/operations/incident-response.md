# Incident response

This document coordinates containment and recovery for suspected unauthorized access, disclosure or record corruption. Read this as soon as an incident is suspected; routine failures belong in the [Runbook](runbook.md).

## First response

1. Notify the school's privately designated incident lead and controller/privacy officer. They decide access suspension, legal assessment, notifications and reopening; this repository does not prescribe legal deadlines.
2. If identity, cross-user disclosure or wrong-pupil reports are suspected, stop public traffic before debugging. Preserve the surviving database and deployment state; do not run demo reset, seed, destructive cleanup or an unreviewed schema downgrade.
3. Preserve a UTC timeline, request/job/object ids, image tags/digests, Alembic revision and private branding revision. Keep evidence in approved private storage. Do not paste names, grades, dumps, cookies, tokens, signatures or request bodies into tickets or chat.

## Containment by boundary

| Suspected boundary             | Containment                                                                                                                                                                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Individual school account      | Deactivate it in the admin allowlist; sessions are revoked. Verify the account owner before resetting its Google subject binding.                                                                                                                         |
| Application sessions           | Rotate `SESSION_SECRET` and recreate affected processes; under an approved Redis maintenance window remove `session:*` and `user_sessions:*` keys without disturbing unrelated applications. Cookie rotation alone leaves old Redis records until expiry. |
| Gateway/API origin             | Keep traffic stopped while rotating matching `GATEWAY_SECRET` on Caddy/API, or the managed gateway/API. Gateway rotation does not revoke logged-in sessions.                                                                                              |
| OAuth client                   | Revoke/rotate the client credentials in the school-owned Google project and update secret stores.                                                                                                                                                         |
| Infrastructure credential      | Rotate implicated PostgreSQL, Redis, Drive service-account or telemetry credentials in their provider and deployment secret stores. Never commit new values.                                                                                              |
| Generated reports/exports      | Suspend report/download access and review Shared Drive membership and downloaded copies. `flrc purge-job-outputs` only cleans expired outputs/failed parts; it does not revoke unexpired downloads or files already copied elsewhere.                     |
| Wrong historical school number | Stop affected archive/report access. Verify year-scoped enrollment joins and stage-scoped numbers before repair; do not rewrite archived enrollments to match today's roster.                                                                             |

Do not permanently delete teachers as an incident-evidence shortcut. That operation is intentionally irreversible and erases identity and undo data while preserving grade/history attribution ids; see [Privacy](../security/privacy-data-map.md).

## Recovery

- Establish the last trustworthy image, schema, data and private branding revisions. Prefer a reviewed forward fix to a schema downgrade.
- For a code rollback, follow [Deployment](deployment.md#rollback). Reverting images does not undo data migrations. In particular, retired middle-English text columns retain values and are not automatically reactivated by downgrading migration `82a91f4c6d30`.
- If data restoration is required, follow [Backups and restore](backups-and-restore.md): verify checksum, decrypt and restore into a **new isolated database**. Validate revision, aggregate counts, authorized archived reads and affected report behavior before switching production credentials.
- Restore matching private report templates/principal assets separately. Database backups contain teacher signatures, not the complete private runtime overlay.
- Treat restored accounts/sessions and old report files as potential continuing exposure. Review access and revoke sessions before restoring traffic where required.
- Run the [deployment acceptance checks](deployment.md#verify-the-deployed-revision) in the recovered environment. The controller/incident lead approves reopening and external communication.

## Closeout

Record the exact timeline, affected ids/counts, root cause, containment, recovery revisions, evidence locations and prevention changes privately. Update code/regression coverage and these public procedures only with synthetic examples. A successful health check or scheduled backup is not proof that the incident's data boundary has been repaired.
