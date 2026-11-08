# Authentication and sessions

Google establishes identity; FL-ReportCard owns admission, permissions and revocable sessions. Read this when changing login, cookies, role guards, teacher scope or test authentication; deployment hardening is specified in the [security model](../security/security-model.md).

## Google OAuth/OIDC flow

The teacher SPA owns `/login`; both panels use the same session. Backend routes live in `apps/backend/src/flrc/modules/auth/`.

1. `GET /api/auth/login` calls Authlib's Google OIDC client with `openid email profile`, `prompt=select_account` and the callback URI `${FRONTEND_ORIGIN}/api/auth/callback`. Ordinary school login includes a hosted-domain hint; public visitor login deliberately does not.
2. Starlette `SessionMiddleware` carries short-lived signed OAuth state in a separate cookie (`flrc_oauth_state`, school mode `__Host-flrc_oauth_state`), with a ten-minute lifetime. This cookie is not the logged-in session store.
3. `/api/auth/callback` exchanges/verifies the authorization response through Authlib. School admission requires the normalized Google `hd` claim and email suffix to match the configured domain, a verified email, a nonempty bounded `sub`, and an existing active local allowlist row.
4. The allowlist row is locked. On first login its unique `google_subject` is bound; later login must match it. A subject already bound to another account or an identity mismatch is rejected. Google is not allowed to create ordinary school accounts automatically.
5. The application creates a Redis session, sets the signed session-ID cookie and redirects to the teacher origin. Failure redirects to `/login?error=<stable_code>` for translated UI feedback.

The `hd` authorization hint alone is not a security check: callback validation and local allowlist membership are both required ([ADR-012](../adr/012-google-oauth-plus-explicit-allowlist.md)). Google access/refresh tokens are not browser-session credentials and are not stored in localStorage.

## Redis session and cookie contract

`auth/sessions.py` creates a cryptographically random ID (`secrets.token_urlsafe(32)`), stores `session:{sid} → user_id` with an absolute TTL, and indexes issued IDs in `user_sessions:{user_id}` for revocation. Reads do not extend expiry. Default `SESSION_TTL_SECONDS` is eight hours; an explicitly shortened lifetime cannot lengthen the configured maximum.

`auth/cookies.py` signs the ID with `URLSafeTimedSerializer` and salt `flrc-session`; verification also checks maximum age. Cookies are host-only (no Domain), Path `/`, HttpOnly and SameSite=Lax. School mode uses `__Host-flrc_session`; other modes use `flrc_session`. Secure is enabled outside dev/test. Do not introduce JWTs or client-readable session tokens: immediate server-side revocation is intentional ([ADR-005](../adr/005-server-side-sessions-over-jwts.md)).

For each protected request `current_user`:

- requires and unsigns the cookie;
- resolves the Redis session and loads the current user from PostgreSQL;
- rejects missing/inactive users and destroys that session;
- rechecks the configured email domain and destroys a now-invalid session.

