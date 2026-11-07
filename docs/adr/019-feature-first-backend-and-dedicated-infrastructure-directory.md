# ADR-019: Feature-first backend and dedicated infrastructure directory

[ADR index](README.md)

**Status:** Accepted
**Date:** 2026-07-15
**Phase:** 1.4

## Context

The original backend path, `apps/api/app/api`, used “api” for both the deployable project and its
router layer while “app” was a generic Python package name. As the same Python project will also
contain a Celery worker, CLI, importer, and report renderer, the path obscured its actual boundary.
The repository also kept deployment definitions at the root even though it must support both
managed hosting and a school-controlled virtual machine.

## Decision

Rename the Python project to `apps/backend` and make it an installable uv package under
`apps/backend/src/flrc`. Organize business code feature-first under `flrc.modules`; keep shared
technical infrastructure under `flrc.core` and `flrc.db`, and worker process code under
`flrc.workers`.

Create a top-level `infra/` boundary for orchestration:

- development and production Compose definitions under `infra/compose/`;
- the school-hosted reverse proxy under `infra/caddy/`;
- provider definitions under provider-named directories such as `infra/render/`.

**Later layout amendment (ADR-053 to ADR-055):** the current school deployment template lives in
`infra/school-template/compose.yaml`, and the web image/Caddy configuration in `infra/web/`.
The development Compose file remains in `infra/compose/`; `infra/caddy/` is no longer a current path.

Application Dockerfiles remain beside the applications they build. Managed and school-hosted
deployments use the same images and environment-variable contracts.

## Alternatives considered

- Keep `apps/api/app/api` and add more layer-oriented folders.
- Move the backend to `services/backend`.
- Use a strict `domain/application/infrastructure/presentation` clean-architecture hierarchy.
- Put Dockerfiles and all build contexts under `infra/docker/`.
- Keep production provider files at the repository root.

## Consequences

- Imports identify the product, for example `from flrc.config import settings`.
- A feature's router, schemas, service, and queries can evolve together.
- Shared layer folders must not become dumping grounds for feature-specific code.
- Python packaging requires a build-system declaration and `src`-layout-aware Docker builds.
- Deployment commands use explicit paths such as `infra/compose/compose.dev.yaml`.
- The managed profile remains preferred, while a school-controlled VM is a supported fallback.
- Existing handbook paths, CI working directories, hooks, and deployment definitions must follow
  the new layout.
