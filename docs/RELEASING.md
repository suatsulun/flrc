# Releasing

The public repository is the only place application code changes (ADR-053). A release is a
version tag; everything else follows from it.

## Cut a release

1. Merge the feature PRs to `main` with CI green.
2. In a release PR, set the version in `apps/backend/pyproject.toml` and the root `package.json`,
   and run `cd apps/backend && uv lock` so the lockfile records it. Include migration and
   rollback notes, then merge the release PR after CI passes.
3. Tag that merged commit and push:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

4. `.github/workflows/release.yml` refuses a tag that does not match the version, builds
   `ghcr.io/<owner>/flrc-backend` and `ghcr.io/<owner>/flrc-web` for `linux/amd64` and
   `linux/arm64`, tags them `X.Y.Z` and `X.Y`, and creates a GitHub Release with generated notes.

## What the images contain

- `flrc-backend`: the FastAPI API, the Celery worker (`bin/start-worker-web.sh`), the `flrc`
  CLI, and the Alembic migrations. Generic branding is synced in; a deployment mounts its own
  folder and sets `SCHOOL_BRANDING_DIR`.
- `flrc-web`: Caddy with both compiled SPAs, the same-origin `/api` proxy, automatic TLS, and the
  `/branding/` overlay with generic fallbacks (`infra/web/`).

## How a deployment consumes a release

The private school repository pins both image tags in its Compose file and holds the environment.
When private report assets exist, mount `branding/public/` into the web container and the complete
`branding/` folder into API/worker/backup containers. Dependabot's `docker-compose` ecosystem opens a pull request
there when a new tag appears; merging it is the approval, and the deploy workflow applies it.
Rolling back is reverting that pull request. Update deployment pins only after both published
images are available. Validate the private configuration in PR CI; enable server deployment
automation only after the server, hostname and SSH settings are configured.

## The demo

Connect Render and the Vercel projects to the public repository's `main` branch for automatic
demo deployment; it does not wait for a tag. Use the [demo setup instructions](../infra/README.md),
including the synthetic database, golden branch, OAuth and reset settings. The managed school
Render blueprint uses `ENV=school`; it is not the public demo's environment configuration.

Release-specific migration and rollback notes: [1.2.0](UPGRADING-1.2.0.md).