Failures distinguish `not_authenticated`, `bad_session`, `session_expired`, `not_registered` and `wrong_domain`. Error wrapping/translation conventions are in [backend](backend.md#http-and-error-contract).

Both SPAs are served from one origin in deployed environments, so the same host-only cookie works for `/` and `/admin/`. The panels are **not** authorization or origin-isolation boundaries; see [ADR-022](../adr/022-one-public-frontend-origin-with-the-admin-spa-under-admin.md).

## Authorization and assessment scope

| Guard/rule                     | Meaning                                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `current_user`                 | Valid current session and active admitted account                                                                  |
| `require_admin`                | `user.is_admin` is true                                                                                            |
| `require_coordinator_or_admin` | Either coordinator or administrator flag is true                                                                   |
| `writable_semester`            | Open semester joined to an active academic year; otherwise 409 `semester_locked`                                   |
| `writable_year`                | Active academic year exists; otherwise 409 `year_not_writable`                                                     |
| Assignment                     | A class-specific main/skills/german/french slot identifies the responsible teacher, not a global account privilege |
| Override grant                 | Temporary permission for one user/class/owner role with an expiry, audited when used                               |

Teachers can discover/read every class's assessment grid and print middle-school English class sheets. Assignment ownership controls warnings and save confirmation, **not class discovery**. This supersedes the narrower assignment-only grid reading policy in [ADR-044](../adr/044-teacher-assignments-are-object-level-read-and-write.md); current behavior is [ADR-071](../adr/071-teachers-see-every-class-assignments-decide-warnings-not.md).

`save_grid` validates active semester/grade/subject columns and the student's applicable roster. A non-admin saving outside their assignment needs a live grant or explicit `confirm_outside_assignment`; confirmation renews a one-hour grant and audit entries record its ID. Admins do not need this ownership confirmation. Force conflict resolution does not bypass roster, type or writable-semester validation. `POST /api/classes/{class_id}/grants` also requires a currently assigned role and the writable class/year.

Card preview intentionally remains assignment-based even though grid reads are school-wide: main/skills assignments yield the class's English card; German/French assignments yield eligible students' matching karne. Coordinators/admins can preview every eligible card. Grants do not make a preview assignment. Official report-set generation is coordinator/admin; year export and account/setup/lifecycle writes are admin. Jobs have their own requester/admin/coordinator read rules. See [reports and jobs](reports-and-jobs.md).

## Revocation and permanent deletion

`POST /api/auth/logout` deletes the current session/index entry and clears the cookie. Administrative revocation deletes all indexed sessions through `revoke_user_sessions`. The session index outlives the longest issued session, so creating a short session cannot break revocation of an earlier long one. Expired IDs are pruned by live-session counting.

Account deactivation stops access; changing sensitive account state can revoke existing sessions. Permanent deletion is only allowed after deactivation and is irreversible: personal identity/signatures are scrubbed while the user row remains for grade/audit FKs. Assignments are removed and grants ended. Transactions touching accounts use shared/exclusive ordered account locks to avoid deletion races ([ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md)); details are in [backend](backend.md#transaction-and-concurrency-rules). Authentication reads the account once without a lock, so writes that change accounts or roles, cannot be undone, or touch assignments check the acting administrator again under that lock: one deactivated or deleted meanwhile gets 401 `not_registered`, one demoted 403 `forbidden`. Grid saves, grid undo and grant requests likewise hold the caller's own account and refuse it with 401 `not_registered` if it was deactivated or deleted meanwhile.

## Public-demo visitors

Only `ENV=demo` with `DEMO_PUBLIC_LOGIN=true` enables temporary visitor admission. Any verified Google account with valid subject may enter the **synthetic shared school** as a pseudonymous administrator/coordinator; it is not a private sandbox per visitor.

`auth/demo.py` stores an HMAC of Google's subject, not the subject, email or profile name. An advisory transaction lock serializes concurrent logins for that identity. A still-active visitor with a live session is reused; otherwise the prior link is scrubbed and a new synthetic account is created within the daily limit (`DEMO_VISITOR_LIMIT_PER_DAY`, default 500).

Visitor identity lifetime is at most 24 hours; each issued session is capped by both its remaining visitor lifetime and configured session TTL. Logout scrubs the visitor after its last live session ends. Scrubbing removes the hash, deactivates the account and replaces its display identity; nightly demo reset removes transient rows. See [ADR-051](../adr/051-public-demo-visitors-are-pseudonymous-temporary.md), [public-demo operations](../operations/public-demo.md) and [using the demo](../getting-started/using-the-demo.md).

## E2E-only sessions

`POST /api/test/session` is mounted **only** when `ENV=test`. It accepts `{"email":"<synthetic active allowlisted account>"}` and header `X-E2E-Secret` matching nonempty `E2E_AUTH_SECRET` using constant-time comparison. Bad configuration, wrong secret and unknown/inactive users return 404. A successful request issues the same Redis/cookie session mechanism as normal login.

This bypass exists for isolated browser testing, not deployment login or a school back door. School startup rejects a nonempty `E2E_AUTH_SECRET`. Follow [testing](../development/testing.md) for its synthetic fixture stack.

## School-mode checks

`Settings.validate_security_configuration()` runs before app creation. `ENV=school` requires exact identical HTTPS frontend/admin origins (no path), an actual configured Workspace domain/client, independent strong session/gateway/operations secrets, an explicit trusted-host list and secure remote database/Redis transport. Session TTL is bounded to 15 minutes–eight hours, and request-body limits are bounded. Public-demo visitor mode and E2E bypass cannot be used as school authentication.

School mode enables HTTPS redirects, trusted-host validation, HSTS, `__Host-` cookies, origin checks and gateway-secret isolation. Interactive OpenAPI/docs routes are disabled. Missing allowed Origin on an unsafe browser mutation is rejected; operations routes use their own token and are exempt from cookie-CSRF origin checks. Security middleware details and exceptions are in [backend](backend.md#http-and-error-contract); exact environment configuration belongs in the [configuration reference](../reference/configuration.md).

## OAuth rate limits

Login and callback each have independent per-client-address budgets: **30 requests/60 seconds** and **60 requests/five minutes**, enforced together through Redis. This avoids counting the two halves of one successful login against one allowance. Identities are HMAC-pseudonymized in keys; school mode fails closed if the rate-limit store is unavailable. Limit errors are 429 with `Retry-After`; expensive authenticated operations use separate [per-account budgets](reports-and-jobs.md#limits).
