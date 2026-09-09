# Restore drills

Record every restore here without student names or copied row data.

| Date                                     | Backup filename | SHA-256 verified | Student rows | Grade rows | Archived read | Operator/result        |
| ---------------------------------------- | --------------- | ---------------- | -----------: | ---------: | ------------- | ---------------------- |
| _Pending school-owned production backup_ | —               | —                |            — |          — | —             | Owner: school operator |

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
   docker cp flrc.dump compose-postgres-1:/tmp/flrc.dump
   docker compose -f infra/compose/compose.dev.yaml exec postgres \
     pg_restore -U flrc -d flrc_restore --no-owner --no-privileges /tmp/flrc.dump
   ```

4. Query only aggregate counts, point a temporary API at `flrc_restore`, and verify one archived
   read. Confirm the restored archive reads its number from `enrollments`, active years have no
   null enrollment numbers, and reuse of the same number across different years is preserved.
5. Delete the scratch database, the decrypted dump, and the local copy of the identity, then
   record the drill in the table above.

Year archives are checked the same way: open the PDFs and the workbook from `archives/<year>/`
and compare `manifest.json` checksums with `sha256sum`.
