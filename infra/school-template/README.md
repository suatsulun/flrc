# School deployment template

This folder is the starting content for a school's private deployment repository, not an application fork. Read this when copying the template or maintaining its settings; the full procedure is [Self-hosting](../../docs/operations/self-hosting.md) in the public application repository.

Copy **all contents, including dotfiles**, into the private repository. Links below resolve from this template in the application checkout; after copying, consult the same paths in the public application's docs.

## Files and responsibilities

| Path                                 | Purpose                                                                            |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| `compose.yaml`                       | Production services, resource limits and backend/web release pins                  |
| `.env.example`                       | Template for the server-only `/srv/flrc/.env`                                      |
| `branding/`                          | Runtime identity; private report assets stay backend-only                          |
| `.github/dependabot.yml`             | Proposed image-pin upgrades                                                        |
| `.github/workflows/deploy.yml`       | Validate, ship configuration/branding, pull and apply containers, check API health |
| `.github/workflows/backup-check.yml` | Read the server's backup status and judge freshness                                |

The application remains generic and public; school identities, assets and operator details remain private. See [ADR-053](../../docs/adr/053-one-public-application-repository-private-deployment.md).

## Configure before enabling automation

| Location             | Required values                                                |
| -------------------- | -------------------------------------------------------------- |
| Repository secrets   | `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`                         |
| Repository variables | `DEPLOY_HOST`, `SITE_HOST`                                     |
| Automation flag      | `SCHOOL_DEPLOY_ENABLED=true` once server and secrets are ready |
| Server only          | `/srv/flrc/.env`, filled from `.env.example`, never committed  |

Authenticate the server host-key fingerprint independently before saving known hosts. Push deployment and scheduled backup freshness checks require the flag; manual dispatch bypasses it and still requires valid configuration. The deploy workflow records runs in the `school` environment and does not overwrite the server `.env`.

## Updates and rollback

Pin backend and web to the same **published full release version**. Features in the application checkout do not automatically exist in the template's image pins. Read [Deployment](../../docs/operations/deployment.md) for release publication, pre-deploy backup, migration verification and rollback.

**The supplied deploy workflow does not take a pre-deploy dump.** Arrange and verify it before applying migrations. Compose runs a one-shot migration service; do not treat a failed deployment as proof that the old runtime was unaffected.

Reverting image pins does not reverse data migrations. Preserve the matching private branding revision and prefer forward database fixes over unreviewed Alembic downgrades.

## Branding and backups

Use [Branding](../../docs/operations/branding.md) for exact runtime files and report overlay configuration. Before adding confidential assets, mount only `branding/public/` into web and keep the complete folder in API/worker/backup. Deployments restart report processes even for branding-only changes.

Use [Backups and restore](../../docs/operations/backups-and-restore.md) for Shared Drive/age setup, scheduler behavior, manual commands, freshness thresholds and isolated drills. A configured service or green freshness job is not evidence that a human can recover a backup.

Routine procedures: [Runbook](../../docs/operations/runbook.md). Suspected disclosure/corruption: [Incident response](../../docs/operations/incident-response.md).
