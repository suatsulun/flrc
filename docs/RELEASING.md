# Releasing

The public repository is the only place where application code changes (ADR-053). A release is a
version tag; everything else follows from it.

## Current source versus the 1.2.0 tag

As inspected locally on 2026-09-11, manifests still read `1.2.0`, but HEAD has additional commits
after `v1.2.0`, and the working tree has further changes. The tag contains migration
`e2a91c743b60`; HEAD also contains `7d26cb91a540`; the pending migration is `82a91f4c6d30`.
Check `git status`, `git log v1.2.0..HEAD`, and `uv run alembic heads` from the backend before
preparing the next release. Existing image pins do not include newer uncommitted source.
This refresh did not verify remote image publication or a running deployment.

The next release notes must cover comment eligibility and preserved history, year ordering, PDF
batching/fallback, and all post-tag commits actually included. The newest migration's downgrade
does not reactivate retired fields; reversing application image pins alone does not restore them.
Review [the open gates](TODO.md) and keep [1.2.0 notes](UPGRADING-1.2.0.md) historical.

## Cut a release

1. Review all intended changes, including untracked migrations, and merge focused feature PRs to
   `main` with CI green. Record validation against the exact reviewed revision.
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

Connect Render and the single Vercel project (Root Directory `infra/vercel`, ADR-064) to the
public repository's `main` branch for automatic demo deployment; it does not wait for a tag. Use the [demo setup instructions](../infra/README.md),
including the synthetic database, golden branch, OAuth and reset settings. The managed school
Render blueprint uses `ENV=school`; it is not the public demo's environment configuration.

Release-specific migration and rollback notes: [1.2.0](UPGRADING-1.2.0.md).
