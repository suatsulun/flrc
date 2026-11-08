# flrc (FL-ReportCard backend)

The Python package behind FL-ReportCard: the FastAPI API, the Celery worker, the `flrc` CLI,
report rendering and the importer. Source is in `src/flrc`, migrations in `migrations/`, tests in
`tests/`. This file is the package's metadata README (`pyproject.toml` and the Dockerfile use it).

Documentation lives in the repository's [docs](../../docs/README.md):

- [Backend architecture](../../docs/architecture/backend.md) and [data model](../../docs/architecture/data-model.md)
- [Local development](../../docs/getting-started/local-development.md) and [testing](../../docs/development/testing.md)
- [Configuration reference](../../docs/reference/configuration.md) and [CLI reference](../../docs/reference/cli.md)
