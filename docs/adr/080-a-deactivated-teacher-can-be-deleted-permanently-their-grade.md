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
- One lock order per account: whatever writes or records something about an account locks the
  account row first: account edits and signature changes exclusively, assignment writers
  (single slot and matrix), the year rollover, grid saves and grant requests (on the caller's own
  account) shared, and undo before it locks the action row (exclusive for account actions, shared
  on every teacher an assignment change names). The deletion holds the row exclusively, then
  deletes assignments, then scrubs actions. So no action naming the account is recorded after the
  scrub, assignment writers revalidate the account after waiting and refuse an inactive or deleted
  one, the rollover leaves a deleted teacher's slots empty, a save or grant request that raced the
  deactivation and deletion answers `401 not_registered` instead of saving through a removed
  grant or recording a new one, and nothing deadlocks with the deletion.
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

Extends ADR-075 (undo records) and Step 3.2's deactivation; supersedes nothing.
