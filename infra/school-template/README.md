# FL-ReportCard — school deployment

This repository deploys the published FL-ReportCard release to the school's server. It contains
no application code: the application lives in the public repository, and this repository pins a
release, carries the school's branding, and holds the deployment configuration (ADR-053).

| Path                           | What it is                                                     |
| ------------------------------ | -------------------------------------------------------------- |
| `compose.yaml`                 | The five services and the two pinned image tags                |
| `.env.example`                 | Every setting the server's `/srv/flrc/.env` must contain       |
| `branding/`                    | The school's name, logo, and favicon (served, never rebuilt)   |
| `.github/dependabot.yml`       | Opens a pull request when a new application release exists     |
| `.github/workflows/deploy.yml` | Ships `compose.yaml` and `branding/` to the server and applies |

The complete runbook (server creation, first deploy, upgrades, rollback, backups) is
`docs/SELF-HOSTING.md` in the public repository.

## Upgrade

1. Dependabot opens "Bump ghcr.io/…/flrc-backend and flrc-web to X.Y.Z". Read the release notes it links.
2. Merge it. Merging is the approval: the deploy workflow ships the files, the server pulls the
   images, applies pending migrations, restarts, and the workflow checks
   `https://<site>/api/healthz`. Every deploy is listed under the `school` environment.

## Roll back

Revert the bump pull request; merging the revert deploys the previous release. Do not downgrade the database
schema by hand; a destructive migration is a documented decision, not a rollback.

## Rebrand

Replace `branding/logo.svg`, `branding/favicon.svg`, and the strings in `branding/brand.js` and
`branding/brand.json`, then merge. No image changes.

## Secrets and settings this repository needs

- Repository secrets: `DEPLOY_SSH_KEY` (private key of the `flrc` deploy user), `DEPLOY_KNOWN_HOSTS`
  (output of `ssh-keyscan <server>`).
- Repository variables: `DEPLOY_HOST` (server address), `SITE_HOST` (public hostname).
- Environment `school` (created automatically by the first deploy). GitHub offers required
  reviewers on private-repository environments only on paid plans; on the free plan, merging the
  pull request is the approval step.
- The application secrets are only in `/srv/flrc/.env` on the server.
