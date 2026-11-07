# FL-ReportCard documentation

Everything about how FL-ReportCard works, how to change it and how to run it. Coding agents read
[AGENTS.md](../AGENTS.md) first; it says which of these documents to read for each kind of change.
Each document opens with what it covers and when to read it. The code in this checkout is the final
authority: when a document and the code disagree, fix the document in the same change.

## Getting started

| Document                                                  | Read it to                                                                                    |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [Local development](getting-started/local-development.md) | Install, run the apps, API and worker, seed data and sign in locally (with or without Google) |
| [Using the demo](getting-started/using-the-demo.md)       | Try the public demo and know what happens to your data                                        |

## Architecture

| Document                                                         | Read it to                                                                             |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [Overview](architecture/overview.md)                             | See the whole system, its users, the monorepo map and one grade save end to end        |
| [Backend](architecture/backend.md)                               | Find your way around the FastAPI modules, errors, transactions, locks and undo         |
| [Frontend](architecture/frontend.md)                             | Understand the two React apps, routing, data fetching, state and the shared UI package |
| [Data model](architecture/data-model.md)                         | Know every table, its invariants, the academic-year lifecycle and migration rules      |
| [Reports and jobs](architecture/reports-and-jobs.md)             | Change report cards, PDFs, background jobs, exports or their retention                 |
| [Authentication and sessions](architecture/auth-and-sessions.md) | Change sign-in, roles, sessions, demo visitors or test sign-in                         |

## Design

| Document                                                       | Read it to                                                                                                     |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [Design system](design/design-system.md)                       | Build UI with the existing tokens, components, layouts, loading states, phone patterns and accessibility rules |
| [Writing and translations](design/writing-and-translations.md) | Write Turkish-first UI copy and add translation keys in all four languages                                     |

## Development

| Document                                  | Read it to                                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [Conventions](development/conventions.md) | Follow the code, API, database, privacy, git and definition-of-done rules                      |
| [Testing](development/testing.md)         | Run and write backend tests, browser tests and static checks the way CI does                   |
| [Code review](development/code-review.md) | Review a change: repository invariants, failure modes and severity levels                      |
| [How-to recipes](development/how-to.md)   | Add an endpoint, migration, page, translation, report change, undoable action, E2E spec or ADR |
| [Contributing](../CONTRIBUTING.md)        | Open a pull request                                                                            |

## Operations

| Document                                                 | Read it to                                                          |
| -------------------------------------------------------- | ------------------------------------------------------------------- |
| [Deployment](operations/deployment.md)                   | Release images, deploy a school installation, verify and roll back  |
| [Self-hosting](operations/self-hosting.md)               | Set up a school server from the published images                    |
| [Branding](operations/branding.md)                       | Give an installation its own name, logo, colours and report assets  |
| [Backups and restore](operations/backups-and-restore.md) | Run, check and restore backups, and drill the restore               |
| [Runbook](operations/runbook.md)                         | Do routine operations: health, logs, jobs, purges, year changes     |
| [Incident response](operations/incident-response.md)     | Contain and recover from an incident                                |
| [Public demo](operations/public-demo.md)                 | Operate the hosted demo: baseline, nightly reset, keepalive, limits |

## Security

| Document                                         | Read it to                                                                                 |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| [Security model](security/security-model.md)     | Understand threats, access control, sessions, origin checks, rate limits and open findings |
| [Privacy data map](security/privacy-data-map.md) | Know what personal data is stored, why, for how long and how it is deleted                 |

## Reference

| Document                                    | Read it to                                               |
| ------------------------------------------- | -------------------------------------------------------- |
| [Configuration](reference/configuration.md) | Look up every backend and frontend setting               |
| [CLI](reference/cli.md)                     | Look up every `flrc` command and root package script     |
| [Glossary](reference/glossary.md)           | Translate Turkish school terms to English and code names |
| [Decision records](adr/README.md)           | Find why something is the way it is (ADR-001 to ADR-082) |

Elsewhere: [branding/README.md](../branding/README.md) (the rebranding tool) and
[infra/school-template/README.md](../infra/school-template/README.md) (the school server template).
