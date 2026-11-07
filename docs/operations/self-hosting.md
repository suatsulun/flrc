# Self-hosting a school

This document provisions the supplied single-server school profile. Read this when creating a school-controlled installation; subsequent releases belong in [Deployment](deployment.md), and recovery belongs in [Backups and restore](backups-and-restore.md).

## Topology and ownership

The profile in `infra/school-template/compose.yaml` runs Caddy/web, API, Celery worker, backup scheduler, PostgreSQL 18 and Redis 8, plus a one-shot migration service. Only web publishes ports: 80/TCP, 443/TCP and 443/UDP. Database and Redis remain on the Compose network. See [ADR-055](../adr/055-school-hosting-is-one-compose-stack-on-a-school-owned-server.md).

Use school-owned hosting, DNS, Google Workspace/OAuth, backup storage and secret management. Assign a controller, technical operator and incident lead before collecting real data. Keep real identities and server details out of the public repository.

## Provision

1. Create a private deployment repository from **all contents**, including dotfiles, of `infra/school-template/`.
2. Provision an Ubuntu LTS server; `infra/hetzner/cloud-init.yaml` targets 4 vCPU/8 GB and accepts separate deploy/operator public keys. Review it before use: it installs Docker, creates `flrc` and `ops`, disables password/root SSH, enables fail2ban/UFW and unattended upgrades, and allows SSH plus the web ports. Docker-group membership is privileged access, not an application sandbox.
3. Point the chosen hostname's DNS at the server. Keep the one public HTTPS origin for teacher, `/admin`, API and OAuth callback.
4. Configure a Google Web OAuth client, normally with an internal Workspace audience, and exact redirect `https://<public-host>/api/auth/callback`. The verified email domain **and** Google's hosted-domain claim must match the school's Workspace domain.
5. Verify the SSH host-key fingerprint through a trusted channel before storing the known-hosts entry; `ssh-keyscan` alone does not authenticate a host.

## Server configuration

Create `/srv/flrc/.env` from `.env.example`, mode 0600, owned/readable by the deploy account. Never commit it. The template supplies the required variables; see [Configuration](../reference/configuration.md) for application defaults and [Security model](../security/security-model.md) for startup validation.

- Set `SITE_ADDRESS`, identical pathless HTTPS `FRONTEND_ORIGIN`/`ADMIN_ORIGIN`, and explicit `TRUSTED_HOSTS` including the public hostname **and `localhost`** for the container probe.
- Set Workspace domain and OAuth credentials. Leave `E2E_AUTH_SECRET` empty and `DEMO_PUBLIC_LOGIN` false.
- Generate three separate random secrets (`openssl rand -base64 48`) for session signing, gateway and operations. Generate a database password (`openssl rand -hex 24`) and repeat it correctly in both database URLs.
- Configure Shared Drive and age keys using [Backups](backups-and-restore.md). The backup volume must be writable by image UID 10001; cloud-init prepares `/srv/flrc/backups` accordingly.
- Configure public/private branding mounts before adding private report assets; see [Branding](branding.md).

The template worker explicitly uses `REPORT_RENDER_WORKERS=2` within its 1 GiB limit. Do not remove this cap casually: large report sets render per class but still assemble/store bounded output. API has a 2 GiB limit; PostgreSQL and backup each have 1 GiB, Redis/web 256 MiB each.

## First deploy and first administrator

Private repository secrets: `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`. Variables: `DEPLOY_HOST`, `SITE_HOST`; set `SCHOOL_DEPLOY_ENABLED=true` only once the server/configuration is ready. Manual workflow dispatch remains possible without that flag. The workflow leaves the server `.env` unchanged.

Dispatch deployment, inspect the migration result and health checks, then create the initial allowlist entry:

```bash
cd /srv/flrc
docker compose exec api flrc bootstrap-admin --email admin@example.edu --name "Example Administrator"
```

Use the actual approved Workspace account **only in the private operator environment**. This command creates the sole initial active admin with middle-school English teaching identity and no coordinator flag. It does not seed a school. An exact repeat for the sole active admin is idempotent; a different bootstrap is refused once an active admin exists.

Sign in normally. In Admin, create the academic year, preview/review/commit the roster, manually add teachers, assign teachers and configure report columns (“sütun”). Activate the year when ready. Roster import does not create staff accounts or assessment definitions. Do not run `flrc seed`, `flrc reset`, demo restoration or test fixtures against a school database.

Complete [deployment verification](deployment.md#verify-the-deployed-revision), prove a manual backup/restore test, and then enable broader access.

## Alternative managed profile

`infra/render/render.yaml` is a **school-mode** API/worker blueprint, not demo-ready configuration. `infra/cloudflare/worker.js` routes teacher, `/admin` and `/api` through one public origin and injects `GATEWAY_SECRET`; direct school API data requests must fail. Managed remote PostgreSQL requires TLS and remote Redis authenticated `rediss://`. Keep pooled application and direct migration/backup database URLs separate where the provider requires it.

Do not combine hosting profiles accidentally: the Compose stack already supplies Caddy/TLS/proxy/database/Redis. Vercel assembly and free Render cold starts are documented separately under [Public demo](public-demo.md).
