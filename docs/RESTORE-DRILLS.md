# Restore drills

Record every restore here without student names or copied row data.

Handbook Step 4.5. The documentation review on 2026-09-11 did not perform a restore or verify
school-owned backup access; the pending row below remains uncompleted. Use a school-approved,
isolated recovery environment, separate from developer demo/test databases and their cleanup jobs.

| Date                                     | Backup filename | SHA-256 verified | Student rows | Grade rows | Archived read | Operator/result        |
| ---------------------------------------- | --------------- | ---------------- | -----------: | ---------: | ------------- | ---------------------- |
| _Pending school-owned production backup_ | none            | none             |          n/a |        n/a | none          | Owner: school operator |

## Drill procedure (once per semester, by a person)

The monthly automated restore test proves the newest copy restores on the server. The drill proves
a person can do it somewhere else with nothing but the Drive folder and the key from the safe.

1. From the school's Shared Drive folder, download the newest `flrc-….dump.age` and its
   `.sha256` companion; from the safe or the password manager, obtain the age identity.
2. Verify and decrypt on a machine with [age](https://github.com/FiloSottile/age) installed:

   ```bash
   sha256sum -c flrc-….dump.age.sha256
   age --decrypt -i identity.txt -o flrc.dump flrc-….dump.age
   ```

3. Create a scratch database in the local development stack and restore into it:

   ```bash
   docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_restore
   docker compose -f infra/compose/compose.dev.yaml cp flrc.dump postgres:/tmp/flrc.dump
   docker compose -f infra/compose/compose.dev.yaml exec postgres \
     pg_restore -U flrc -d flrc_restore --no-owner --no-privileges /tmp/flrc.dump
   ```

4. Compare the restored Alembic revision with the backup manifest and use a compatible application
   image before applying any newer migrations. Query only aggregate counts, point a temporary API
   at `flrc_restore`, and verify one archived
   read. Confirm the restored archive reads its number from `enrollments`, active years have no
   null enrollment numbers, and reuse of the same number across different years is preserved.
5. Verify report names/signature presence through authorized views without copying images or names
   into this log. Restore the matching private branding/templates/principal assets separately;
   they are not part of the database dump. For ADR-063-era backups, distinguish retained text
   records from the intentionally hidden middle-English opinion fields.
6. Delete the scratch database, the decrypted dump on both host and container, and the local
   identity copy, then record the drill in the table above.

Year archives are checked the same way: open the PDFs and the workbook from `archives/<year>/`
and compare `manifest.json` checksums with `sha256sum`.

Record the application image tag, restored migration revision, aggregate counts, and outcome with
each future drill. Never mark an automated schedule or a source-only review as a completed restore.
