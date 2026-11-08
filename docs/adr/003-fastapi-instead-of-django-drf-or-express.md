# ADR-003: FastAPI instead of Django/DRF or Express

[ADR index](README.md)

**Status:** Accepted  
**Phase:** 1.3

## Context

The backend needs typed request/response schemas, dependency-based auth guards, OpenAPI generation, async database access, and good testability. The project is also intended as a portfolio project.

## Decision

Use FastAPI with Pydantic v2, SQLAlchemy 2.0, Alembic, and uv.

## Alternatives considered

- Django + Django REST Framework.
- Flask.
- Node/Express or NestJS.
- SQLModel.

## Consequences

- OpenAPI generation becomes the source for the TypeScript client.
- Dependency injection becomes the main security composition mechanism.
- The project demonstrates a real Python backend stack.
- More admin functionality must be built manually than in Django.
