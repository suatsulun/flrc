# Self-hosting on the school's server

The school-hosted profile (ADR-019, ADR-055) runs the published images on one server the school
owns: Caddy with both apps and TLS, the API, the worker, PostgreSQL 18, and Redis, on a private
Docker network. Only Caddy publishes ports. The school's private deployment repository holds the
pinned release, the branding, and the deployment workflow; `infra/school-template/` in this
repository is its starting content.

## Before the server exists

1. **Accounts belong to the school.** Hetzner project, DNS zone, Google Cloud project, GitHub
   deployment repository, and backup storage are created under school-owned accounts; the
   developer is invited as a member. This keeps the school the controller of its own records.
2. **Domain.** Choose one hostname, for example `flrc.school.k12.tr`, and keep it: it is the
   session cookie host, the OAuth callback, and the certificate name.
3. **Google OAuth client.** In the school's Google Cloud project create an OAuth client of type
   Web application with user type Internal and exactly one authorized redirect URI:
   `https://<hostname>/api/auth/callback`.
4. **Deployment repository.** Create a private repository from `infra/school-template/` (copy
   the folder's contents, including the dotfiles). Add the repository secrets and variables
   listed in its README. Merging a pull request there is the deployment approval; a paid GitHub
   plan can additionally require a reviewer on the `school` environment.
5. **Keys.** Generate two SSH key pairs: one for the deploy workflow (`DEPLOY_SSH_KEY`), one for
   the school's operator.

## Create the server

Hetzner Cloud, an EU location, Ubuntu LTS, a 4 vCPU / 8 GB plan (CX33 or the Arm CAX21; the
images are multi-architecture). Paste `infra/hetzner/cloud-init.yaml` with the two public keys
filled in. Point the DNS A/AAAA records at the server. After the first boot the machine has
Docker, a firewall admitting only SSH and HTTPS, automatic security updates with a 04:30 reboot
window, and the `flrc` user owning `/srv/flrc`.

Record the host key for the workflow:

```bash
ssh-keyscan -H <server address>
```

## First deployment

1. As the operator, create the environment file on the server from the template and fill every
   value; three secrets come from `openssl rand -base64 48`, the database password from
   `openssl rand -hex 24`:

   ```bash
   ssh ops@<server> 'sudo -u flrc install -m 600 /dev/stdin /srv/flrc/.env' < .env.filled
   ```

   Never commit the filled file anywhere.

2. Push the deployment repository's initial commit to `main`; the deploy workflow runs. It
   ships `compose.yaml` and `branding/`, pulls the pinned images, runs the migrations,
   starts the services, and checks `https://<hostname>/api/healthz`. Caddy obtains the certificate
   on first request; allow a minute.
3. Create the only bootstrap administrator, then use the admin table for everyone else:

   ```bash
   ssh ops@<server> 'cd /srv/flrc && docker compose exec api flrc bootstrap-admin --email admin@school.k12.tr --name "School Administrator"'
   ```

4. Sign in with that Workspace account, open `/admin`, and run the launch checks in
   `docs/RUNBOOK.md`.

## Upgrading

A new application release is a new image tag. Dependabot opens a pull request in the deployment
repository; merging it is the whole upgrade. Migrations
run in the one-shot `migrate` service before the API starts, so a failed migration leaves the old
containers running and the workflow red.

## Rolling back

Revert the bump pull request; merging the revert deploys the previous release. The database schema is not downgraded
automatically; a release that changed the schema destructively documents its own recovery in the
release notes, and the backup restore procedure remains the last resort.

## Operating

- Logs: `docker compose logs --since 1h api worker web` on the server. Logs never contain student
  data (docs/SECURITY.md).
- Status: `docker compose ps`; the API and worker have health checks, and `web` only starts once
  the API is healthy.
- Disk: `docker system df` and the `pgdata` volume. Report PDFs are generated on demand and export
  blobs expire after 24 hours, so growth is slow.
- Secrets rotation: edit `/srv/flrc/.env`, then `docker compose up -d`. Rotating `GATEWAY_SECRET`
  or `SESSION_SECRET` signs every teacher out.
- Backups and academic-year archives: the section below.

## Backups, restore tests, and year archives

The `backup` service in the Compose file (ADR-056) runs inside the same image as the API and
needs four values in `.env`:

1. **A Shared Drive folder the school owns.** In Google Workspace, create a Shared Drive (or use
   an existing one), a folder such as `FL-ReportCard backups` inside it, and note the folder id
   from its URL. Service accounts have no storage of their own, so the folder must be in a Shared
   Drive.
2. **A service account.** In the school's Google Cloud project, enable the Drive API, create a
   service account, create a JSON key for it, and add the service account's e-mail address to the
   Shared Drive as a Content manager. Put the key's JSON on one line into
   `GDRIVE_SERVICE_ACCOUNT_JSON` and the folder id into `GDRIVE_BACKUP_FOLDER_ID`.
3. **An age key pair.** `docker compose run --rm backup flrc backup keygen` prints both halves.
   `BACKUP_AGE_RECIPIENT` encrypts; `BACKUP_AGE_IDENTITY` decrypts. Store the identity in the
   school's password manager and in a sealed envelope in the school safe: without it every backup
   is unreadable, and with it every backup is readable.
4. `docker compose up -d backup`, then prove the loop once by hand:

   ```bash
   docker compose run --rm backup flrc backup run
   docker compose run --rm backup flrc backup restore-test
   docker compose run --rm backup flrc backup status
   ```

Every night at `BACKUP_AT` the service dumps the database with `pg_dump`, encrypts the dump,
uploads it with a checksum, and keeps the newest `BACKUP_RETAIN` copies; a failed night never
deletes an older copy. On day `BACKUP_RESTORE_TEST_DAY` of each month it downloads the newest
copy, verifies the checksum, decrypts it, restores it into a scratch database on the same server,
checks the schema revision and row counts, and drops the scratch database. Every run also looks
for academic years in the `archived` state that have no bundle in `archives/<year>/` yet and
uploads one: every non-empty report set per semester as PDF, the whole-year workbook, an encrypted
full dump from that moment, and a `manifest.json` with checksums and counts. Archives are never
pruned; the school deletes them under its own records policy.

`backups/status.json` on the server records the last success, the last error, the last restore
test, and the archives written. The deployment repository's `backup-check.yml` reads it every
morning over SSH and fails when the backup is older than 26 hours, the last run failed, or the
restore test is older than 40 days or failed. Twice a year, follow `docs/RESTORE-DRILLS.md` by
hand, including fetching the identity from the safe.

## What the server never exposes

PostgreSQL and Redis have no published ports. The API is reachable only through Caddy, which
injects the gateway secret the API requires in school mode and strips any client-supplied
`Cf-Connecting-Ip`. OpenAPI documentation is disabled in school mode.
