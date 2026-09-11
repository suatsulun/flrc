# Upgrading to 1.2.0

These notes describe the local `v1.2.0` tag. The 2026-09-11 documentation refresh confirmed that
current HEAD and pending working-tree edits extend that tag even though manifests still say
`1.2.0`. Image publication and installed school versions were not checked. See
[RELEASING.md](RELEASING.md) before assigning newer changes to a release.

This release adds teacher report names and PNG signatures, private school report templates and
principal identities, notes-only filtering, and student/class bulk 1-2-3 drafts. It also includes
the scheduled-operation and branding-file security fixes merged since 1.1.0.

## Database and compatibility

Migration `e2a91c743b60` follows `b7d2e8f4a1c9`. It adds nullable `report_name`, `signature_png`
and `signature_digest` fields to `users` and a `report_identity_audits` table. Existing accounts,
assignments and grades are preserved. Back up the database before upgrading a school server.

Apply `alembic upgrade head` before starting the new application. The school Compose migration
service handles this; the demo API startup migrates both its golden and demo branches when
`DATABASE_URL_GOLDEN_DIRECT` is configured. Restart the worker with the same release.

The generic templates remain the default. A private school opts into report templates and
principal assets through `SCHOOL_BRANDING_DIR/reports/config.json`. See
[branding configuration](../branding/README.md). Teacher names and signatures are edited in
Admin → Teachers → Report name & signature. Assign teachers to classes before generating reports.

The grade-save endpoint now accepts up to 2,000 cells, keeping normal class-wide rating changes
in one audited save batch. Bulk controls change only rating drafts until Save is selected;
scores, comments, ownership checks, conflicts and undo retain their existing behavior.

## Demo setup

Use the public repository with synthetic data and `ENV=demo`. Follow
[the infrastructure guide](../infra/README.md) for Render, the shared Vercel origin, Neon golden
and demo branches, Upstash, Google OAuth and nightly reset. Keep private school branding and
identities in the school deployment. Enable scheduled operations only in the repository that
owns the configured demo.

## School deployment and rollback

After both 1.2.0 images are published, update backend and web pins together in the private
deployment repo. Before server setup, PR validation can check Compose and render private report
templates without a live school database. Follow [self-hosting](SELF-HOSTING.md) when the server
is available, and enable `SCHOOL_DEPLOY_ENABLED` only after its SSH and hostname settings exist.

To roll back application behavior, restore the previous backend/web pins and the matching
branding configuration. The 1.1.0 renderer does not support private report overlays or uploaded
teacher signatures. Leave the additive database migration in place so new identity data and
audit history are retained; do not run the destructive Alembic downgrade as an application rollback.
Existing exported PDFs remain unchanged; newly generated reports use the currently configured
templates and identities. For database recovery, use the encrypted backup and restore procedure.

## Changes after this tag

`7d26cb91a540` restores missing default comments in configured non-archived programmes. It is
present at HEAD but absent from the local `v1.2.0` tag. The subsequent, currently untracked
`82a91f4c6d30` deactivates grades 5-8 English text definitions across years under ADR-063;
primary English and German/French retain comments. Saved values and audit history remain stored,
and the deactivation downgrade intentionally does not reactivate fields.

Assessment page-density changes, shared language controls, bounded bulk reads/streaming exports,
and pending year sorting/PDF layout batches also need the next release's own validation and notes.
Do not apply these descriptions to an already-published 1.2.0 image or assume that reverting to it
will undo the data changes. Previously downloaded PDFs and stored archive bundles are unchanged.
