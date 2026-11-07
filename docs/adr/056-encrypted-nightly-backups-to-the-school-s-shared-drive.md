# ADR-056: Encrypted nightly backups to the school's Shared Drive, proven monthly

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.5 (school operations)

## Context

ARCH §7.5 promised weekly dumps to school-owned Google Drive from a GitHub Actions workflow. On the
school-hosted profile (ADR-055), the database has no public port, the school wants daily copies kept
for a week, academic years must remain retrievable for years, and a backup is a hypothesis until a
restore succeeds. Service accounts have no Drive storage of their own, so the destination must be
a Shared Drive the school owns.

## Decision

A `backup` service in the school's Compose file runs the backend image with `flrc backup schedule`.
Every night at `BACKUP_AT` (02:30 Europe/Istanbul) it runs `pg_dump` with the PostgreSQL 18 client
now included in the image, encrypts the dump with age to the school's recipient key, uploads the
file and a SHA-256 companion to the school's Shared Drive folder through a service account, and
keeps the newest `BACKUP_RETAIN` (7) copies by upload time, so a failed night never shrinks the set.
On day `BACKUP_RESTORE_TEST_DAY` of each month it downloads the newest copy, verifies the checksum,
decrypts it with the identity the server holds, restores it into a scratch database on the same
server, checks the schema revision against the live one and that students and users are present,
and drops the scratch database. Every run also bundles each academic year in the `archived` state
that has no `archives/<label>/manifest.json` yet: every non-empty report set per semester as PDF,
the whole-year workbook, an encrypted full dump from that moment, and a manifest with checksums,
counts, the application version, and the schema revision. Archives are never pruned.

The service writes `status.json` into a bind-mounted `backups/` folder; nothing in it is personal
data. The deployment repository's daily workflow reads that file over SSH and fails when the last
success is older than 26 hours, the last run failed, or the restore test failed or is older than
40 days. A person performs the drill in [operations/backups-and-restore.md](../operations/backups-and-restore.md) each semester with only the Drive
folder and the identity from the school safe. The identity and the service-account key live only
in the server's `.env`; the recipient alone cannot decrypt anything.

## Alternatives considered

- Keep the GitHub Actions workflow: it cannot reach a database with no public port, and it would
  hold the school's credentials in a repository secret.
- Hetzner Storage Box with restic: decided against earlier because the school already owns Google
  Workspace and wants one vendor for its records.
- A dedicated backup image: the backend image already has the application, the reports, and the
  workbook builder that the year archive needs; adding the client tools was smaller.
- Age-based retention: it deletes the last good copy after a week of failures; count-based
  retention cannot.

## Consequences

- One `.env` block and one Shared Drive folder configure the whole backup story.
- Losing the age identity loses every backup; the runbook requires two copies outside the server.
- The backend image grows by the PostgreSQL client tools and the Drive libraries.
- `scripts/upload_backup_to_drive.py` and the weekly workflow are removed; the module replaces
  them.

## Supersedes / Superseded by

Supersedes the weekly Drive workflow described in handbook step 4.5 and ARCH §7.5.
