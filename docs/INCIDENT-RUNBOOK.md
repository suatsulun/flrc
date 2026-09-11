# Incident runbook

Handbook Steps 4.8-4.10. Reviewed for repository behavior on 2026-09-11; named school owners and
actual response exercises remain operational evidence. Use [RUNBOOK.md](RUNBOOK.md) and the
matching deployment profile when executing recovery.

## First response

1. The named school incident lead decides whether to disable access. If identity or cross-user disclosure is suspected, stop public traffic before debugging.
2. Preserve timestamps, request ids, job ids, and deployment revisions. Do not copy names, grades, request bodies, database dumps, cookies, or OAuth tokens into tickets/chat.
3. Notify the school controller/DPO. Counsel/DPO owns legal assessment and notification deadlines; this document does not invent them.

## Containment

- Deactivate affected users through the allowlist screen; this revokes Redis sessions.
- For a global logout, rotate `SESSION_SECRET`, redeploy API/worker, and clear `session:*` and `user_sessions:*` keys through an approved Redis maintenance window.
- If the public gateway or API-origin boundary is implicated, rotate `GATEWAY_SECRET` in
  Cloudflare and Render together, or in the Caddy/API deployment environment for a school VM.
  Until both sides match, keep public traffic disabled. Gateway-secret rotation alone does not
  revoke application sessions.
- Revoke/rotate the Google OAuth client if identity credentials are implicated.
- Rotate database, Redis, Sentry, and Drive service-account credentials in their secret stores; never commit new values.
- Stop report/download access if generated artifacts may be exposed. `flrc purge-job-outputs`
  deletes expired blobs only; it does not revoke unexpired job downloads, previously downloaded
  PDFs, or Drive archives. Contain access to those stores and preserve incident evidence before
  any targeted cleanup approved by the school.
- If an archive shows a current-year number, stop report and archive access before repair. Preserve
  ids and year ids only; verify joins use `(student_id, year_id)` and do not rewrite archived
  enrollments.

## Recovery

Deploy the last known-good release. Prefer a forward database fix. If data restoration is required, restore the last verified dump into a new database, validate aggregate counts and one authorized read, then switch credentials through change control.

Record the image tags, Alembic revision, and private branding revision together. Migration
`82a91f4c6d30` retires middle-English comments without deleting the historical values; its downgrade
does not reactivate fields. Do not confuse missing display fields with data loss, or a code rollback
with restoration of active flags. Restore private report assets separately from the database dump.

## Closeout

Document an exact UTC timeline, affected ids/counts, containment, recovery, and prevention. Record no student data. The controller approves reopening and any external communication.
