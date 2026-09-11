# Security model

FL-ReportCard treats the backend as the only data-security boundary. Frontend route guards improve
the experience, but they never grant access. Every response containing school, staff, student,
grade, archive, report, job, or administration data is behind the server-side session dependency.

No system can honestly promise that it is impossible to compromise. This document records the
controls, public exceptions, deployment obligations, and tests used to make unauthorized access
fail closed.

Maintained against repository source on 2026-09-11 (handbook Steps 1.7-1.8 and 4.8).
This describes implemented controls and required checks, not a fresh penetration test or proof
of provider configuration. See [the dated audit](SECURITY-AUDIT.md), [open gates](TODO.md), and
[the review handoff](AI-HANDOFF.md).

## Authentication gates

A request reaches school data only after all of these checks:

1. HTTPS reaches the one public school origin.
2. The selected gateway adds a secret header: Cloudflare for managed hosting or Caddy for the
   school VM. Direct requests to the managed API origin receive `404`, except for the
   information-free liveness endpoint. On the VM, the API has no published host port.
3. The browser presents a signed, host-only, `HttpOnly`, `Secure`, `SameSite=Lax` session
   cookie.
4. The random session id exists in Redis and has not reached its configured absolute expiry
   (eight hours by default, at most eight hours in school mode).
5. The referenced user still exists, is active, and still has an email in the configured school
   domain.
6. The role and class/subject permissions required by the endpoint pass.

For teacher-facing academic routes, an assignment is also a read boundary. A teacher can enumerate
only academic years, classes, and subjects for which that teacher has a `teaching_assignments` row.
An override grant permits cross-role work only inside that already-assigned class and subject; it
cannot be used to discover or enter a different class or language subject. Admins retain full
access, and coordinators retain the documented read-only oversight access.

Google login itself also requires all of the following:

- a cryptographically verified OIDC response handled by Authlib;
- an exact Google Workspace `hd` claim;
- `email_verified=true`;
- an email ending in the exact configured school domain;
- an active user row created beforehand by an administrator;
- the same stable Google `sub` value after the first successful login.

An email address reassigned to a different Google account therefore cannot inherit the previous
person's allowlist entry. An admin must first deactivate the entry, explicitly reset its bound
Google identity, verify the new account owner, and reactivate only when that person is ready to
sign in.

## Intentionally public surface

Only these paths work without an application session:

- the static login application and its JavaScript/CSS assets;
- `/api/auth/login` and `/api/auth/callback`, which are necessary to create a Google session;
- `/api/auth/logout`, which returns no data and remains protected by the exact-origin check;
- `/api/healthz`, which returns HTTP 204 with an empty body.

Browser application files cannot be secret: a browser must download them to display the login
screen. They contain no credentials or school data. OpenAPI and interactive API documentation are
disabled in `ENV=school`.

## Production invariants

`ENV=school` refuses to start unless:

- both frontend settings are the same pathless `https://` origin;
- the real Workspace domain and both OAuth credentials are configured;
- session, gateway, and operations secrets are distinct, non-placeholder random values;
- `TRUSTED_HOSTS` is explicit and contains no wildcard;
- the test-login secret is empty;
- session duration is between 15 minutes and eight hours;
- request-body size is between 1 KiB and 25 MiB;
- remote PostgreSQL URLs require TLS;
- remote Redis uses authenticated `rediss://`.

All `/api` responses are `Cache-Control: no-store, private`, vary on cookies, and carry
restrictive browser headers. Unsafe methods require the exact public `Origin`. Request bodies are
counted even when streamed and rejected above the configured limit.

Each OAuth entry/callback endpoint is limited to 120 attempts per five minutes per pseudonymized
client address. Report/export routes are limited to 10 requests per minute per user. The counters live in
Redis, contain an HMAC rather than the raw address/user identifier, and fail closed in school mode.

XLSX imports are bounded by compressed size, ZIP member count, total and per-member expanded size,
compression ratio, worksheet count, and worksheet dimensions before `openpyxl` parses cell data.
CSV/XLSX exports prefix formula-like text so names, labels, and observations cannot execute as
spreadsheet formulas when an administrator opens an export.

Backend telemetry explicitly disables request-body capture and stack-frame local variables. Its
event and breadcrumb scrubbers remove URLs, query strings, cookies, authorization values, gateway
headers, identity fields, and grade values before anything can leave the process.

Set the gateway secret in both places without committing it:

```bash
openssl rand -base64 48
pnpm exec wrangler secret put GATEWAY_SECRET
```

These gateway-secret commands apply to managed hosting. Store the same value as Render's
`GATEWAY_SECRET`. On a school VM, the private deployment environment supplies the matching
secret to Caddy and the API. Generate separate values for `SESSION_SECRET` and `OPS_TOKEN`.

## Report and export boundaries

