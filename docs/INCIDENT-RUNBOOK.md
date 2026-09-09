# Incident runbook

## First response

1. The named school incident lead decides whether to disable access. If identity or cross-user disclosure is suspected, stop public traffic before debugging.
2. Preserve timestamps, request ids, job ids, and deployment revisions. Do not copy names, grades, request bodies, database dumps, cookies, or OAuth tokens into tickets/chat.
3. Notify the school controller/DPO. Counsel/DPO owns legal assessment and notification deadlines; this document does not invent them.

## Containment

- Deactivate affected users through the allowlist screen; this revokes Redis sessions.
- For a global logout, rotate `SESSION_SECRET`, redeploy API/worker, and clear `session:*` and `user_sessions:*` keys through an approved Redis maintenance window.
- If the public gateway or API-origin boundary is implicated, rotate `GATEWAY_SECRET` in
  Cloudflare and Render together. Until both sides match, keep public traffic disabled.
- Revoke/rotate the Google OAuth client if identity credentials are implicated.
- Rotate database, Redis, Sentry, and Drive service-account credentials in their secret stores; never commit new values.
- Stop report/download access and run `flrc purge-job-outputs` if generated artifacts may be exposed.
- If an archive shows a current-year number, stop report and archive access before repair. Preserve
  ids and year ids only; verify joins use `(student_id, year_id)` and do not rewrite archived
  enrollments.

## Recovery

Deploy the last known-good release. Prefer a forward database fix. If data restoration is required, restore the last verified dump into a new database, validate aggregate counts and one authorized read, then switch credentials through change control.

## Closeout

Document an exact UTC timeline, affected ids/counts, containment, recovery, and prevention. Record no student data. The controller approves reopening and any external communication.
