# Security model

This document defines implemented security boundaries, residual risks and deployment obligations. Read this before changing authentication, authorization, uploads, reporting, telemetry or infrastructure; detailed session mechanics belong in [Auth and sessions](../architecture/auth-and-sessions.md).

## Threat model and trust boundaries

School records include children's identities, grades, teacher identities and signatures. Threats include unauthenticated access, an authenticated user crossing a role boundary, reassigned Google accounts, CSRF, hostile workbooks, report resource fetching, stolen credentials and accidental disclosure through exports/logs/backups. The backend—not SPA navigation or hidden buttons—is the data-security boundary.

| Boundary                    | Implemented control / source                                                                                               |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Public origin → API         | School HTTPS redirect, explicit trusted hosts, gateway header comparison; `core/middleware.py`, `main.py`                  |
| Browser → session           | Signed host-only HttpOnly cookie, Redis random session id, absolute expiry and active/domain recheck; `modules/auth/`      |
| User → privileged operation | Central protected API dependency plus endpoint admin/coordinator checks; `main.py`, `modules/auth/dependencies.py`         |
| Untrusted workbook → parser | Request-body cap, XLSX ZIP/expansion/member/worksheet/dimension bounds; `modules/imports/parser.py`                        |
| Report → filesystem/network | Deny-by-default renderer fetcher, contained overlay paths, sandboxed templates; `modules/reports/render.py`, `branding.py` |
| Broker → worker             | JSON-only accepted serializers, no Celery result backend; `workers/celery.py`                                              |
| App → telemetry/export      | Scrubbing and formula neutralization; `core/telemetry.py`, `spreadsheets.py`                                               |

A compromised server, database administrator, private deployment repository, or backup decryption identity remains highly privileged. School operators must secure those systems independently. A school-authorized teacher is deliberately trusted with school-wide academic reads and confirmed writes—not confined to their assignments.

## Authentication and permissions

School Google login verifies OIDC through Authlib, `email_verified=true`, exact Workspace `hd` and email domain, an existing active allowlist row and stable Google `sub`. First login binds the subject; a different subject cannot inherit a recycled email. Administrators must deactivate, verify the new owner, explicitly reset the binding and reactivate. There is no school public-registration flow ([ADR-038](../adr/038-fail-closed-school-authentication-and-managed-origin.md)).

The central protected router requires `current_user` for school/staff/student/grade/archive/report/job/dashboard/change data. Every request checks the signed cookie, Redis session, active user and configured email domain; frontend guards do not grant access.

- Teachers can discover every class/year/subject and save to writable grids. Out-of-assignment columns require explicit confirmation and an audited override grant. This is a deliberate product policy ([ADR-071](../adr/071-teachers-see-every-class-assignments-decide-warnings-not.md)), **not** the old assignment-scoped access rule from ADR-044.
- Admin/coordinator operations retain explicit role checks. Locked semesters and archived years are not made writable by an admin flag.
- Jobs are readable/downloadable by their requester or an admin; coordinators may also read non-`year_export` jobs. Guessing an id is not authorization (`modules/jobs/router.py:may_read_job`).
- Grade undo rechecks current semester, column and pupil roster state; admin undo checks current state/conflicts and expires after seven days. Do not bypass those checks for repair.

## Public routes and cookies

Intentionally unauthenticated surfaces are static application/login assets, `/api/auth/login`, `/api/auth/callback`, origin-checked POST `/api/auth/logout`, empty-204 `/api/healthz`, and `/api/demo` (null outside demo). School `/api/docs` and `/api/openapi.json` are disabled. The test-session router mounts only with `ENV=test`; school mode rejects an E2E secret. Public demo has separate token-protected operations exceptions described in [Public demo operations](../operations/public-demo.md).

School cookies use `__Host-flrc_session`, `Secure`, `HttpOnly`, `SameSite=Lax`, path `/` and no Domain. Redis stores a random session-id → user-id mapping with absolute TTL (default eight hours, school range 15 minutes–eight hours); requests do not extend it. The per-user index supports revocation. OAuth state uses a separate signed ten-minute cookie, not a persistent login token. No password or browser-local bearer-token login is used.

## CSRF, origin and gateway

In school mode all unsafe methods require an exact configured public `Origin`; `Sec-Fetch-Site`, when supplied, must be `same-origin` or `none`. Missing Origin is rejected, including operator curl mutations. Safe methods are GET/HEAD/OPTIONS. Token-authenticated `/api/ops/` paths bypass this browser-cookie CSRF check; school does not mount demo operations.

Caddy injects/replaces `X-Flrc-Gateway` and strips `Cf-Connecting-Ip`. The Cloudflare managed gateway replaces client gateway assertions and adds its secret. School API requests without the matching secret return 404 except health; Compose publishes no API/Redis/PostgreSQL host ports. Do not expose Uvicorn directly: its startup trusts forwarded headers from its gateway network.

## Fail-closed school startup

`config.py:validate_security_configuration` rejects:

- different frontend/admin origins, non-HTTPS origins, paths/query/credentials/fragments;
- invalid Workspace domain/client configuration, placeholder/short/non-diverse secrets, or reuse of session/gateway/operations secrets;
- wildcard/missing trusted hosts or omission of the public host;
- test-login secret, public-demo login/reset settings in school mode;
- session TTL outside 900–28800 seconds or body limit outside 1 KiB–25 MiB;
- remote PostgreSQL without required TLS or remote Redis without authenticated `rediss://`.

The default body cap is 12 MiB and is enforced for streamed requests too. Local Compose service connections are an explicit TLS exception. Startup checks do not prove provider ownership, firewall correctness or successful backups. Initial provisioning is in [Self-hosting](../operations/self-hosting.md).

## Abuse and resource limits

`core/rate_limit.py` uses atomic Redis fixed windows and HMAC-derived identities. OAuth login and callback each have independent **30/minute and 60/five-minute** client-address budgets. Per-account counters below are independent:

| Operation                      | Requests/minute |
| ------------------------------ | --------------: |
| Whole report set               |               5 |
| Single pupil/class/preview PDF |              30 |
| Audit/year export              |               3 |
| Workbook commit                |               3 |
| Interactive workbook preview   |              30 |

Exceeding a limit returns 429 with `Retry-After`. Redis errors return 503 `security_service_unavailable` in school mode; other environments fail open. These are selected-operation limits, not API-wide or volumetric DDoS protection ([ADR-068](../adr/068-tighten-operation-limits-and-bound-oauth-bursts.md)).

XLSX validation limits 1,000 archive entries, 50 MiB total expanded bytes, 20 MiB per entry, 200:1 aggregate compression ratio, 100 worksheets, 10,000 rows and 100 columns per worksheet. Encrypted/malformed workbooks are rejected. Preview/commit digest checks protect reviewed roster agreement. CSV/XLSX output neutralizes formula-like text through the shared spreadsheet helper.

## Headers, rendering and telemetry

All API responses have `no-store, private, max-age=0`, cookie variation, nosniff, frame denial, no-referrer, restrictive permissions, same-origin resource/opener policies and deny-by-default CSP (non-school interactive docs are exempted). School adds HSTS. Caddy's frontend CSP permits same-origin scripts, Sentry ingest connections, data images and same-origin/blob PDF frames; inline styles are permitted, inline scripts are not. These policies must survive any replacement gateway.

The renderer permits renderer-created `data:` resources and rejects network/file fetching. Private templates use a sandbox, strict undefined variables and autoescaping; overlay paths reject traversal/escaping symlinks. Signature uploads are validated/normalized PNGs and identity edits are audited. Private assets must stay out of web mounts ([Branding](../operations/branding.md)).

Structured request logs contain request id, method/path, status and duration—not query strings or bodies. Sentry disables default PII, stack locals, request bodies and tracing; recursive event/breadcrumb scrubbers filter identity, grade, URL/query and secret keys. This is not permission to log sensitive free-form exception strings. The browser privacy boundary is [ADR-067](../adr/067-preserve-browser-telemetry-privacy-and-own-the-shared.md).

## Audit and data lifecycle

Grade audits/save batches preserve who changed which values, conflict versions and override-grant attribution. `report_identity_audits` retain before/after report names and image digests, not historical image bytes. `admin_actions` temporarily retain row snapshots and sometimes old signature bytes for undo ([ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md)). Permanent teacher deletion scrubs personal identity but preserves attribution ids ([ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md)). Exact retention/purge responsibilities belong in [Privacy data map](privacy-data-map.md).

## Open findings and residual obligations

The superseded security audit's SEC-03 resource-fetcher and SEC-04 Celery-serializer findings are **implemented fixes**, not pending branches: see `reports/render.py` and `workers/celery.py`. Its former SEC-01 assignment restriction was intentionally replaced by ADR-071. Do not repeat the historical audit's assurance as a current penetration-test result.

Remaining operational risks visible in the implementation:

- Fixed-window/per-operation budgets do not prevent upstream DDoS; shared school addresses require care when adding proxy limits.
- Demo visitor/rate counters fail open on Redis failure; the public demo is not the school security profile.
- A missing checksum sidecar is tolerated by the automated restore test, and a never-run restore test only warns in backup freshness CI. Require both checksum evidence and an actual drill before trusting recovery.
- Expiry is not physical deletion: maintenance must purge undo/output storage; downloaded reports, older backups and plaintext Drive year archives remain independently retained.
- Static security controls and source review cannot establish deployed firewall, secret storage, provider access, privacy approval or asset mount correctness. Verify those privately at launch and after relevant changes.

These are explicit residual obligations, not claims of newly discovered exploitable vulnerabilities. The current repository supplies regression suites in `apps/backend/tests/test_security_launch.py`, `test_auth_security.py`, `test_security_hardening.py`, `test_grades.py` and `test_school_provisioning.py`; consult [Testing](../development/testing.md) before running them against their disposable database. `.github/workflows/security.yml` scans full history with gitleaks and audits locked production JS/Python dependencies (PyPI and OSV). CodeQL and dependency review run for public repos or `GHAS_ENABLED=true`; scheduled scanning runs weekly. A passing scan is not a complete security assessment.
