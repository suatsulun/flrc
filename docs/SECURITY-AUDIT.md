# Security audit — 2026-09-07

## Executive summary

The audit covered the backend authentication and authorization boundary, every parameterized API
route, workbook ingestion and spreadsheet export, report rendering, Celery configuration,
middleware and production configuration, both browser applications, deployment files, dependency
locks, CI workflows, and repository history. No critical finding was identified.

The branch fixes three high, seven medium, and four low findings. Two high findings in files owned
by the concurrent PDF worker are recorded here but intentionally not modified on this branch; that
worker has implemented the routed fixes, which must land before production deployment. The
route-by-route IDOR probe found no further bypass after the assignment boundary was added.

Severity reflects likely impact to children's school records in the documented deployment, not
only technical exploit complexity. “Fixed” means fixed and regression-tested on this branch.

## Findings

### High

#### SEC-01 — Teachers could enumerate and alter other classes and subjects — Fixed

- Location: `apps/backend/src/flrc/modules/grades/permissions.py:18`,
  `apps/backend/src/flrc/modules/grades/router.py:264`,
  `apps/backend/src/flrc/modules/academics/assignments.py:97`
- Exploit scenario: any authenticated teacher changes `class_id`, `subject`, or `year_id` in an API
  request and reads another class's student names, school numbers, and grades. The same broad access
  allowed saves, grants, and undo operations outside the teacher's assignment.
- Resolution: exact class-and-subject assignment checks now guard grid read, save, grant, and undo;
  catalog and academic-year enumeration are scoped to the teacher's assignments. Unknown and
  unassigned year probes both return an empty catalog.
- Evidence: `test_teacher_cannot_cross_class_or_subject_boundaries`,
  `test_teacher_cannot_enumerate_unassigned_academic_year`, and the parameterized privileged-route
  probe in `apps/backend/tests/test_security_hardening.py`.

#### SEC-02 — Hostile XLSX files could exhaust memory/CPU or silently truncate a roster — Fixed

- Location: `apps/backend/src/flrc/modules/imports/parser.py:25-63`,
  `apps/backend/src/flrc/modules/imports/parser.py:127-168`
- Exploit scenario: an administrator is induced to upload a small ZIP bomb, an archive with extreme
  member count/dimensions, or a sheet whose attacker-controlled declared dimension hides later
  rows. The first two can exhaust the API process; the last can silently import only part of a
  roster.
- Resolution: compressed and expanded sizes, member count, compression ratio, encryption,
  worksheet count, real streamed row count, and real column count are bounded before data is
  accepted. Malformed XML is mapped to a stable 422 response.
- Evidence: ZIP-bomb, lying-dimension, missing-dimension, and external-entity tests in
  `apps/backend/tests/test_security_hardening.py`.

#### SEC-03 — WeasyPrint retained its default network/local-file fetch capability — Routed fix

- Location: `apps/backend/src/flrc/modules/reports/render.py:473`
- Exploit scenario: if a future branding value, template field, or imported value reaches a CSS/HTML
  URL, PDF rendering can fetch internal HTTP services or local files with the backend's authority.
  Current templates do not expose a direct attacker-controlled URL, which lowers immediacy but not
  the unsafe default's blast radius.
- Status: the PDF worker owns this file and has implemented a deny-by-default `url_fetcher` on its
  branch. This security branch does not duplicate that concurrent edit. Production release is
  blocked until that change is merged and its tests pass.

#### SEC-04 — Celery did not explicitly reject non-JSON serializers — Routed fix

- Location: `apps/backend/src/flrc/workers/celery.py:10-18`
- Exploit scenario: a broker credential compromise or future producer misconfiguration could place
  a pickle-serialized task on the queue; accepting pickle permits code execution in the worker.
- Status: the PDF worker owns this file and has implemented explicit JSON task/result serializers
  and `accept_content=["json"]` on its branch. Production release is blocked until that change is
  merged and verified.

### Medium

#### SEC-05 — Expensive and unauthenticated endpoints had no application rate limits — Fixed

- Location: `apps/backend/src/flrc/core/rate_limit.py:24-113`,
  `apps/backend/src/flrc/main.py:100`
- Exploit scenario: automated OAuth requests consume provider/application capacity, or one logged-in
  account repeatedly parses workbooks and renders/exports reports until the small school service is
  unavailable.
- Resolution: Redis-backed endpoint-specific OAuth counters and per-user expensive-operation
  counters return 429 with `Retry-After`. Keys contain an HMAC, not raw addresses or user ids, and
  the control fails closed in school mode.

#### SEC-06 — Remote Postgres/Redis could be configured without authenticated TLS — Fixed

- Location: `apps/backend/src/flrc/config.py:100-118`
- Exploit scenario: a mistaken production URL sends session data, job messages, grades, or database
  credentials over an unprotected remote connection.
- Resolution: school-mode startup rejects remote Redis without authenticated `rediss://` and remote
  database URLs that do not require TLS.

#### SEC-07 — Reusing operational secrets enlarged compromise scope — Fixed

