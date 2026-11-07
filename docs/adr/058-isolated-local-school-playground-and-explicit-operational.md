# ADR-058: Isolated local school playground and explicit operational schedules

[ADR index](README.md)

**Status:** Accepted

**Date:** 2026-09-10

**Phase:** 4.2 (report verification), local development and deployment

## Context

Private branding alone did not provide a usable local school: the published images predated
report identities, the worker was not launched, and the criteria and teacher manifest still
required manual setup. Copied repositories also scheduled resets, backups and deployment before
their credentials or servers existed.

## Decision

A school may keep a separate `compose.local.yaml` and launcher in its private deployment repo.
The launcher builds the current application source, starts isolated PostgreSQL/Redis/API/worker/web
services, applies migrations and seeds an empty playground. Data and uploaded signatures persist
across restarts. A local seed must verify its exact test database and refuse to overwrite existing
work; school criteria are applied only to newly created, ungraded columns.

The private localhost entry point runs in `ENV=test` and offers an account chooser for the seeded
local domain. It uses the existing Redis session and HttpOnly cookie functions, retains role and
origin checks, and refuses other environments or database targets. It is mounted only in the local
Compose profile; the shared application image and production entry point do not contain this
chooser. Only the web port is published, bound to `127.0.0.1`. This is a sample-data playground,
not the production authentication configuration.

Operational workflows require explicit repository enablement variables. CI and security checks
remain automatic. Unconfigured scheduled operations are skipped; manual runs still fail clearly
on missing credentials. Enable keepalive only in the repository that owns the demo. A skipped
backup job does not assert that a backup exists.

## Validation

Verify first startup and migration, idempotent seeding, authenticated admin/teacher screens,
teacher identity editing and persistence, source-grade PDF page counts and principal placement,
private-asset denial, and a queued year export through the real worker. Verify the complete local
stack can stop and restart while retaining identity changes. Operational fixes pass the existing
GitHub CI and dependency audit before merging.
