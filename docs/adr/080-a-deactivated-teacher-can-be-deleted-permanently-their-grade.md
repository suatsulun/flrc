# ADR-080: A deactivated teacher can be deleted permanently; their grade history stays

[ADR index](README.md)

**Status:** Accepted  
**Date:** 2026-11-07  
**Phase:** 3.2 (teachers and access) maintenance

## Context

A teacher who leaves the school could only be deactivated. The account stayed in the teachers
list with its name, e-mail, Google identity, printed name and signature, and its e-mail could not
be added again for a new account. The grades the teacher entered, their audit trail and save
batches must stay: report cards and accountability depend on them, and every one of those rows
points at the account.

## Decision

- `DELETE /api/admin/users/{id}` (administrators only) permanently erases a **deactivated**
  account's personal data and answers `{deleted: true, revoked_sessions}`. Refusals:
  `404 unknown_user` (also for an already deleted account), `409 cannot_delete_self`,
  `403 visitor_protected` (demo visitors, ADR-051), `409 user_active`.
- The row stays, so grade values, grade audit, save batches and job rows keep valid foreign keys.
  Its name becomes "Silinmiş öğretmen", which every history view shows through the stored name;
  the e-mail becomes the unique, non-routable `deleted-<id>@deleted.invalid`, so the real address
  can be added again as a new account; the Google subject, report name, signature and admin and
  coordinator flags are cleared; `users.deleted_at` marks the deletion.
- The account's teaching assignments and its own `report_identity_audits` rows are deleted. Its
  override grants are deleted too, except a grant a save went through: `audit_entries.via_grant_id`
  keeps naming it, so it only expires (a grant holds no personal data). Remaining sessions are
  revoked after the commit.
- Recorded admin actions (ADR-075) lose the account's personal data in the same transaction:
  `user.create`, `user.edit`, `signature.upload` and `signature.delete` for the account keep only
  `{"user_id"}` as their snapshot, drop the kept image and show the erased name without e-mail or
  name changes; `assignments.replace` entries show the erased name for the account's slots.