PDF generation uses an asset fetcher that permits renderer-created `data:` URIs and denies
network/local-file fetching. Private overlay paths are validated, and only public branding files
are served by the web container. Teacher signature uploads are normalized PNGs; identity edits
have dedicated audit records. Celery accepts JSON only and has no result backend.

The pending ADR-063 change hides middle-English opinion fields without deleting saved values or
audits. Hidden fields are not erased data: authenticated audit/workbook exports and backups retain
them. Historical downloaded reports are unchanged. Include this distinction in retention and
incident handling; see [PRIVACY-DATA-MAP.md](PRIVACY-DATA-MAP.md).

## First administrator

There is no public registration route. After migrations and before the first login, an operator
with database deployment access creates exactly one initial allowlist entry:

```bash
cd apps/backend
uv run flrc bootstrap-admin --email admin@school.k12.tr --name "School Administrator"
```

Once an active admin exists, this command refuses to create another one. All later users are added
through the authenticated admin table.

## Public demo

`ENV=demo` with `DEMO_PUBLIC_LOGIN=true` (ADR-051) accepts any verified Google identity and creates
a temporary administrator of the shared synthetic school. The application never stores the
visitor's Google subject, email, name, or picture: the account carries a random synthetic email in
the configured demo domain, a generated name, and a keyed hash of the subject used only to reuse
the account while a session is alive. Sessions expire at most 24 hours after the account was
created; the last logout, or a login that finds no live session, scrubs the identity link and
deactivates the row. Visitors cannot edit other visitor accounts, managed users must use the
synthetic domain, and new visitor accounts are capped per day. The flag is refused at startup in
every other environment, including school mode.

The demo also mounts two operations routes, `POST /api/ops/demo/reset` and
`GET /api/ops/demo/status`, which exist only in `ENV=demo` and require the `X-Ops-Token` header to
equal `OPS_TOKEN`; they bypass the Origin check because no browser cookie is involved. The public
`GET /api/demo` route reports only the next reset time and the visitor lifetime. A Neon API key
scoped to the demo project performs the branch restore and is scrubbed from telemetry like the
other secrets.

## Automated proof

`tests/test_security_launch.py` enumerates the complete API router and sends an unauthenticated
request to every data route. Adding a route without central authentication makes CI fail. It also
tests the gateway secret, HTTPS redirect, trusted hosts, disabled schema, security headers, CSRF,
test-route absence, body limits, and unsafe production configuration.

`tests/test_auth_security.py` attacks the OAuth claim and allowlist boundary: wrong domains,
unverified email, missing identity, unregistered school account, reassigned email takeover, and a
session whose allowlist email no longer belongs to the school.

Run the focused gate:

```bash
cd apps/backend
uv run pytest -q tests/test_security_launch.py tests/test_auth_security.py tests/test_guards.py
```

First inspect the test fixtures: this command migrates and clears local `flrc_test`. Use only a
disposable test database, with no concurrent pytest run. Add `tests/test_security_hardening.py`,
`tests/test_report_identity.py`, and `tests/test_report_overlay.py` for report/asset reviews.
The asset fetcher regression lives in `tests/test_phase4.py`.

The locked-dependency audit always scans both production lockfiles. CodeQL scans Python and
TypeScript, and dependency review rejects newly introduced moderate-or-higher runtime
vulnerabilities, when GitHub Advanced Security is available. Private repositories without that
entitlement leave the repository variable `GHAS_ENABLED` unset, so those unsupported jobs are
skipped instead of producing false-red runs; set it to `true` only after enabling the feature.
Dependabot checks npm, Python, Docker, and GitHub Actions weekly. Gitleaks scans the complete Git
history on pull requests, main pushes, and the weekly schedule. Third-party workflow actions and
runtime container bases are pinned to immutable digests.

## Manual deployment proof

Replace the example hosts before running:

```bash
curl -i https://flrc.school.k12.tr/api/me
# 401; no student or staff data

curl -i https://flrc.school.k12.tr/api/openapi.json
# 404

curl -i -X POST https://flrc.school.k12.tr/api/auth/logout
# 403 because Origin is absent

curl -i https://flrc-api-school.onrender.com/api/me
# 404 because the private gateway header is absent

curl -I http://flrc.school.k12.tr/
# redirects to HTTPS
```

Provider configuration is still part of the boundary: enable Cloudflare “Always Use HTTPS,” use a
school-owned Google OAuth client configured as Internal where available, register only the exact
callback URL, protect provider accounts with MFA, and restrict the direct API by inbound IP rules
when the selected Render plan supports them.

For school-hosted production, replace the Render probe with confirmation that PostgreSQL, Redis,
and the API have no published ports and Caddy alone accepts public traffic. Verify `/branding/`
serves only the public logo, favicon, and brand script; private report templates/signatures must
not be retrievable. Follow the chosen profile rather than assuming both gateways are present.
