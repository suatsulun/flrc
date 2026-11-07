# ADR-055: School hosting is one Compose stack on a school-owned server

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-09

**Phase:** 5.4 (school deployment)

## Context

ADR-019 allowed a school-controlled VM as a fallback to the managed profile. With ADR-053, the
application ships as two images, so the school no longer needs the managed providers, and the
KVKK posture is simplest when every account and every byte belongs to the school.

## Decision

The school runs one Hetzner server (4 vCPU / 8 GB, EU) created from `infra/hetzner/cloud-init.yaml`
with Docker Compose managing five services: `web` (the `flrc-web` image: Caddy, both SPAs, the
`/api` proxy, TLS, the branding overlay), `api` and `worker` (the `flrc-backend` image), PostgreSQL
18, and Redis. A one-shot `migrate` service applies migrations before the API starts. Only `web`
publishes ports; the API is reachable solely through Caddy, which injects the school-mode gateway
secret and strips `Cf-Connecting-Ip`.

The school's private deployment repository starts from `infra/school-template/`: the pinned
Compose file, an environment template, the branding overlay, Dependabot for image bumps, and a
deploy workflow that ships the Compose file and branding over SSH, pulls, applies, and checks
health; merging the pull request is the approval, and a paid GitHub plan can add a required
reviewer on the `school` environment. Secrets exist only in `/srv/flrc/.env`
on the server. All accounts (Hetzner, DNS, Google Cloud, GitHub, backup storage) are school-owned
with the developer as a member. The runbook is [operations/self-hosting.md](../operations/self-hosting.md).

## Alternatives considered

- The managed profile (Render, Neon, Upstash, Cloudflare): more moving parts and providers to
  contract with, and Vercel's non-commercial terms exclude it for the school.
- A separate edge proxy in the private repository: this moves the security-relevant routing order
  out of the tested public image.
- Developer-owned infrastructure billed to the school: student data on a private individual's
  account, contrary to the school-as-controller posture.

## Consequences

- One monthly invoice of roughly €9, one server to patch, and a runbook a school IT person can
  follow.
- Upgrades and rollbacks are pull requests; nothing is built on the server.
- The database and Redis have no public ports; backups must leave the machine another way
  (ADR-056).
- A single server is a single failure domain; the daily off-site backup and restore drill are the
  recovery plan.
