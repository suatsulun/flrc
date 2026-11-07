# Releases and deployment

This document defines how application releases reach a school and how to verify or reverse that change. Read this when releasing code or updating a private deployment; use [Self-hosting](self-hosting.md) for initial provisioning.

## Application versus deployment

Application code lives in this public repository. A school's private deployment repository owns its image pins, runtime branding, private report templates and deployment configuration—not a fork of the application. This separation is [ADR-053](../adr/053-one-public-application-repository-private-deployment.md); the isolated playground and explicit operational boundaries are [ADR-058](../adr/058-isolated-local-school-playground-and-explicit-operational.md).

The checked-in `infra/school-template/` is a starting template, not evidence that a particular release is installed. Never assume a feature in the current checkout exists in an older published image.

## Publish a release

1. Merge reviewed application changes with required CI passing. Include every migration and describe data effects and rollback limitations in release notes.
2. Update `apps/backend/pyproject.toml` and root `package.json` versions; refresh `apps/backend/uv.lock` with `uv lock` from that directory.
3. Tag the reviewed merged revision `vX.Y.Z` and push the tag.
4. Wait for `.github/workflows/release.yml` to publish **both** images and create the GitHub Release before changing deployment pins.

The workflow triggers on `v*` and checks the tag against `apps/backend/pyproject.toml`. It builds `linux/amd64` and `linux/arm64` images with full-version `X.Y.Z` and moving minor `X.Y` tags:

| Image                                | Contents                                                                    |
| ------------------------------------ | --------------------------------------------------------------------------- |
| `ghcr.io/<owner>/flrc-backend:X.Y.Z` | API, worker, maintenance CLI, Alembic migrations and generic report assets  |
| `ghcr.io/<owner>/flrc-web:X.Y.Z`     | Caddy, compiled teacher/admin SPAs, API proxy and generic branding fallback |

Pin full versions together. The release workflow does not deploy a school. Demo deployments may follow `main` independently; see [Public demo](public-demo.md).

## Deploy a school update

Run commands below in the **private deployment directory**, with the approved server environment. Do not use demo/test credentials.

1. Read release notes and compare the pending migrations with the installed revision. Preserve the old image pins and private branding revision.
2. Take a pre-deploy dump before migrations. The template deploy workflow does **not** do this automatically. An operator can run:

   ```bash
   docker compose run --rm backup flrc backup run
   docker compose run --rm backup flrc backup status
   ```

   Record the successful filename/checksum in private deployment evidence. Do not proceed on a failed backup; see [Backups and restore](backups-and-restore.md).

3. Update both image pins in private `compose.yaml` (Dependabot proposes image updates). Review/merge the deployment PR, or dispatch its deploy workflow.
4. The supplied workflow validates Compose, ships `compose.yaml` and `branding/` over SSH, pulls images, runs `docker compose up -d --remove-orphans`, and restarts `api worker backup` to reload branding caches. The one-shot `migrate` service runs `alembic upgrade head`; API/worker depend on its successful completion.
5. Inspect migration/service status. A failed workflow is not proof the previous deployment was untouched; inspect running containers before deciding recovery.

Automatic push deployment requires `SCHOOL_DEPLOY_ENABLED=true`; manual dispatch bypasses that flag. The workflow uses the `school` environment and serializes deployments without cancelling an in-progress one.

## Verify the deployed revision

- `docker compose ps` shows expected images and healthy API/worker; inspect `docker compose logs --since 15m migrate api worker` for machine errors.
- `docker compose exec api alembic current` matches `docker compose exec api alembic heads` for the deployed image.
- Public `GET /api/healthz` returns **204 with no body**. The workflow retries this check twelve times; this is liveness, not a full acceptance check.
- An anonymous `/api/me` request is 401; school `/api/docs`, `/api/openapi.json`, `/api/test/session` and `/api/local/login` are unavailable. Use the normal gateway, not a private API origin.
- An approved allowlisted Google account can sign in, switch panels and sign out. An unregistered account must not gain access.
- On approved disposable/synthetic data, exercise a grade save/read, locked-semester rejection, report preview and background report download. Never create fake records in a real school's active year just for smoke testing.
- If private assets changed, check report identity/cover rendering and denial of public report-asset URLs; see [Branding](branding.md).

## Rollback

Revert the image-pin change and restore matching private branding, then redeploy. **Do not automatically downgrade the database.** Additive schema changes can remain; destructive or data-changing migrations require their reviewed recovery plan. For example, migration `82a91f4c6d30` deactivates middle-English text columns and its downgrade does not reactivate them; an old image cannot reverse those flags.

Prefer a forward fix. If a database restore is necessary, restore into a new isolated database, validate it, then switch connection settings under [Incident response](incident-response.md). Restore private report assets separately. Already downloaded PDFs and Drive archives do not change when images are rolled back.