- One lock order for the writes that touch accounts, assignments, grants, recorded actions or
  report identity: **accounts by id → year → class → assignment rows by id → action rows**. The
  accounts are the acting administrator (or, for a teacher's own grid write, the teacher) and the
  accounts the write names, locked together in id order: shared, except the one account whose row
  the write changes, which is locked exclusively.
- Administrator writes that change accounts or roles, cannot be undone, or touch assignments
  check the acting administrator again under that lock: account create and edit, the signature
  routes, permanent deletion, both assignment writers, undo and year close. One deactivated or
  deleted meanwhile is refused with `401 not_registered`, one demoted meanwhile with
  `403 forbidden`, before anything is written, erased or archived. Other administrator writes
  (classes, rosters, fields, imports) rely on the request's authorization like any request already
  under way: an administrator removed meanwhile finishes at most that one request.

  | Write                                         | Locks, in order                                                                                                                                                                                                    |
  | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
  | Account create                                | administrator (shared) → the new action                                                                                                                                                                            |
  | Account edit; signature view, upload, removal | administrator (shared) and account (exclusive), by id → its identity audit → the new action                                                                                                                        |
  | Permanent deletion                            | administrator (shared) and account (exclusive), by id → the account's slots by id → its grants → its identity audits → the actions naming it, by id                                                                |
  | Assignment matrix and single slot             | administrator and destination teachers (shared), by id → year → the classes' slots by id → the new action                                                                                                          |
  | Year close and rollover                       | administrator and the year's slot holders (shared), by id → year → the new year's rows                                                                                                                             |
  | Grid save, grid undo, grant request           | the teacher's own account (shared) → grants (save, grant request) or the last save batch (undo) → the fields written, key share, by id → grade values and save batch → grade audit                                 |
  | Undo of a recorded action                     | administrator (shared) and the accounts it names (exclusive for an account action, shared for an assignment change), by id → what the handler restores (year, class, roster, fields, slots by id) → the action row |

  Undos of one action also take a transaction-scoped advisory lock on the action's id before any
  row lock, so a second undo waits and then answers `409 action_already_undone` instead of
  restoring the same rows twice; nothing else takes that key. The expiry purge takes no lock, so an
  undo that waited past its action's expiry may find the action row gone when it locks it last;
  it then rolls back and answers `410 action_expired`. A holder assigned while a year close
  waited for the holders is locked after the year; nothing that locks an account exclusively goes
  on to lock a year, so that cannot deadlock. So no action naming an account is recorded after its
  scrub, assignment writers refuse an inactive or deleted teacher, the rollover leaves a deleted
  teacher's slots empty, a checked write whose own account raced the deactivation and deletion is
  refused instead of saving through a removed grant or recording, undoing, erasing or archiving
  anything, and nothing deadlocks with the deletion.

- Report rendering keeps teachers' signatures out of every process-wide state: the renderer's
  only process-wide memo holds the fixed artwork's bytes (logo, faces, watermarks, overlay
  assets), and WeasyPrint's parsed images, the asset fetcher and the signatures live only as long
  as the document being rendered, in the API process and in render processes alike; a render that
  printed a signature clears `urllib.parse.urlsplit`'s memo, which WeasyPrint fills with every URL
  a document uses. A parallel
  download uses no process pool: an executor's manager and queue threads keep the documents they
  were sent, and a worker killed in the middle of its result could leave them blocked for good.
  Instead each wave starts one process per document, each with its own pipe whose only write end
  is the child's: the child renders, writes its PDF and exits, and the parent reads every pipe
  without blocking until end of file, so a child that dies yields end of file at once. Whatever
  happens, every process is terminated (then killed) if still running and joined, and every pipe
  is closed. A process that exits without its whole PDF makes the download fall back to the serial
  render. The forkserver preloads the renderer, so a process costs a fork, not a WeasyPrint import.
  Concurrent renders share one budget of `render_worker_limit()` processes per OS process: a
  render reserves its workers before starting a wave and releases them after the last process has
  exited, so a second download waits rather than starting more processes. A parallel render that
  has not finished after ten minutes (`RENDER_DEADLINE_SECONDS`) has a stuck process: its
  processes are stopped, the budget is given back and the render fails, so one stuck process
  cannot hold the budget for good. A deleted teacher's signature cannot be printed again or read
  back from a running process.
- No undo can bring the account back: undo handlers refuse a deleted account with
  `target_missing`.
- Deleted accounts are left out of `/api/admin/users` and the `/api/users` teacher picker; editing
  or a signature request for one answers `404 unknown_user`. The deletion itself is not recorded
  as an undoable action.
- The admin app offers "Kalıcı olarak sil" only on deactivated rows. Its confirmation lists what is
  erased and what is kept; the delete button stays disabled for five seconds, counting down, every
  time the dialog opens, while Cancel works at once (shared `CountdownConfirmDialog`, which the
  PDF leave guard also uses). The success toast says the deletion is permanent and has no Undo.

## Alternatives considered

- Delete the `users` row and cascade: loses grades and their history, or needs nullable actor
  columns everywhere.
- Reassign history to a shared "deleted teacher" account: rewrites every grade, audit and batch
  row and merges different people's history.
- Keep the deactivated account and only free the e-mail: leaves names, identities and signatures
  on file with no purpose.
- Make the deletion undoable for seven days: keeping the erased data to restore it defeats the
  erasure.

## Consequences

- History and audit views read "Silinmiş öğretmen" for everything the teacher entered; an archived
  year's re-rendered report cards no longer name a teacher for slots they held.
- Backups taken before the deletion and already generated PDFs still contain the data until they
  expire under the school's policy ([privacy data map](../security/privacy-data-map.md)).
- Undo of earlier actions about the account is refused instead of silently skipped.

## Supersedes / Superseded by

Extends ADR-075 (undo records) and Step 3.2's deactivation. Supersedes ADR-046's warm renderer
pool: a parallel download renders each document in a process of its own, with no executor.