- Location: `apps/backend/src/flrc/config.py:83-94`
- Exploit scenario: the same value is used for session signing, gateway authentication, and the
  operations endpoint, so disclosure of one trust-domain secret compromises the others.
- Resolution: school-mode startup requires all three sufficiently random secrets to be pairwise
  distinct and rejects an enabled E2E authentication secret.

#### SEC-08 — Spreadsheet exports allowed formula injection — Fixed

- Location: `apps/backend/src/flrc/core/spreadsheets.py:1-13`,
  `apps/backend/src/flrc/modules/audit/router.py:162`,
  `apps/backend/src/flrc/workers/tasks/exports.py:25`
- Exploit scenario: a malicious staff/student display value beginning with `=`, `+`, `-`, or `@`
  executes as a formula when an administrator opens an audit CSV or year workbook.
- Resolution: all CSV/XLSX export paths neutralize formula-like text through one shared function.

#### SEC-09 — CI actions and runtime image tags were mutable — Fixed

- Location: `.github/workflows/ci.yml:18`, `.github/workflows/security.yml:20`,
  `apps/backend/Dockerfile:1-12`
- Exploit scenario: compromise or retagging of a referenced action/image executes changed code with
  CI credentials or ships an unreviewed runtime.
- Resolution: third-party actions and backend runtime/build images are pinned to immutable digests;
  Dependabot remains responsible for proposed updates.

#### SEC-10 — Repository history had no automated secret scan — Fixed

- Location: `.github/workflows/security.yml:16-28`
- Exploit scenario: a credential committed and later deleted remains usable from Git history but is
  missed by ordinary current-tree review.
- Resolution: gitleaks scans full history on pull requests, main pushes, and the scheduled workflow.

#### SEC-11 — Locked dependency audit missed workspace-root overrides — Fixed

- Location: `pnpm-workspace.yaml:7-9`, `.github/workflows/security.yml:30-61`
- Exploit scenario: vulnerable transitive `fast-uri` or `qs` releases remain selected even though
  direct manifests look clean.
- Resolution: safe versions are forced at the workspace root and the security workflow audits both
  production lockfiles. CodeQL/dependency review remain entitlement-gated as documented.

### Low

#### SEC-12 — API responses lacked a restrictive CSP and opener isolation — Fixed

- Location: `apps/backend/src/flrc/core/middleware.py:80-97`
- Exploit scenario: a future HTML/error response on an API URL has fewer browser containment layers
  than intended and could be framed or load active resources.
- Resolution: API responses receive deny-by-default CSP and COOP; local interactive documentation is
  exempted because it is disabled entirely in school mode.

#### SEC-13 — Job identifiers needed explicit owner regression coverage — Fixed

- Location: `apps/backend/src/flrc/modules/jobs/router.py:43-100`
- Exploit scenario: a teacher guesses another teacher's sequential job id and requests its status or
  generated output.
- Resolution: existing ownership enforcement was retained and is now tested for both detail and
  download. Coordinators can read non-year report jobs by documented design; year exports remain
  admin-only.

#### SEC-14 — Privileged object routes lacked a complete role-boundary probe — Fixed

- Location: `apps/backend/tests/test_security_hardening.py`
- Exploit scenario: a newly refactored `/{id}` handler performs object lookup before its admin or
  coordinator gate, leaking existence or data to a teacher.
- Resolution: the suite now actively sends a teacher through every parameterized academics,
  administration, archive, reports, and jobs route. Audit/import identifiers are query parameters
  and are covered by their admin gates; system has no identifier route.

#### SEC-15 — Security posture documentation understated the OAuth allowance — Fixed

- Location: `docs/SECURITY.md:77-79`
- Exploit scenario: operators tune gateway limits around an incorrect 20-request claim and
  unexpectedly lock out a NAT-shared school during morning login.
- Resolution: documentation now records the implemented endpoint-separated 120 requests per five
  minutes.

## Negative results and residual risk

- No browser token storage, `dangerouslySetInnerHTML`, or post-login open redirect was found.
- Authentication remained Google OIDC plus hosted-domain verification, local allowlist, stable
  Google subject binding, and server-side Redis sessions. Cookies remain `HttpOnly`, `Secure` in
  school mode, host-only, and `SameSite=Lax`; unsafe methods retain exact-origin enforcement.
- SQLAlchemy expression APIs are used for application queries; no attacker-controlled raw SQL
  construction was found.
- Jinja templates use HTML/XML autoescaping. The separate WeasyPrint fetch boundary remains the
  release-blocking routed item SEC-03.
- The health endpoint is intentionally unauthenticated and returns an empty 204 response. OpenAPI
  and interactive documentation remain disabled in school mode.
- Rate limits are fixed-window controls. They are intended to protect a small service, not replace
  upstream volumetric DDoS protection.

## Verification

The focused security test is:

```bash
cd apps/backend
uv run pytest -q tests/test_security_hardening.py
```

Release gates are recorded in the pull request with exact pass/fail counts. Production deployment
also requires confirmation that SEC-03 and SEC-04 have merged from the coordinated PDF branch.
