# ADR-075: Admin changes can be undone for seven days, and conflicts refuse the undo

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** 3.x (administration) maintenance

## Context

Administrators edit rosters, classes, fields, teachers and assignments in a live school year. A
wrong drag-and-drop move, a deleted field or a replaced signature could only be repaired by hand,
and only if someone remembered the previous values. Teachers' grade saves already have their own
undo (Step 2.8); administrative writes had none.

## Decision

- Every undoable admin write adds one `admin_actions` row in the same transaction as the write:
  `kind`, the acting admin, `summary.params` (display names resolved at write time: student,
  class, field, teacher, from/to classes, counts), `undo_data` (the snapshot that restores the
  previous rows) and, for signatures, the replaced or removed image in a deferred `blob` column.
  Rows expire seven days after the write (`ADMIN_ACTION_TTL`).
- Kinds are stable strings the admin app translates: `student.add`, `student.remove`,
  `student.move`, `student.edit`, `student.language`, `class.create`, `class.edit`,
  `class.delete`, `field.create`, `field.delete`, `field.edit`, `field.reorder`, `field.copy`,
  `user.create`, `user.edit`, `signature.upload`, `signature.delete`, `assignments.replace`.
  Year lifecycle actions, year creation and roster import commits are not undoable.
- Each of those endpoints returns a top-level `action_id`. Write responses use their own models
  (`ColumnWriteOut`, `RosterStudentWriteOut`, ...), so read models stay unchanged; the assignment
  matrix `PUT` now answers `{slots, action_id}`.
- `GET /api/admin/actions?cursor=&limit=` lists actions newest first with
  `status: available | undone | expired`. `POST /api/admin/actions/{id}/undo` restores the
  previous state in one transaction. Any administrator may undo any action; coordinators and
  teachers get 403.
- An undo first checks that the data still looks the way the action left it and that the previous
  state is valid today, with the original endpoints' rules (school numbers per stage, class
  duplicates and use, `editable_semester`, the last-admin and self-deactivation rules, teacher
  subject and stage per role). If not, it refuses with
  `409 {"code": "undo_blocked", "reason", "params"}` naming the blocker, for example
  `school_number_taken` with the number, the pupil holding it and their class, and nothing changes.
  Other answers: `404 unknown_action`, `409 action_already_undone`, `410 action_expired`.
- Undoing an add removes what was added unless it is in use: a new field with grades
  (`field_has_grades`) or with grade history whose grades were undone (`field_has_history`; the
  audit trail is never touched), a class with pupils (`class_in_use`), an account that signed in
  or has work (`user_in_use`). An added pupil who already has grades follows ordinary roster
  removal: the enrollment goes, the person and grades stay; a pupil with nothing attached is
  deleted again. Deleting a field that only has such history hides it, like a graded field.
- Deleted rows return with their original ids (classes, fields), so later actions that refer to
  them still apply. A hidden field with grades is shown again with its grades.
- Every recorded write locks the rows it changes before reading their previous values and holds
  the lock until it commits with its action; undo handlers take the same locks before checking.
  A pupil's number, class and second language are guarded by the year, then their enrollment
  row, so language writes and their undo cannot interleave; every roster write, new pupil,
  removal and undo locks in that order, so none of them deadlock. Grade saves and grid undo
  key-share-lock the fields they write in id order before writing; removing copied fields locks
  them `FOR UPDATE` in the same order, so it waits for a save and is then refused by its grades.
  Field reorders and their undo change only positions and lock the fields `FOR NO KEY UPDATE`,
  which grade saves' key-share locks do not wait for.
- The backup sidecar deletes expired rows and their images each night before the dump
  (`flrc purge-admin-actions` does the same by hand). Until then an expired row is listed as
  `expired` and cannot be undone.

## Alternatives considered

- Event-sourcing every admin table: undo and history for free, but every reader would replay
  events and every existing query would change.
- Undo by replaying the request in reverse without a snapshot: deleted fields, removed pupils and
  replaced images cannot be recreated from the request.
- Overwrite later changes on undo ("last undo wins"): silently discards a colleague's newer edit.
- Keep actions until the year is archived: snapshots hold pupils' names and signature images
  longer than an accidental change needs.

## Consequences

- For seven days the database keeps copies of removed roster rows, deleted fields and replaced
  signature images ([privacy data map](../security/privacy-data-map.md)). Backups taken in that
  window include them.
- An undo that conflicts with later work is refused as a whole; the admin first undoes or edits
  the later change. Edits of other attributes do not block an undo.
- The nightly purge depends on the backup sidecar; an installation without it keeps expired rows
  (still refused as `expired`) until `flrc purge-admin-actions` runs.

## Supersedes / Superseded by

Complements Step 2.8's grade undo; does not change it.
