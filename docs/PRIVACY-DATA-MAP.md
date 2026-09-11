# Privacy data map

Source review date: 2026-09-11; handbook Steps 4.7-4.8. This maps implemented storage, not a legal
retention approval. The school controller supplies the actual retention policy. In a school VM,
Postgres and Redis are school-hosted; Neon/Upstash describe the managed profile.

| Data category             | Exact fields                                                                                                                         | Store/processor                                                  | Purpose                                           | Retention/deletion owner                                                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Staff identity/access     | `users.email`, `google_subject`, `full_name`, role and active flags                                                                  | Postgres; Google Workspace supplies verified identity            | Authentication, authorization, attribution        | School controller; deactivate immediately, delete only under approved policy                                             |
| Teacher report identity   | `users.report_name`, `signature_png`, `signature_digest`; `report_identity_audits` actor/target ids, old/new names and image digests | School Postgres and its encrypted backups                        | Assigned report signers and traceable admin edits | School controller; administrators may replace/remove the current signature; audit follows the target account's retention |
| Principal report identity | Principal names, titles and signature assets                                                                                         | Private school deployment repository and mounted branding folder | Stage-specific report approval blocks             | School controller maintains the assets; never included in public application sources or public branding mounts           |
| Student identity          | `students.id`, `full_name`, `search_name`                                                                                            | Postgres                                                         | Stable person identity and name search            | School controller under the school records policy                                                                        |
| Yearly school number      | `enrollments.year_id`, `school_number`, `class_id`                                                                                   | Postgres                                                         | Year-specific roster identity and class           | School controller under the school records policy                                                                        |
| Academic placement        | enrollment, class, year, second-language ids                                                                                         | Postgres                                                         | Correct roster and subject membership             | School controller                                                                                                        |
| Grades and audit          | typed grade values, versions, actor/student/column ids, old/new audit values                                                         | Postgres                                                         | Report cards, conflict safety, accountability     | School controller; retention period must be written by the school                                                        |
| Sessions                  | random session id → user id                                                                                                          | Redis/Upstash                                                    | Server-side login sessions                        | Eight-hour absolute expiry; admin deactivation revokes immediately                                                       |
| Job messages              | job id only                                                                                                                          | Redis/Upstash Celery broker                                      | Deliver slow work                                 | Broker visibility/queue policy; no names or grade payloads                                                               |
| Generated output          | PDF/XLSX blob and machine metadata                                                                                                   | Postgres `job_runs`                                              | Authorized download after generation              | Blob expires after 24 hours; job metadata retained as operations evidence                                                |
| Backups                   | age-encrypted full database dump and checksum; per archived year the report PDFs, workbook, encrypted dump, manifest                 | School-owned Google Shared Drive                                 | Disaster recovery; long-term school records       | School controller holds the age identity; the newest 7 nightly copies are kept, archives until the school deletes them   |
| Error telemetry           | request/job/batch ids, route, status, duration, error code                                                                           | School-approved Sentry project                                   | Diagnose failures                                 | School controller; bodies/locals disabled, events and breadcrumbs scrubbed                                               |
| Demo visitor link         | `demo_visitors.subject_hash` (keyed hash of Google `sub`), `expires_at`; synthetic email and generated name on `users`               | Postgres, public demo only                                       | Reuse one temporary demo account for 24 hours     | Hash nulled on last logout or expiry; rows deleted by the nightly demo reset; absent in school mode                      |

Not collected: gender, birthdate, national id, home address, browser tokens, or passwords.

## Retained and generated data

- Retiring an assessment column does not erase its saved text, versions, or audit trail. Pending
  ADR-063 deactivates middle-English opinion fields and omits them from normal grids/history/PDFs;
  audit/workbook exports and backups retain the underlying records.
- A report identity audit stores before/after names and signature digests, not copies of every
  prior PNG. The current signature is on the user record; older backups/PDFs may preserve old images.
- Direct PDF responses are not stored as job blobs. Downloaded files and school Drive archive
  bundles have the school's retention policy, independently of the 24-hour job-download expiry.
  Expired job blobs remain in storage until `flrc purge-job-outputs` removes them.
- Dump files are age-encrypted. Archive PDFs/workbooks are readable files protected by school
  Shared Drive membership. `BACKUP_RETAIN` controls nightly dump retention (default 7);
  archived-year bundles are not automatically pruned.
- School sessions default to eight hours and may be shorter. Public demo sessions can last up to
  the visitor's 24-hour lifetime; the temporary subject hash is still a stored identity link.

See [SECURITY.md](SECURITY.md) for access boundaries and [RESTORE-DRILLS.md](RESTORE-DRILLS.md)
for recovery of database identities plus separately maintained private report assets.
