# Data model

PostgreSQL stores stable student identity separately from yearly placement, assessments and operational history. Read this when changing models, enrollment behavior, lifecycle or migrations; the authoritative mapping is `apps/backend/src/flrc/db/models.py`, with database-only behavior in `apps/backend/migrations/versions/`.

## Schema inventory

The application has **17 mapped tables**, plus Alembic's `alembic_version` bookkeeping table. Unless noted otherwise, mapped entities use an identity bigint `id` and `TimestampMixin` creation/update timestamps. Foreign keys below name their target table; the ORM does not replace explicit joins with a relationship graph.

| Table                    | Purpose, key columns and invariants                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `users`                  | Local Google allowlist and role flags. Unique indexed `email` and nullable unique indexed `google_subject`; `full_name`, `is_admin`, `is_coordinator`, `is_active`; `teaching_field` is English/German/French. English requires `teaching_stage` primary/middle; German/French require null stage. Printed identity uses `report_name`, deferred `signature_png`, `signature_digest`. `deleted_at` marks irreversible anonymization. |
| `report_identity_audits` | Changes to a user's printed identity. `user_id → users` cascades on physical deletion; nullable `actor_id → users` uses SET NULL. `before`/`after` JSON record metadata, never image bytes.                                                                                                                                                                                                                                          |
| `academic_years`         | Unique `label`; status `setup`, `active` or `archived`. Endpoint transactions enforce one active year.                                                                                                                                                                                                                                                                                                                               |
| `semesters`              | `year_id → academic_years`, `number` 1 or 2, status open/locked. Unique `(year_id,number)` and partial unique index allowing at most one open term per year.                                                                                                                                                                                                                                                                         |
| `school_classes`         | `year_id → academic_years`, `grade_level` 0–8, `section`; unique `(year_id,grade_level,section)`. Grade 0 is Hazırlık.                                                                                                                                                                                                                                                                                                               |
| `students`               | Stable person identity (`id`), `full_name`, indexed normalized `search_name`. No school number or class FK.                                                                                                                                                                                                                                                                                                                          |
| `enrollments`            | Yearly placement: `student_id → students`, `year_id → academic_years`, `class_id → school_classes`; unique student/year. Nullable positive `school_number`; unique `(year_id,stage,school_number)`. `stage` is derived by database triggers, not application input.                                                                                                                                                                  |
| `student_languages`      | Yearly second foreign language: student/year FKs, language German/French; unique `(student_id,year_id)`.                                                                                                                                                                                                                                                                                                                             |
| `teaching_assignments`   | `class_id → school_classes`, `user_id → users`, `role` main/skills/german/french. Unique `(class_id,role)` gives one teacher per slot; a teacher may occupy multiple slots.                                                                                                                                                                                                                                                          |
| `column_definitions`     | `semester_id → semesters`, grade 0–8, subject English/German/French, `value_type` score/scale3/text, `owner_role` main/skills/german/french. JSON `labels`, nullable `group_labels`, `counts_in_average`, `position`, `is_active`; indexed scope/position. Definitions are shared across every class in the same semester/grade/subject.                                                                                             |
| `grade_values`           | Student/definition FKs; unique `(student_id,column_definition_id)`. Nullable `score` 0–100, `scale` 1–3, `text_value`; `version`, `updated_by → users`. The service selects the correct typed value and clears other value columns.                                                                                                                                                                                                  |
| `save_batches`           | One applied grade-save action: `user_id → users`, `class_id → school_classes`, `is_undo`, `undone`. Groups audit entries for last-save undo.                                                                                                                                                                                                                                                                                         |
| `audit_entries`          | Grade history: batch/actor/student/definition FKs, `old_existed`, old/new score/scale/text, `forced`, nullable `via_grant_id → override_grants`. Records values in the same transaction as their save.                                                                                                                                                                                                                               |
| `override_grants`        | Temporary out-of-assignment permission: user/class FKs, owner `role`, `expires_at`; unique `(user_id,class_id,role)`. Used grants remain as expired historical references when an account is erased.                                                                                                                                                                                                                                 |
| `job_runs`               | Durable report-set/year-export requests: `kind`, queued/running/succeeded/failed `status`, requester FK, JSON payload, nonnegative progress/total, start/finish/error fields. Deferred output blob, filename/MIME/size/expiry. Nullable self-FK `parent_id` (CASCADE) and `part` represent numbered ZIP parts.                                                                                                                       |
| `demo_visitors`          | `user_id → users` is the primary key. Nullable unique `subject_hash`, `expires_at`, `scrubbed_at`; temporary pseudonymous public-demo identities, never school accounts.                                                                                                                                                                                                                                                             |
| `admin_actions`          | Undo snapshots: nullable actor/undoer user FKs (SET NULL), `kind`, JSON `summary`/`undo_data`, deferred optional signature `blob`, created/expiry/undone timestamps. Explicit timestamps, not `TimestampMixin`.                                                                                                                                                                                                                      |

## Identity and placement

`Student.id` is the person key. A school number identifies an **enrollment**, not a person. Primary covers Hazırlık–4; middle covers 5–8. A primary pupil and middle-school pupil may have the same number in the same year. Unnumbered setup enrollments are allowed, but activation refuses them. See [ADR-070](../adr/070-school-numbers-are-unique-per-stage.md).

