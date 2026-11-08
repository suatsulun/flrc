# ADR-009: Celery with Redis broker and Postgres job state

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 4.3

## Context

PDF generation and year exports can be slow. Teachers should not wait behind long-running work. Render's free tier lacks a native worker service, and Upstash Redis command counts are limited.

## Decision

Use Celery with Upstash Redis as the broker. Run the worker as a Render web service with a `/health` endpoint. Store job state in Postgres `job_runs`, not in Celery's Redis result backend.

## Alternatives considered

- Run PDF generation synchronously in FastAPI.
- ARQ or Dramatiq.
- Celery Redis result backend.
- Paid Render worker.

## Consequences

- The project demonstrates Celery, a useful backend skill.
- Worker wake-up and quiet Celery settings are required.
- Job status is durable and auditable in Postgres.
- Operational complexity increases.
