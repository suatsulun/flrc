# Restore drills

Record every restore here without student names or copied row data.

| Date                                     | Backup filename | SHA-256 verified | Student rows | Grade rows | Archived read | Operator/result        |
| ---------------------------------------- | --------------- | ---------------- | -----------: | ---------: | ------------- | ---------------------- |
| _Pending school-owned production backup_ | —               | —                |            — |          — | —             | Owner: school operator |

## Drill procedure

1. Download the `.dump` and `.sha256` files from the school-owned Drive folder.
2. Run `sha256sum -c <file>.dump.sha256`.
3. Create the scratch database: `docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_restore`.
4. Copy and restore with `pg_restore --no-owner --no-privileges`.
5. Query only aggregate counts, point a temporary API at `flrc_restore`, and verify one archived
   read. Confirm the restored archive reads its number from `enrollments`, active years have no null
   enrollment numbers, and reuse of the same number across different years is preserved.
6. Delete the scratch database after recording the result.

The first production-format drill remains a launch gate because it requires the school’s Drive and database credentials.