Migration `9b3e5d7f1c20` installs `stage_for_grade`, `enrollments_derive_stage` and `school_classes_sync_enrollment_stage`. Inserts, class changes, direct stage writes and class moves across the grade-4/5 boundary rederive stage. Do not set it yourself. A stage-crossing class move that creates a number collision must fail rather than renumber students silently.

Moving a student changes the enrollment, not the student identity or grade rows. Grades point to definitions, whose semester identifies the year; they do not point directly to classes ([ADR-007](../adr/007-grade-rows-do-not-directly-reference-classes.md)). Current roster joins decide class membership. Student language is also year-specific and filters German/French rosters and reports.

## Academic lifecycle

`modules/administration/lifecycle.py` owns the transitions; write guards in `auth/dependencies.py` require the relevant active/open state.

1. Create a `setup` year with both semesters locked. Labels must describe consecutive years.
2. Activate only with two semesters, no other active year and no unnumbered enrollments; semester 1 opens, semester 2 stays locked.
3. Advance locks semester 1 and opens semester 2. Locking semester 2 leaves both closed. Reopening an active year's selected semester locks the other first.
4. Closing requires an active year with both terms locked, exact typed year-label confirmation and the SHA-256 digest of the current exported audit CSV. A changed audit invalidates the earlier confirmation.
5. Close archives the source year and attempts automatic creation of the next setup year in the same transaction. Rollover copies eligible structure/assignments/identity links and assessment definitions, not saved grades or grade history. Promoted pupils receive fresh sequential school numbers separately per stage.

Hazırlık and grade 4 wait for school placement rather than automatically carrying sections into grades 1 and 5; grade 8 graduates. This is [ADR-066](../adr/066-rollover-stops-at-stage-boundaries-and-the-roster-import.md). Never infer a pupil's new section from their old number.

Archived-year screens are read-only. Lifecycle changes lock year/semester rows; they are not entries in the ordinary seven-day administrative undo system.

## Columns and programme rules

Columns are data, not schema ([ADR-008](../adr/008-report-columns-are-data-not-schema.md)). A new assessment column is a `ColumnDefinition`, not an Alembic migration or new SQL column. Shared definitions mean editing/deactivating a column affects all classes in its semester/grade/subject scope.

- `owner_role` describes responsibility, not a second global user role. Assignment slots link these responsibilities to teachers.
- `academics/programme.py` is the shared source for stage boundaries and permitted types. Grade 4 German/French allow ratings and text, not scores/averages.
- English grades 5–8 have no active teacher-opinion text columns. Migration `82a91f4c6d30` deactivates them without deleting old values/audits, and its downgrade deliberately does not reactivate them ([ADR-063](../adr/063-no-opinion-field-in-middle-school-english.md)).
- `labels`/`group_labels` are localized data. Naming uses the subject's language; do not confuse labels with UI translation keys ([ADR-072](../adr/072-fields-are-named-in-their-subject-s-language.md)).

## Grades and history

A grade save validates membership/type/permission and checks the expected version. Applied rows, their old/new audit snapshots and one save batch commit together. Empty/cleared values are distinct from an absent historical row through `old_existed`. Conflicts and rejections do not become successful audit writes.

Grade undo is separate from administrative undo: it targets the caller's latest batch for that class, checks current roster/column/writable state and compares current values to what the batch wrote before restoring. Undo produces its own audit history and advances versions (or removes a formerly absent row). See [backend concurrency rules](backend.md#transaction-and-concurrency-rules).

Administrative snapshots can contain personal data and replaced signature images, so expire/purge after seven days ([ADR-075](../adr/075-admin-changes-can-be-undone-for-seven-days-and-conflicts.md)). Permanent teacher deletion requires deactivation first, scrubs identity/signatures and related snapshots/audits, removes assignments, ends grants and revokes sessions. The anonymized user row remains for grade/history FKs; it is not restorable ([ADR-080](../adr/080-a-deactivated-teacher-can-be-deleted-permanently-their-grade.md)).

Job blobs/part lifetimes are specified in [reports and jobs](reports-and-jobs.md). Demo identity and session lifetimes are specified in [authentication](auth-and-sessions.md). Data sensitivity/retention ownership belongs in the [privacy data map](../security/privacy-data-map.md).

## Migrations and inspection

Use Alembic for every schema change. Prefer additive-first changes, review generated SQL and constraints, and supply a deliberate downgrade. Do not edit already-applied migrations or rewrite grade/audit data to make a rollback convenient. Some downgrades intentionally preserve retired data or refuse an incompatible state: the stage-number migration refuses year-wide uniqueness when stages share numbers.

From `apps/backend`, inspect without changing the schema:

```bash
uv run alembic heads
uv run alembic history
uv run alembic current
```

`current` connects to the configured database. Alembic uses `FLRC_MIGRATIONS_URL` when supplied, otherwise `DATABASE_URL_DIRECT`; application traffic uses `DATABASE_URL`. In `psql` connected to the intended database, `\dt`, `\d+ enrollments`, `\d+ grade_values` and `\d+ job_runs` show live tables, constraints, indexes and triggers. Model files describe desired mapping; migration files and the target database establish actual schema state. Production execution and rollback precautions belong in [deployment](../operations/deployment.md).
