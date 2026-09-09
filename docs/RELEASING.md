# Releasing

The public repository is the only place application code changes (ADR-053). A release is a
version tag; everything else follows from it.

## Cut a release

1. Merge to `main` with CI green.
2. Set the version once, in `apps/backend/pyproject.toml` and the root `package.json`, and run
   `cd apps/backend && uv lock` so the lockfile records it. Commit as `chore(release): vX.Y.Z`.
3. Tag and push:

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

The private school repository pins both image tags in its Compose file, mounts three branding
files, and holds the environment. Dependabot's `docker-compose` ecosystem opens a pull request
there when a new tag appears; merging it is the approval, and the deploy workflow applies it.
Rolling back is reverting that pull request.

## The demo

The public demo deploys automatically from `main` (Render and Vercel are connected to the public
repository); it does not wait for a tag.
