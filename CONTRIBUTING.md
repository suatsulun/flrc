# Contributing

This is the contribution entry point; read this when preparing a change or pull request.

1. Read [AGENTS.md](AGENTS.md), the [architecture](docs/architecture/overview.md), and the relevant feature documentation before editing. Agents implement directly; no guide-first approval cycle is required.
2. Create a focused branch from `main`. Keep unrelated changes out of the branch; open a pull request against `main` with the problem, approach, user-visible effects, migration/deployment implications, and actual check results.
3. Follow [conventions](docs/development/conventions.md), use conventional commits such as `fix(auth): preserve session expiry`, and do not add AI attribution to commits or source.
4. Run the relevant [checks](docs/development/testing.md). Required contribution evidence includes lint/type checks, regression coverage, regenerated API types when applicable, and updated documentation. Do not claim checks you did not run. CI also builds production images and checks deployment templates, dependencies, secrets, and API contract drift.
5. Review using [the review guide](docs/development/code-review.md). Resolve correctness/security findings and failing final-head CI before requesting acceptance. UI changes need desktop and phone evidence, loading/error states, accessibility, and all four locales.

Start with [local development](docs/getting-started/local-development.md); use [recipes](docs/development/how-to.md) for routine changes. Record architectural decisions in [an ADR](docs/adr/README.md). Never include school data, credentials, private deployment details, or identifiable screenshots in a public PR.
