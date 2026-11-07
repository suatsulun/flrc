# Backups and restore

This document covers the school backup scheduler, manual recovery and human restore drills. Read this before relying on a backup or restoring school records; incident coordination belongs in [Incident response](incident-response.md).

## Stored copies and prerequisites

The `backup` service uses the backend image and `flrc backup schedule` ([ADR-056](../adr/056-encrypted-nightly-backups-to-the-school-s-shared-drive.md)). Its implementation is `apps/backend/src/flrc/modules/backup/`.

| Setting                        | Purpose/default                                                     |
| ------------------------------ | ------------------------------------------------------------------- |
| `DATABASE_URL_DIRECT`          | Direct PostgreSQL dump/restore connection; not a transaction pooler |
| `BACKUP_DIR`                   | Working files and `status.json`; default `/srv/backups`             |
| `BACKUP_AGE_RECIPIENT`         | Public age encryption recipient                                     |
| `BACKUP_AGE_IDENTITY`          | Secret age identity needed for restore tests/recovery               |
| `GDRIVE_SERVICE_ACCOUNT_JSON`  | One-line service-account JSON key                                   |
| `GDRIVE_BACKUP_FOLDER_ID`      | Backup folder in a school-owned Shared Drive                        |
| `BACKUP_AT`, `BACKUP_TIMEZONE` | `02:30`, `Europe/Istanbul`                                          |
| `BACKUP_RETAIN`                | Newest 7 nightly encrypted dumps                                    |
| `BACKUP_RESTORE_TEST_DAY`      | Day 1 of each month                                                 |

Enable Drive API and grant the service account suitable Shared Drive access to upload/delete backup files (for example Content manager). A service account's own storage is not the target. Generate the age pair with `docker compose run --rm backup flrc backup keygen`. Keep the identity in approved school secret storage plus an independently recoverable sealed copy; losing it makes encrypted dumps unrecoverable.

The backup mount must be writable by UID 10001. Run backup operations serially: the implementation shares and clears `BACKUP_DIR/work`, so do not overlap manual commands with the scheduler.

## What a scheduled night does

1. Attempts to purge expired seven-day admin undo records and expired/unfinished job output parts before the new dump. A purge failure is logged but does not stop the backup; inspect maintenance errors rather than assuming expired snapshots cannot enter a new dump.
2. Produces a PostgreSQL custom-format dump, computes plaintext checksum, age-encrypts it, removes the plaintext working copy, uploads `flrc-<UTC timestamp>.dump.age` and its `.sha256` companion, then prunes older successful dumps.
3. On the configured monthly day, downloads the newest backup, verifies the checksum **if a sidecar is present**, decrypts, restores into a scratch database and checks schema revision plus aggregate student/user/grade counts. It rejects a different revision from the live database and empty students/users.
4. Bundles archived years lacking a completed manifest into `archives/<year>/`: nonempty report sets for both semesters, workbook, encrypted **full database** dump and checksum/count manifest. Existing completed archives are skipped, not regenerated when templates change.

Dump files are encrypted; archive PDFs/workbooks are **not** age-encrypted and depend on Shared Drive access controls. Year bundles are never automatically pruned. The full dump in a year bundle is not limited to that year's data. Cleanup of temporary files does not prove secure erasure of underlying storage.

## Prove backup operation

From the private deployment directory:

```bash
docker compose run --rm backup flrc backup run
docker compose run --rm backup flrc backup restore-test
docker compose run --rm backup flrc backup archives
docker compose run --rm backup flrc backup status
```

Read `backups/status.json` and retain only filenames, checksums, revisions, aggregate counts and outcomes in private operator records. A configured schedule is not evidence of a successful backup.

The private template's `.github/workflows/backup-check.yml` runs at 08:00 Europe/Istanbul. Scheduled execution requires `SCHOOL_DEPLOY_ENABLED=true`; manual execution bypasses that flag. It reads status over SSH using the deploy credentials and fails for no successful backup, success older than 26 hours, a recorded backup error, a failed/older-than-40-day restore test, or archive error. **No restore test yet produces a warning, not a failed job**; require an actual initial restore test before launch. There is no backup workflow in the public application's root workflows.

## Human restore drill

At least once per semester, prove recovery on a separate school-approved isolated machine, not a developer playground or test database. Obtain the backup from Drive and the identity independently from its recovery store.

```bash
sha256sum -c flrc-example.dump.age.sha256
age --decrypt -i identity.txt -o flrc.dump flrc-example.dump.age
createdb --host=<recovery-db-host> --username=<recovery-user> flrc_restore
pg_restore --host=<recovery-db-host> --username=<recovery-user> \
  --dbname=flrc_restore --no-owner --no-privileges flrc.dump
```

Use PostgreSQL tooling compatible with the dump and pass credentials via approved secret handling, not command history. These commands intentionally target a new scratch database, never the live database.

1. Verify the checksum before decrypting. Restore with the application image compatible with the backup's Alembic revision before applying any newer migrations.
2. Compare aggregate counts and schema revision with saved backup evidence. Through an isolated authenticated app, verify one archived read, correct year/stage-scoped enrollment numbers and one report preview/download.
3. Verify teacher report identity/signature presence without copying identity data into the drill record. Restore the matching private branding/templates/principal assets separately: the database does not contain them.
4. Check year archive manifest checksums and readable PDF/workbook output. Hidden middle-English comments are intentionally retained in storage; missing display columns do not imply data loss.
5. Remove the scratch database, decrypted host/container files and local identity copies. Record date, backup filename/checksum, image and branding revisions, Alembic revision, aggregate counts, duration and outcome in private operational evidence—not this public repository.

For a real recovery, stop writes, preserve evidence, restore into a **new** database, validate and explicitly switch application credentials. Do not overwrite the only surviving database or reflexively downgrade Alembic. Reset/revoke sessions as required by the incident; database restoration alone does not clear Redis or invalidate downloaded files.
