# Upgrading to 1.2.0

This release adds teacher report names and PNG signatures, private school report templates and
principal identities, notes-only filtering, and student/class bulk 1–2–3 drafts. It also includes
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
