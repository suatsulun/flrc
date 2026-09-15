# FL-ReportCard: The Builder's Handbook

_The complete assembly manual. Like an IKEA guide: every step tells you **what** we're building, **why**, then walks from a vague hint down to the exact screws. You choose how deep to read, but the exact instructions are always there at the bottom of every step, so you can never be stranded._

_This handbook supersedes BUILD-STEPS.md. The old ARCHITECTURE.md stays alive as the deep-theory companion (domain model reasoning, decision records, KVKK) and is cited as "ARCH §x.x"._

## Current checkout (2026-09-11)

This is the learning/build manual, not a claim that every example still matches the finished
application. Steps retain their original assembly snippets; current amendments below describe
accepted changes. When maintaining this checkout, inspect the corresponding source and tests
before replacing a file with a historical snippet. Report any remaining mismatch using the
source-of-truth protocol in [AGENTS.md](../AGENTS.md).

Use [TODO.md](TODO.md) for open work and [AI-HANDOFF.md](AI-HANDOFF.md) for a review-first prompt.
The local `v1.2.0` tag predates several commits, while manifests still read `1.2.0`. The pending
ADR-063 migration and year-order/PDF-batching changes are not verified deployment state.

| Handbook scope            | Current implementation amendment                                                                                                                               |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0-1: tooling and skeleton | Node 26.8.1, pnpm 11.25.0, Python 3.13 are pinned locally. Existing apps are implemented; do not scaffold over them.                                           |
| 1.11: demo hosting        | One Vercel project (`infra/vercel`) serves both SPAs and the `/api` rewrite (ADR-064); Render hosts the API and worker.                                        |
| 1.5, 2.1, 4.1: schema     | Fourteen original tables plus `demo_visitors` and `report_identity_audits`; exact names are in ARCH §3.1.                                                      |
| 2.1: assessment programme | Grade 4 German/French permit ratings and comments without numeric averages. Pending ADR-063 removes grades 5-8 English comments.                               |
| 2.4-2.6: grid/save        | Four/five sentence columns at laptop widths, angled middle-English overview, pupil/class rating drafts, maximum 2,000 cells per save.                          |
| 2.11, 4.6: tests          | Frontend packages have no standalone `test` script. Use root Playwright, configured test servers, and the existing synthetic backend suite.                    |
| 3.5, 3.9-3.10: years      | Rollover preserves student identity and assigns fresh year-scoped numbers. Pending lists sort by label, not insertion id.                                      |
| 4.2-4.4: reports          | Four PDF sets return directly from `/api/reports/pdf` (ADR-028); year XLSX exports remain durable Celery jobs. Private report overlays/signatures use ADR-057. |
| 4.5, 4.9-4.10: operations | School deployment consumes paired images, runtime branding, nightly encrypted backups, and monthly restore tests from `infra/school-template/`.                |

Backend pytest fixtures wipe the fixed local `flrc_test` database; migration tests also downgrade
it. Runs must be serialized on disposable test data. Root Playwright does not launch servers and
its seeded suite must not share a mutable database with another run. Historical green exit lists
below are learning checkpoints, not fresh release evidence.

## Handbook status

| Part       | Contents                                                                                                                                                                                     | Status       |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| I          | The whole architecture: every app, tool, and service (what it is, its job here, why it beat the alternatives)                                                                                | ✅ this file |
| II         | How to read a step (the legend)                                                                                                                                                              | ✅ this file |
| III        | Phase 0: Day zero, full depth                                                                                                                                                                | ✅ this file |
| IV         | Phase 1: Walking skeleton, steps 1.1-1.6, full depth                                                                                                                                         | ✅ this file |
| IV (cont.) | Phase 1 steps 1.7-1.11 (OAuth, guards, client generation, frontend shells, deploy + CI)                                                                                                      | ✅ this file |
| V          | Phase 2: The grid, complete (2.1-2.11: schema, columns API + editor, assignments, grid endpoint + UI, dirty store, batch save + conflicts, grants, undo, audit viewer, phone stepper, tests) | ✅ this file |
| VI         | Phase 3: Admin lifecycle + importer, full depth                                                                                                                                              | ✅ this file |
| VII        | Phase 4: PDFs, Celery, backups, E2E, launch, full depth                                                                                                                                      | ✅ this file |

---

# Part I: The Whole Architecture

Read this once before touching a keyboard, then come back whenever a step names something and you've forgotten why it exists. Every entry answers four questions: **What is it? What is its job in this project? Why did it win (and over what)? Where will you meet it?**

## I.1 The shape of the system

You are building **six deployable things** and **three shared packages**, all living in one repository:

```
                         THE USER'S BROWSER
                                │
                    flrc.<school-domain>
                    gateway / path router
                     │       │        │
                     │       │        └── login redirect to Google and back
                     ▼       ▼
             apps/teacher  apps/admin
             at /          at /admin/*
                     │       │
                     └── every /api/* request is PROXIED ──┐
                         (same-origin rewrite)              │
                                                          ▼
                                              apps/backend (FastAPI)
                                              on Render (free web service #1)
                                                │        │
                        reads/writes ───────────┘        └───── enqueues jobs +
                                ▼                               "wake up" pings
                        Neon PostgreSQL                              │
                        (one database,                               ▼
                         every year,                     apps/backend worker mode (Celery)
                         EU Frankfurt)                   on Render (free web service #2,
                                ▲                        disguised as a web app)
                                │                              │
                                └── job status rows ───────────┤
                                                               ▼
                                                    Upstash Redis (EU)
                                                    sessions + job queue

      GitHub Actions (free robots): CI on every PR · keep-alive pings on school
      hours · weekly pg_dump → the school's own Google Drive folder
```

Why six things and not one? Because each has a different life: the SPAs are independent static
builds; the tiny gateway composes them without merging their deployments; the API is a
long-running process that guards the database; the worker does slow jobs that must never block a
teacher's save; and the robots (CI, backups, pings) should not need a server. Splitting along those
lines follows the hosting boundaries without widening the browser's session boundary.

That diagram is the **managed profile**, not a dependency baked into the code. The supported
school-hosted profile runs Caddy, both static frontend builds, FastAPI, Celery, PostgreSQL, and
Redis on a school-controlled VM through `infra/school-template/compose.yaml`. Caddy preserves
the same-origin `/api/*` contract. The two profiles use the same application image and settings;
Neon, Upstash, Render, and Caddy never appear in business-code imports.

**The one non-obvious trick that makes everything else simple:** the browser never talks to Render directly. The SPA's host (Vercel/Cloudflare) _proxies_ `/api/*` to Render, so as far as the browser knows, frontend and backend are **the same origin**. That single decision means cookies "just work" (`SameSite=Lax`, first-party), CORS configuration barely exists, and CSRF defense is one small middleware. Every alternative (cross-site cookies, tokens in localStorage) is a hole-riddled boat you'd bail all summer. Full reasoning: ARCH decision #4.

## I.2 The two languages

**TypeScript** (everything in `apps/teacher`, `apps/admin`, `packages/*`)

- _What:_ JavaScript with a static type system compiled away at build time.
- _Job here:_ the entire browser side. Types are the guardrails that let you refactor a grid with 15 column types without fear.
- _Why it won:_ over plain JavaScript because a grade grid is exactly the kind of app where "is this cell's value a number, a 1-3 scale, or text?" must be answered by the compiler, not by a runtime crash in front of a teacher. There was no real competitor; TS is the industry default and the job-listing keyword.
- _You'll meet it:_ everywhere from §1.1.

**Python 3.13** (everything in `apps/backend`)

- _What:_ the backend language, run through `uv`.
- _Job here:_ the API, the Celery worker, the Excel importer, the PDF renderer, the seed CLI.
- _Why it won:_ over Node/Express or NestJS because (a) you're deliberately building a two-language résumé (full-stack means both sides of the fence); (b) the Python data-tooling ecosystem (openpyxl, WeasyPrint) is simply better at this project's ugliest jobs; (c) FastAPI + SQLAlchemy 2.0 + Alembic is one of the most-requested backend stacks in job listings right now. Over Django because Django's batteries (admin, templates, its ORM) mostly duplicate things you're building yourself on purpose; you'd fight the framework to learn less.
- _You'll meet it:_ §1.3 onward.

## I.3 The frontend stack, piece by piece

**React 19**

- _What:_ the UI library: components, hooks, one-way data flow.
- _Job here:_ renders both SPAs; the grid alone justifies it.
- _Why it won:_ over Vue/Svelte/Solid not on technical merit (all four are fine) but on two project goals: you already think in React, and React remains the overwhelming majority of frontend job listings in your market. This project's innovation budget is spent on the backend and the grid logic; the view library is deliberately the boring choice. Version 19 specifically because it's current and you've already absorbed its changes (you hit the `FormEvent` deprecation months ago).
- _You'll meet it:_ §1.1.3.

**Vite**

- _What:_ the dev server + build tool. Serves your source over native ES modules in development (instant startup, instant hot-reload) and creates production bundles using the version pinned in the app manifest.
- _Job here:_ runs both SPAs locally, builds them for deploy, and hosts two critical config points: the dev proxy (`/api` → localhost:8000) and the Tailwind plugin.
- _Why it won:_ over Next.js because Next's whole value is server-side rendering and server components, machinery for SEO and first-paint on public pages. FL-ReportCard is an auth-walled internal tool; there is nothing to SEO and nobody to impress before login. SSR here would mean running a Node server for pages that could have been free static files; you'd pay complexity _and_ lose the free-hosting math. Over CRA/webpack because those are the previous era.
- _You'll meet it:_ §1.1.3, §1.10.1.

**Tailwind CSS v4**

- _What:_ utility-class CSS: you style in the markup with composable classes; v4 moved configuration into CSS itself (`@import "tailwindcss"`, `@theme` tokens) with a dedicated Vite plugin.
- _Job here:_ every pixel of both apps; also the design language shadcn/ui components are built from.
- _Why it won:_ over CSS Modules / styled-components because in a two-app monorepo, utilities + a shared token theme keep the apps visually identical without a "design system project" you don't have time for. v4 specifically (not v3) because it's current, faster, and its CSS-first config is where the ecosystem moved, and because _you already use it_; consistency with your own muscle memory is worth something. **Watch-out baked into AGENTS.md:** v3 tutorials with `tailwind.config.js` are everywhere online and wrong for you.
- _You'll meet it:_ §1.10.2.

**shadcn/ui**

- _What:_ not a component _library_ but a component _generator_: it copies accessible, Tailwind-styled source components (built on Radix primitives) into your own repo, where you own and edit them.
- _Job here:_ dialogs (conflict! grant! confirm!), popovers (text cells), dropdowns, the data tables of the admin panel, buttons, toasts.
- _Why it won:_ over MUI/Chakra/Ant because those are opinionated black boxes; you'd theme against them forever and the grid's custom cells would fight their styling engine. shadcn gives you production-quality _source_ you can crack open, which doubles as a component-patterns tutorial. It's also, frankly, what 2026 job listings picture when they say "modern React UI."
- _You'll meet it:_ §1.10.2, then every dialog in Phase 2.

**TanStack Router**

- _What:_ a fully type-safe router: routes are files, params and search-params are typed end to end, and loaders/`beforeLoad` hooks integrate with data fetching.
- _Job here:_ all navigation; the auth guard (`beforeLoad` checks `/api/me`, redirects to login); typed search params carry the year-switcher and class/subject selection; its `useBlocker` powers the "you have unsaved grades" leave-guard.
- _Why it won:_ over React Router v7 (which you already know) precisely _because_ you already know it: zero new learning is a cost, not a saving, in a learning project. TanStack Router's typed params eliminate a whole class of "undefined is not a string" bugs in a URL-heavy app (year, class, subject, student index all live in the URL). It also completes a coherent story (Query, Table, Router from one ecosystem) that demos well. **Escape hatch, pre-authorized:** if its type ceremony is still fighting you at the end of day two, switch to React Router v7 without shame and write the ADR; the grid doesn't care.
- _You'll meet it:_ §1.10.3.

**TanStack Query v5**

- _What:_ the server-state manager: caching, deduplication, background refetching, and mutation lifecycles for anything fetched from an API.
- _Job here:_ owns _every byte the server has confirmed_: the grid data, `/api/me`, column lists, job statuses (its `refetchInterval` is the whole job-polling UI). After a save, `setQueryData` merges the new cell versions into the cache with no refetch flash.
- _Why it won:_ over "fetch in useEffect + useState" because that road leads to hand-rolled caching bugs that Query solved a decade ago (stale closures, race conditions, duplicate requests). Over Redux-with-thunks because server cache is not application state; modeling it as state is the classic 2018 mistake. Over SWR because Query's mutation API and devtools are stronger, and it pairs with the generated client (see hey-api below), which emits Query hooks directly.
- _You'll meet it:_ §1.10.3, then §2.3 through §2.6 hard.

**TanStack Table** (the current teacher manifest declares 9.x)

- _What:_ a _headless_ table engine: it computes row models, header groups, and cell contexts; you render every `<td>` yourself.
- _Job here:_ the grade grid: grouped headers (the "Listening / Reading / Speaking" categories), a stable student identity column, and, crucially, _your_ cell components (score input, three-face toggle, text popover) mounted inside its cell contexts. Also the admin panel's data tables and the bulk-move row selection.
- _Why it won:_ your call in the original questionnaire, and the right one. Over AG Grid / Handsontable because those ship the cells, the editing, the everything; you'd configure a product instead of learning to build one, and their licenses lurk. Over fully hand-rolling because header-group math and row modeling are solved problems with zero learning payoff; the learning is in the _cells_ and the save pipeline, which stay 100% yours either way.
- _You'll meet it:_ §2.4.

**Zustand**

- _What:_ a tiny global-state library: a store is a hook, state updates are plain function calls, no providers or reducers required.
- _Job here:_ exactly one store with one job: the **dirty map**, every cell the teacher has edited but not saved, keyed `studentId:columnId`, holding the typed value and the version the client last saw. Save All drains it; the leave-guard watches its count; the phone stepper and the desktop grid share it.
- _Why it won:_ over Redux Toolkit because one map does not justify actions/slices/devtools ceremony. Over React Context because the grid re-renders on every keystroke if naive context holds the map; Zustand's selector subscriptions keep typing 60fps. Over "just component state" because the dirty map must outlive view switches (grid ↔ stepper) and be readable by the header's Save button. The deeper reason it exists at all: **Query owns what the server said; Zustand owns what the human typed and hasn't sent.** Keeping those separate is the single most quotable design sentence in this app. (ARCH decision #14.)
- _You'll meet it:_ §2.5.

**react-hook-form + Zod v4**

- _What:_ RHF manages form state via uncontrolled inputs (fast, minimal re-renders); Zod declares validation schemas in TypeScript that double as parsed types.
- _Job here:_ every admin form: column editor, teacher allowlist, student edit, class dialogs. Zod schemas are written to _mirror the generated API types_, so a form literally cannot drift from what the backend accepts.
- _Why it won:_ RHF over Formik because Formik is effectively unmaintained legacy; over hand-rolled `useState` forms because the admin panel has a dozen forms and you'd re-implement dirty/touched/error logic a dozen times. Zod over Yup because Zod is TypeScript-first (`z.infer` gives you the type for free) and is the shared language of the modern stack; v4 because current.
- _You'll meet it:_ §2.1.3, then every admin dialog.

**i18next + react-i18next**

- _What:_ the translation runtime: JSON resource bundles per language, a `t("key")` function, React bindings, a browser language detector.
- _Job here:_ four locales (TR/EN/DE/FR) across both apps from day one; the API returns machine _codes_ and the frontend translates them; DB-stored column labels arrive already localized so only UI chrome lives in the bundles.
- _Why it won:_ over react-intl/Lingui mostly on ecosystem weight and simplicity: i18next is the default answer, its detector and namespace model fit a two-app monorepo, and there's an ESLint plugin (`no-literal-string`) that mechanically enforces the house rule. The _real_ decision isn't the library; it's doing i18n **from the first component**, because retrofitting translations onto a finished app is the most tedious refactor in frontend work. (ARCH §4/1.10.)
- _You'll meet it:_ §1.10.4, completion in §4.4.

## I.4 The backend stack, piece by piece

**FastAPI**

- _What:_ the Python web framework: async request handling, dependency injection, and automatic OpenAPI schema generation straight from your type hints.
- _Job here:_ every endpoint; its **dependency system** is secretly the app's security architecture (`current_user`, `require_admin`, `writable_semester` are all dependencies); its auto-generated `openapi.json` is the contract the TypeScript client is generated from.
- _Why it won:_ over Flask because Flask gives you routing and a shrug; you'd bolt on validation, docs, and async by hand. Over Django/DRF because you're building the admin, the ORM patterns, and the auth _on purpose, to learn them_; Django would do them for you in ways you'd then have to un-learn. Over Litestar (a genuinely good newer rival) on ecosystem size and job-listing frequency.
- _You'll meet it:_ §1.3.

**Pydantic v2 + pydantic-settings**

- _What:_ Pydantic turns type-annotated classes into runtime validators/parsers (it's what FastAPI uses for request/response models); pydantic-settings reads the same kind of class from environment variables and `.env` files.
- _Job here:_ every request body and response model; every Excel row (the importer's `RowModel` _is_ a Pydantic class); and the single `Settings` object that is the only place environment configuration exists.
- _Why it won:_ it's not really a choice (it's FastAPI's native tongue), but it earns its place independently in the importer, where "parse, don't validate" turns hostile spreadsheet rows into typed objects or precise cell-addressed errors.
- _You'll meet it:_ §1.3.2, importer in Phase 3.

**SQLAlchemy 2.0**

- _What:_ the database toolkit and ORM. The 2.0 style means fully typed models (`Mapped[int]`, `mapped_column(...)`) and one query language (`select()`) for both raw and ORM use.
- _Job here:_ the original fourteen tables (now sixteen after ADR-051 and ADR-057); **two engines on purpose**: an async engine (asyncpg driver) inside FastAPI, a plain sync engine (psycopg driver) inside the Celery worker and the seed CLI, because Celery's execution model is synchronous and pretending otherwise buys pain.
- _Why it won:_ over Django ORM (wrong framework), over SQLModel (a thin wrapper that leaks at exactly the advanced spots this app hits: versioned updates, `ON CONFLICT`, composite constraints), over raw SQL everywhere (maximum learning, one-third the shipping speed; you'll still write the two most interesting statements, the compare-and-set UPDATE and the conflict-tolerant INSERT, essentially by hand through SQLAlchemy Core). It is also, with no serious rival, _the_ Python database skill employers ask for.
- _You'll meet it:_ §1.5.

**Alembic**

- _What:_ SQLAlchemy's migration tool: it diffs your models against the live schema and generates versioned upgrade/downgrade scripts.
- _Job here:_ the only way schema changes ever happen. The discipline (autogenerate → _read the diff_ → apply; never edit an applied migration) is half the lesson.
- _Why it won:_ no real alternative in this stack; the choice inside it was using its **async template** (`alembic init -t async`) so it drives the asyncpg engine without hand surgery, and the rule that migrations use Neon's **direct** endpoint while the app uses the **pooled** one; DDL through a transaction-mode pooler misbehaves in ways that eat afternoons.
- _You'll meet it:_ §1.5.5.

**Authlib**

- _What:_ the OAuth/OIDC client library, with Starlette/FastAPI integration.
- _Job here:_ the entire Google sign-in dance (redirect out with `state`, exchange the returned code for tokens, cryptographically validate the ID token), after which _your_ code takes over for the two gates that matter: the `hd` domain claim and the pre-registered allowlist.
- _Why it won:_ over fastapi-users (would finish auth in an hour and teach you nothing; this is 30% of the backend's educational value), over hand-rolling the protocol with httpx (real learning, but token validation is exactly where DIY security goes quietly wrong), over Auth0/Firebase/Clerk (a third-party processor of children's-school data, which detonates the KVKK story, and the school already rejected third-party auth).
- _You'll meet it:_ §1.7.

**redis-py + itsdangerous** (sessions)

- _What:_ redis-py is the Redis client; itsdangerous signs small values so they can't be forged.
- _Job here:_ server-side sessions. A random session id lives in Redis with an eight-hour absolute
  TTL; the browser holds only that id, _signed_, in a host-only `HttpOnly` cookie. Log out a
  departed teacher = delete a Redis key. That instant revocability is the entire argument for
  sessions over JWTs (ARCH decisions #5 and #38).
- _You'll meet it:_ §1.7.2 through §1.7.3.

**Celery 5**

- _What:_ the task-queue framework: the API drops job messages into Redis; a separate worker process picks them up and runs them.
- _Job here:_ the slow stuff: rendering a class's 30 PDFs, zipping them, the year-Excel export. A teacher's save must never wait behind a PDF.
- _Why it won:_ your explicit call (Celery is the CV keyword), and the constraints it drags in became the syllabus: Render's free tier has no worker dyno type (so the worker _masquerades as a web service_ with a `/health` stub), workers fall asleep (so the API _pings them awake_ on enqueue and on every status poll), and Upstash counts commands (so Celery runs with gossip/mingle/heartbeat off and **no Redis result backend**; job state lives in a Postgres `job_runs` row instead). ARQ or Dramatiq would have been gentler; the ADR saying _why you know that_ is worth more than the gentleness. (ARCH decision #9, §7/4.3.)
- _You'll meet it:_ §4.3.

**openpyxl**

- _What:_ reads and writes `.xlsx` files cell by cell.
- _Job here:_ both directions: parsing the school's hostile roster workbook (read-only mode, header hunting, footer heuristics, and the deliberate _discarding_ of the gender column) and writing the year-export backup workbook.
- _Why it won:_ over pandas because pandas is a dataframe engine wearing an Excel reader as a hat; its dtype coercion turns school numbers into floats and its 60 MB of dependency buys nothing here. You want cells with addresses, because your error messages must say "sheet 5/B, cell C14".
- _You'll meet it:_ Phase 3.

**WeasyPrint + Jinja2**

- _What:_ Jinja2 renders HTML from templates + data; WeasyPrint turns HTML/CSS into print-grade PDF, honoring `@page` sizes and page breaks.
- _Job here:_ all three report-card types (A5 landscape progress reports and the A4 bilingual karnes) from the same CSS skills you already own.
- _Why it won:_ over ReportLab (hand-placing bilingual nested tables by x/y coordinate: no), over headless Chromium printing (a 200 MB browser inside a 512 MB dyno), over LaTeX (beautiful, wrong decade for a one-person team), over **Typst** (the genuinely exciting modern option, pip-installable, no system deps), which lost only because HTML/CSS reuses skills you're selling; it's earmarked as a one-evening Phase-4 experiment and blog post. WeasyPrint's cost: system libraries (pango, cairo), which is _why_ the API ships as a Docker image. (ARCH decision #10.)
- _You'll meet it:_ §4.2.

**Typer, Faker, structlog, Sentry, pytest & friends**

- _Typer:_ CLI framework (decorator-per-command) for the `flrc` tool: seed, reset, later export. Chosen over argparse for ergonomics and over Click for its type-hint-native design.
- _Faker (tr_TR):_ generates the fictional school. Its deterministic seeding is what makes screenshots reproducible and the **synthetic-data-only** rule (no real student ever enters repo/demo/logs; see ARCH §8.5) actually livable.
- _structlog:_ JSON event logs (`grade_batch_saved`, `import_committed`) with a request-id bound to every line (your only forensics on a no-APM budget). Chosen over stdlib logging config because structured events are grep-able facts, not prose.
- _Sentry:_ crash reporting for API and both SPAs, with `send_default_pii=False` and a scrubber so student data never rides along in a stack trace.
- _pytest + httpx + time-machine:_ the backend test stack: the app runs in-process via `ASGITransport` (no server, no ports), dependencies get overridden to fake any user, and time-machine freezes clocks so "grant expires after one hour" is a test, not a hope. Playwright joins in Phase 4 for the two-browsers-collide E2E crown jewel.

## I.5 The tooling belt

**pnpm**: the JS package manager. Strict `node_modules` (no phantom dependencies), a content-addressed store (fast, disk-cheap), and first-class **workspaces**, the mechanism that lets `apps/teacher` depend on `@flrc/ui` as source. Over npm/yarn: correctness + speed + it's what modern monorepos assume.

**Turborepo**: the task runner over the workspace. You declare that `build` depends on your dependencies' `build` (`"dependsOn": ["^build"]`), it computes the graph, runs in parallel, and caches by content hash, including the Python tasks, which join via `package.json` script shims calling `uv run`. Over Nx: Nx is more powerful and heavier-vocabularied than three apps need. Over nothing: "run lint in six packages in the right order" gets old on day two.

**uv**: Python's package/project manager (from the Ruff people). Creates the venv, resolves and locks (`uv.lock`), installs at Rust speed, runs tools (`uv run pytest`). Over pip+venv: 10-100× faster and lockfile-correct. Over Poetry: the ecosystem's mindshare visibly moved in 2024-25; uv is the current answer and the one worth having on a CV.

**Ruff + mypy**: Ruff is linter _and_ formatter (replaces flake8, isort, Black in one Rust binary; its `UP` rules quietly teach modern Python idioms as you write). mypy adds static types, started permissive and ratcheted. Over the old five-tool pile: one config, one speed.

**ESLint 10 (flat config) + Prettier**: lint and format for TS. ESLint 10 removes the legacy eslintrc system entirely and resolves flat configs from each linted file, which fits this multi-app workspace. This project standardizes development and CI on Node 26. Over Biome (fast, rising): the shadcn/React ecosystem's examples and most employers still assume ESLint; noted as the road not taken.

**Lefthook**: git hooks from one YAML, polyglot and fast: on pre-commit it runs Prettier/ESLint on staged TS _and_ Ruff on staged Python. Over Husky+lint-staged (JS-centric) and pre-commit (Python-centric): one tool that doesn't pick a side in a two-language repo.

**Docker + Compose**: Compose runs Postgres 18 and Redis locally with one command (the compose file _is_ the repo's onboarding doc); the Dockerfile is the exact artifact Render runs, killing "works on my machine", and it's the only sane way to ship WeasyPrint's system libraries. Multi-stage with uv keeps the image small.

**@hey-api/openapi-ts**: the contract machine. It reads the committed `openapi.json` snapshot FastAPI produced and emits a typed fetch client _plus TanStack Query hooks_. The frontend never hand-writes a request type; a CI job regenerates and fails on diff, so "someone changed the API and forgot the client" dies at PR time. Over tRPC (needs a TS backend), GraphQL (a second API paradigm for one consumer), orval (fine; hey-api's Query plugin is the tighter fit).

**GitHub Actions + Dependabot/CodeQL**: Actions is CI
(lint/typecheck/test/contract/security on every PR), opt-in school-hours demo keepalive, nightly
demo reset, and release publishing. School-hosted backups run in the dedicated Compose service;
its private repository checks freshness. Dependabot proposes dependency updates. CodeQL and
dependency review are enabled only when the configured GitHub entitlement supports them.

## I.6 The services (where it all runs, and what "free" costs)

Provider quotas and pricing in this original planning table are historical assumptions, not a
current availability or cost check. Verify the chosen provider account before deployment.

This table describes the managed profile taught by the deployment steps. If the school does not
fund or approve those providers, ADR-019's school-hosted profile replaces the hosting rows with a
school-controlled VM, Caddy, PostgreSQL, and Redis. It does not remove the requirements for TLS,
monitoring, security updates, off-machine backups, or a restore drill.

| Service                      | Role                                             | Why this one                                                                                                   | The catch you design around                                                                                                                                                                              |
| ---------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Neon**                     | PostgreSQL, one DB, all years, EU-Frankfurt      | Real Postgres with scale-to-zero, generous free storage for data this small, built-in pooler, branches for dev | 5-min autosuspend (→ `pool_pre_ping`); pooled vs **direct** URL split (migrations use direct); only a 6-hour restore window (→ §4.5 backups are non-optional)                                            |
| **Upstash**                  | Redis: sessions + Celery broker, EU              | Serverless Redis with TLS, free tier fits ~30 users easily                                                     | 500K commands/month; the whole "quiet Celery" configuration exists because of this number                                                                                                                |
| **Render**                   | The API and the worker, as two free web services | Docker deploys, health checks, blueprints (`infra/render/render.yaml`), honest free tier                       | 750 instance-hours/month **shared**, 15-min sleep, ~45 s cold start, **no free worker type** → worker wears a web-service costume; keep-alive only on school hours                                       |
| **Vercel**                   | The _demo_ frontends + `/api` rewrite proxy      | You know it; monorepo-native; rewrites make same-origin trivial                                                | Hobby ToS = personal/non-commercial → demo only, never school prod                                                                                                                                       |
| **Cloudflare Pages**         | The _school_ frontends + public path gateway     | No non-commercial clause, unlimited static bandwidth, and it can compose separate builds under one origin      | The gateway must order `/api/*`, `/admin/*`, then the teacher catch-all; the admin build must be base-path-safe                                                                                          |
| **Google (Workspace OAuth)** | Identity                                         | The school already issues every teacher an account: no passwords to store, ever                                | Consent screen: External+test-users for local development; published consent for the public demo; **Internal** under the school's Workspace for prod; the `hd` _claim_ (not the login hint) is the proof |
| **Google Drive**             | Backup destination                               | Backups land in a folder **the school owns**: the data never gains a new home; a KVKK pitch line, verbatim     | Needs a service account granted access to that one folder                                                                                                                                                |
| **Sentry**                   | Error tracking, all three apps                   | Free tier fits; sourcemaps make SPA crashes readable                                                           | Must be configured to scrub; student data never enters an error payload                                                                                                                                  |

## I.7 Follow one grade through the machine

The best way to hold the architecture in your head is to trace **one teacher saving one score**:

1. Kıvılcım types **91** into Progress Exam 1 for a student. The **ScoreCell** component validates the keystrokes and, on blur, writes `{value: 91, expectedVersion: 3}` into the **Zustand** dirty map. Nothing has left the browser.
2. She presses **Save All**. The teacher app drains the dirty map into one request body and calls the **generated client's** save mutation, a typed function that hey-api built from FastAPI's own schema, wrapped in a **TanStack Query** mutation.
3. The browser sends `POST /api/classes/12/grid/save` _to its own origin_. **Vercel/Cloudflare** matches the `/api/*` rewrite and proxies it to **Render**. Because it's same-origin, the `flrc_session` cookie rides along under `SameSite=Lax` with zero ceremony.
4. **FastAPI** wakes (or was kept warm by the school-hours ping). The **Origin-check middleware** approves the request. The `current_user` dependency unsigns the cookie with **itsdangerous**, looks the session id up in **Upstash Redis**, loads Kıvılcım from **Neon**. The `writable_semester` dependency confirms semester 1 is open.
5. The save service checks she owns the `main` role for class 12 (or holds a live grant), then runs the one statement the whole app pivots on: an **SQLAlchemy** UPDATE whose WHERE clause says `AND version = 3`. Rowcount 1: applied, version becomes 4, and an **audit_entry** + **save_batch** row commit in the same transaction. Rowcount 0: someone got there first, and a conflict record with the other teacher's name goes back instead.
6. The response returns `applied` with new versions. TanStack Query's `setQueryData` merges them into the cached grid (no refetch flash), and the store clears those dirty keys. The Save button ticks to ✓.
7. Months later that cell is ink: a coordinator requests one of the four report sets through
   `/api/reports/pdf`. The builder assembles the report data, **Jinja2** renders HTML, and
   **WeasyPrint** produces the PDF outside the API's async event loop. The browser opens that
   response directly. A whole-year workbook follows the separate **Celery** path: queue its job id,
   record progress/output in **Postgres `job_runs`**, and download through the authenticated API.

Every tool in Part I appears in that story or guards it. If a step ever feels arbitrary later, re-read the trace.

## I.8 The repository map

```
fl-reportcard/
├── apps/
│   ├── teacher/        React SPA: the grid, the stepper, teachers' daily life
│   ├── admin/          React SPA: columns, roster, lifecycle, import, reports, audit
│   └── backend/        Python: FastAPI app + Celery worker + CLI + templates
│       ├── src/flrc/   installable package; feature modules plus core/, db/, workers/
│       ├── migrations/ Alembic
│       ├── tests/      pytest
│       └── Dockerfile  backend and worker image
├── packages/
│   ├── ui/             shared shadcn components + the three grid cells
│   ├── api-client/     GENERATED: openapi.json snapshot + typed client + Query hooks
│   └── i18n/           the four locale bundles + init
├── e2e/                Playwright (Phase 4)
├── docs/               HANDBOOK.md (this) · ARCHITECTURE.md · DECISIONS.md
├── infra/              Compose, Caddy, and managed deployment definitions
├── .github/workflows/  ci.yml · security.yml · keepalive.yml · demo-reset.yml · release.yml
├── turbo.json          the task graph
├── pnpm-workspace.yaml the workspace definition
└── AGENTS.md           AI-assistant working rules
```

Rule of thumb for "where does this file go": if two apps need it → `packages/`; if it's generated → never hand-edit it; if it's a decision → `docs/DECISIONS.md` before you forget why.

---

# Part II: How to read a step (the legend)

Every numbered step in Parts III through VII is assembled from the same labeled pieces, always in this order:

- **What we're building**: the outcome of the step, in one or two plain sentences. The picture on the IKEA box.
- **Why**: the reasons this exists and why now; what breaks or gets expensive later without it.
- **Layer 1 · Nudge**: the vague hint. _Stop reading here first_ and try; struggling briefly is the point of the whole format.
- **Layer 2 · Guide**: the concrete approach (names of functions, files, options); the shape of the solution without the final text.
- **Layer 3 · Exact assembly**: the IKEA panel (exact commands, exact file paths, and exact contents). For configuration and boilerplate this is verbatim. For application logic it is complete too; read it only when Layers 1-2 didn't get you there, and even then, _type it, don't paste it_; your fingers are part of your memory.
- **Check**: the proof the step is done: a command and what it must print, or a click and what you must see. Never continue on a red Check.
- **If it breaks**: the most likely failures and their fixes, so being stuck has a first page to turn to.
- **Docs / Why deeper**: the one official docs page worth opening, and the ARCH § that holds the long-form reasoning.

Session ritual: end on a green Check → commit. Stuck longer than 90 minutes after Layer 3 and "If it breaks" → take the step's escape hatch if it names one, write the ADR, move on.

---

# Part III. Phase 0: Day zero (one sitting, no app code)

## Step 0.1: Install the workshop

**What we're building:** an Arch machine that can run containers, JavaScript tooling, and Python tooling: the three power tools every later step assumes.

**Why:** every "it doesn't work" in week one traces back to a missing or half-installed tool. One careful hour now buys silence later. Docker specifically needs two things people always forget: the _service_ running and your _user_ in the docker group.

**Layer 1 · Nudge:** you need git, Docker with Compose, Node 26 with pnpm 11, and uv. Arch's repos have all of them.

**Layer 2 · Guide:** pacman for git/docker/docker-compose/uv (and Node if you do not manage it with fnm). Enable + start `docker.service`, add yourself to the `docker` group (takes effect on re-login). Node 25+ no longer bundles Corepack, so install pnpm into the active Node 26 environment; `packageManager` still pins the repository's exact pnpm line.

**Layer 3 · Exact assembly:**

```bash
sudo pacman -S --needed git docker docker-compose uv nodejs npm
sudo systemctl enable --now docker.service
sudo usermod -aG docker $USER
# log out and back in (or run: newgrp docker) so the group applies
npm install --global pnpm@11.25.0
```

**Check:**

```bash
docker run --rm hello-world   # prints "Hello from Docker!"
git --version && node -v && pnpm -v && uv --version
```

**If it breaks:**

- `permission denied … docker.sock` → you skipped the re-login after `usermod`; `newgrp docker` for this shell or log out/in.
- `pnpm: command not found` after changing fnm versions → pnpm was installed under the previous Node installation; run `npm install --global pnpm@11.25.0` again while Node 26 is active.
- Node version drift → `.node-version` is the local source of truth; `node -v` must report v26 before installing or running pnpm.

**Docs:** wiki.archlinux.org/title/Docker · pnpm.io/installation

## Step 0.2: The repository skeleton

**What we're building:** the empty-but-shaped repo: folders, docs, ignore rules, first commit.

**Why:** the folder shape from §I.8 is a contract with every later step ("create `apps/backend/src/flrc/config.py`" only means something if `apps/` exists). The `.gitignore` matters _before_ the first `.env` exists, not after it leaks.

**Layer 1 · Nudge:** private GitHub repo, clone, make the top-level folders, drop the three docs in, gitignore Node+Python+env, commit.

**Layer 2 · Guide:** `mkdir -p apps packages infra docs e2e .github/workflows`; docs get this file as `HANDBOOK.md`, the reference as `ARCHITECTURE.md`, plus `DECISIONS.md`; `AGENTS.md` sits at the root. Ignore: `node_modules`, `dist`, `.venv`, `__pycache__`, `.env` and variants, `.turbo`, editor litter.

**Layer 3 · Exact assembly:** create the repo on GitHub (private, no template), then:

```bash
git clone git@github.com:<you>/fl-reportcard.git && cd fl-reportcard
mkdir -p apps packages infra docs e2e .github/workflows
# copy in: docs/HANDBOOK.md docs/ARCHITECTURE.md AGENTS.md
touch docs/DECISIONS.md
cat > .gitignore << 'EOF'
node_modules/
dist/
.turbo/
.venv/
__pycache__/
*.pyc
.env
.env.*
!.env.example
.DS_Store
EOF
git add -A && git commit -m "chore: repo skeleton" && git push
```

**Check:** `git status` clean; the repo on GitHub shows the tree from §I.8 (minus the yet-unbuilt parts); `cat .gitignore` includes `.env` **above** the `!.env.example` exception.

**If it breaks:** SSH clone refused → add your key (`ssh-keygen -t ed25519`, paste `.pub` into GitHub → Settings → SSH keys), test `ssh -T git@github.com`.

## Step 0.3: Google OAuth demo client

**What we're building:** the Google-side half of login: a project, a consent screen, and a Web-application OAuth client whose redirect URI points at your future local API.

**Why:** §1.7 needs a client ID + secret to exist _before_ you write auth code, and Google's console is fiddly enough that doing it fresh mid-coding-session wrecks momentum. A local development client can use "External + test users"; the public demo uses the published
consent configuration in `infra/README.md` (ADR-051 and ADR-052); the school gets its own _Internal_ client under their Workspace much later; two clients so redirect URIs never mix (ARCH §4/1.7).

**Layer 1 · Nudge:** console.cloud.google.com → new project → consent screen → credentials → OAuth client (Web) → one redirect URI: your local API's callback.

**Layer 2 · Guide:** the consent screen wants a user type (**External**), an app name, your email twice, and, critically, **you added as a test user**, or your own logins will be refused. The client wants exactly `http://localhost:8000/api/auth/callback` as an authorized redirect URI (scheme, port and path must match to the character; Google compares strings, not intentions).

**Layer 3 · Exact assembly:**

1. console.cloud.google.com → project picker → **New project** → name `flrc-demo` → Create, then make sure it's selected.
2. **APIs & Services → OAuth consent screen** → External → Create. App name `FL-ReportCard (demo)`, user support email = you, developer contact = you → Save through the scopes page (add nothing; `openid email profile` are default-class scopes requested at runtime) → **Test users → Add users** → your Gmail _and_ your school address → Save.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Web application** → name `flrc-local` → **Authorized redirect URIs → Add**: `http://localhost:8000/api/auth/callback` → Create.
4. Copy the **Client ID** and **Client secret** into your password manager under "FLRC demo OAuth". They go into `apps/backend/.env` in §1.3.2.

**Check:** the Credentials page lists `flrc-local`; opening it shows the exact redirect URI with no trailing slash.

**If it breaks (pre-answering §1.7's classics):** `redirect_uri_mismatch` at login time → the URI in the console differs by one character from what the app sends (http vs https, 8000 vs 5173, trailing slash). `access_denied / app not verified` → you forgot the test-user entry. Secret pasted with a trailing newline → token exchange fails mysteriously; re-paste.

**Docs:** developers.google.com/identity/openid-connect/openid-connect

## Step 0.4: Read the theory once

**What:** tonight, away from the keyboard, read ARCH §3 (the domain model) end to end, and skim §I.7's grade-save trace again.

**Why:** §3 is the only theory that genuinely pays before code exists: every table you'll type in §1.5 is motivated there, and the save algorithm you'll build in Phase 2 stops being clever and starts being obvious once §3.5 has settled overnight. Everything else in ARCH is better read _after_ the step that cites it.

**Check:** you can answer, from memory, "why do grade rows not reference the class?" and "what does version 0 mean?". If not, re-read §3.4.

---

# Part IV. Phase 1: The walking skeleton

**Phase goal:** by the end, a deployed app logs you in with your real Google account, FastAPI answers through a same-origin proxy, CI is green, and a fake school lives in the database. Nothing more, and deliberately so: every later feature lands faster on a deployed skeleton than on a perfect local one.

## Step 1.1: The monorepo takes shape

### 1.1.1 Workspace root

**What we're building:** the root `package.json` + `pnpm-workspace.yaml` + Turborepo: the frame every package bolts onto.

**Why:** pnpm workspaces make `apps/*` and `packages/*` one installable universe (so `@flrc/teacher` can import `@flrc/ui` as source); Turborepo reads one JSON of task wiring and gives you "run everything, in order, in parallel, cached", which is the difference between a monorepo and a folder of regrets.

**Layer 1 · Nudge:** `pnpm init` at the root, mark it private, tell pnpm where packages live, add turbo, describe six tasks.

**Layer 2 · Guide:** `pnpm-workspace.yaml` needs one key, `packages:`, listing the two globs. `turbo.json` (v2 schema: the key is `tasks`, not the old `pipeline`) declares: `build` depends on `^build` (caret = "my dependencies' build first") and outputs `dist/**`; `lint`, `typecheck`, `test` are plain; `generate` will later chain schema-export → client-generation; `dev` is uncached and persistent.

**Layer 3 · Exact assembly:**

```bash
pnpm init
pnpm add -D turbo -w
```

Edit the root `package.json` to exactly:

```json
{
  "name": "fl-reportcard",
  "private": true,
  "packageManager": "pnpm@<exact version printed by pnpm -v>",
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "test": "turbo run test",
    "generate": "turbo run generate"
  },
  "devDependencies": { "turbo": "^2.5.0" }
}
```

(Replace the `packageManager` placeholder with whatever `pnpm -v` printed; that field pins the
version for CI and teammates.)

Create `pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

Create `turbo.json`:

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "lint": {},
    "typecheck": { "dependsOn": ["^build"] },
    "test": { "dependsOn": ["^build"] },
    "generate": { "cache": false },
    "dev": { "cache": false, "persistent": true }
  }
}
```

**Check:** `pnpm turbo run build --dry-run` prints a summary with "Tasks: 0" and no error; an empty graph is the correct graph today.

**If it breaks:** `Could not find turbo.json` → you're not at the repo root. Complaints about `pipeline` → you pasted a Turborepo v1 example from an old blog; the key is `tasks`.

**Docs:** turborepo.dev/docs; read the "Structuring a repository" page now, ten minutes. **Why deeper:** ARCH decision #1.

### 1.1.2 The two SPAs

**What we're building:** `apps/teacher` and `apps/admin`, scaffolded by Vite's React-TS template and renamed into the `@flrc` scope.

**Why:** two apps, not one with role-routing, because teachers and admins have different bundles, different deploy targets at the school, and different blast radii; an admin-panel bug should not be able to take down grade entry. (ARCH §2.)

**Layer 1 · Nudge:** `pnpm create vite` twice with the react-ts template; fix each `package.json` name.

**Layer 2 · Guide:** the template drops a runnable app with `dev`/`build`/`preview` scripts. You change: `"name"` → `@flrc/teacher` / `@flrc/admin`, and add a `"typecheck": "tsc -b --noEmit"` script so Turborepo's task finds a target. Delete the demo CSS noise now or in 1.10; your call.

**Layer 3 · Exact assembly:**

```bash
pnpm create vite apps/teacher --template react-ts
pnpm create vite apps/admin --template react-ts
```

In `apps/teacher/package.json` set `"name": "@flrc/teacher", "private": true` and add to scripts: `"typecheck": "tsc -b --noEmit"`. Same for admin with its name. Then, from the root:

```bash
pnpm install
```

**Check:** `pnpm --filter @flrc/teacher dev` → the Vite starter spins at `localhost:5173`. Ctrl-C, same for admin (it'll pick 5174 if 5173 is busy, which is fine).

**If it breaks:** `--filter` matches nothing → the `name` field wasn't saved, or you didn't re-run `pnpm install` after renaming (pnpm indexes workspaces at install time).

### 1.1.3 The three shared packages

**What we're building:** `@flrc/ui`, `@flrc/i18n`, `@flrc/api-client` as **source-consumed internal packages**: no build step, the consuming app's Vite compiles them.

**Why:** the "internal packages" pattern (Turborepo's own recommendation) deletes the entire class of "did you rebuild the shared package?" bugs. `main` pointing at a `.ts` file looks illegal and is, for _published_ packages; for workspace-internal ones it's the whole trick.

**Layer 1 · Nudge:** three folders, each a `package.json` whose `main`/`types` point into `src/index.ts`, plus a stub export. One shared `tsconfig.base.json` at the root that everything extends.

**Layer 2 · Guide:** each package: `package.json` (name, private, main, types), `src/index.ts` (export _something_ so imports resolve), `tsconfig.json` extending the base. The base config carries the strictness and JSX settings once: `strict`, `moduleResolution: "bundler"`, `jsx: "react-jsx"`, ES2022 targets.

**Layer 3 · Exact assembly:** root `tsconfig.base.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "resolveJsonModule": true
  }
}
```

For each of `packages/ui`, `packages/i18n`, `packages/api-client` (shown for `ui`; repeat with the name changed):

`packages/ui/package.json`

```json
{
  "name": "@flrc/ui",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": { "lint": "eslint src", "typecheck": "tsc --noEmit" }
}
```

`packages/ui/tsconfig.json`

```json
{ "extends": "../../tsconfig.base.json", "include": ["src"] }
```

`packages/ui/src/index.ts`

```ts
export const Hello = () => <p>flrc ui alive</p>;
```

(That file must be `index.tsx` since it contains JSX; name it `src/index.tsx` and point `main`/`types` at it. The other two packages keep plain `index.ts` with e.g. `export const placeholder = true;`.)

Also make both **apps'** `tsconfig.json` extend the base (keep Vite's references structure if the template used `tsconfig.app.json`; extend from there).

**Check:** next sub-step proves the wiring live.

### 1.1.4 Prove the wiring

**What we're building:** the teacher app importing a component from `@flrc/ui` with zero build steps in between.

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/teacher add @flrc/ui@workspace:*
```

In `apps/teacher/src/App.tsx`, import `{ Hello }` from `@flrc/ui` and render it. Run the dev server.

**Check:** the page shows _flrc ui alive_; edit the string in `packages/ui/src/index.tsx` → hot-reloads in the app. That round trip _is_ the monorepo working.

**If it breaks:** "Failed to resolve import @flrc/ui" → `pnpm install` after adding the dependency; or the `main` path doesn't match the actual filename (`index.ts` vs `index.tsx`). JSX error inside the package → the base tsconfig's `jsx: "react-jsx"` isn't being inherited; check the `extends` chain.

Commit: `feat: monorepo scaffold`, and write **DECISIONS.md #1** (monorepo, pnpm+Turborepo, internal-packages-as-source, over: two repos / Nx) in your own words. Ten minutes, do it now; the habit is the deliverable.

## Step 1.2: Tooling baseline (format, lint, hooks)

### 1.2.1 Prettier

**What / Why:** one formatter, root-level, so diffs are content, not whitespace, and code review (even self-review) reads clean.

**Layer 3 · Exact assembly:**

```bash
pnpm add -D prettier -w
```

Root `.prettierrc`: `{ "singleQuote": true, "semi": true, "printWidth": 100 }` (taste: pick once, never discuss again). Root `.prettierignore`:

```
dist/
.turbo/
packages/api-client/src/
pnpm-lock.yaml
```

(The generated client is machine-formatted; fighting it wastes hooks.)

**Check:** `pnpm prettier --check .` runs; it may list files; `pnpm prettier --write .` once, commit as `style: prettier pass`.

### 1.2.2 ESLint 10, flat config, per app

**What we're building:** ESLint 10 flat config in both apps and `packages/ui`: JS recommended + typescript-eslint + React hooks rules. ESLint 10 only supports flat config and looks for `eslint.config.js` starting from each linted file, so every lint target owns its config and dependencies.

**Why:** the hooks rules alone (deps arrays, conditional hooks) prevent the two most common React footguns; typescript-eslint catches the unsafe-`any` drift that strict tsconfig can't see in expressions.

**Layer 1 · Nudge:** `eslint.config.js` at each package root, composing three recommended sets with `typescript-eslint`'s helper.

**Layer 3 · Exact assembly (per app; ui too):**

```bash
pnpm --filter @flrc/teacher add -D eslint@^10.7.0 @eslint/js@^10.0.1 typescript-eslint@^8.64.0 eslint-plugin-react-hooks@^7.1.1
```

`apps/teacher/eslint.config.js`:

```js
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      parserOptions: { tsconfigRootDir: import.meta.dirname },
    },
  },
]);
```

For `packages/ui`, ensure its manifest declares `"type": "module"` so Node loads
`eslint.config.js` as ESM. Use the same config without the app-only React Refresh rules.

The template already gave you a `"lint": "eslint src"` script; keep it (add it where missing).

**Check:** `pnpm turbo run lint`; three packages, all pass (the Vite template code is clean).

**If it breaks:** ESLint cannot find a config → v10 searches from the linted file, so confirm that package has its own `eslint.config.js`. Node compatibility error → use the Node 26 version in `.node-version`. `reactHooks.configs.flat.recommended` undefined → the React Hooks plugin is stale; install the pinned major above.

### 1.2.3 Lefthook

**What we're building:** git hooks from one YAML: staged TS gets Prettier+ESLint, staged Python (from §1.3 on) gets Ruff; commit refuses if any fail.

**Why:** hooks convert "I'll lint later" into physics. Lefthook specifically because it's one fast binary that treats both languages as equals (ARCH decision #16).

**Layer 3 · Exact assembly:**

```bash
pnpm add -D lefthook -w
pnpm lefthook install
```

Root `lefthook.yml`:

```yaml
glob_matcher: doublestar

pre-commit:
  parallel: true
  jobs:
    - name: prettier
      glob: "**/*.{ts,tsx,css,md,json,yaml,yml}"
      run: pnpm prettier --check {staged_files}

    - name: eslint-teacher
      root: "apps/teacher/"
      glob: "apps/teacher/**/*.{ts,tsx}"
      run: pnpm eslint --no-warn-ignored {staged_files}

    - name: eslint-admin
      root: "apps/admin/"
      glob: "apps/admin/**/*.{ts,tsx}"
      run: pnpm eslint --no-warn-ignored {staged_files}

    - name: eslint-ui
      root: "packages/ui/"
      glob: "packages/ui/**/*.{ts,tsx}"
      run: pnpm eslint --no-warn-ignored {staged_files}
```

(The `ruff` block will simply never match until §1.3 creates Python files: harmless now, armed later.)

**Check:** add a deliberately unformatted line to any `.ts` file, `git add`, `git commit` → the hook blocks with Prettier's complaint; fix; commit passes. Revert the vandalism.

**If it breaks:** hooks don't fire at all → `pnpm lefthook install` writes `.git/hooks`; re-run it after any fresh clone (add a root `"prepare": "lefthook install"` script so pnpm does it automatically; do that now).

## Step 1.3: The FastAPI skeleton

### 1.3.1 Project + dependencies

**What we're building:** `apps/backend` as a real uv-managed Python project with FastAPI installed and a package layout that will hold everything backend for the next two months.

**Why:** uv gives you a locked, reproducible environment (`uv.lock` is to Python what `pnpm-lock.yaml` is to JS); the installable `src/flrc/` package layout is what lets imports, tests, Docker, and Alembic all agree on where code lives without relying on the current working directory.

**Layer 1 · Nudge:** initialize a packaged uv application, add `fastapi[standard]` and `pydantic-settings`, then shape `src/flrc/` with `main.py`, `config.py`, and a `modules/system/` feature.

**Layer 2 · Guide:** `uv init apps/backend` writes `pyproject.toml` and pins Python in `.python-version`. The `[standard]` extra matters: bare `fastapi` has no dev server CLI. Delete uv's sample file; create the package by hand. Add ruff/mypy/pytest as dev deps and configure them in the same `pyproject.toml` (one file to rule the Python side).

**Layer 3 · Exact assembly:**

```bash
uv init --package --build-backend uv --name flrc-backend apps/backend
cd apps/backend
rm -f main.py hello.py            # whichever sample uv created
rm -rf src/flrc_backend           # replace uv's normalized package name with the product package
uv add "fastapi[standard]" pydantic-settings
uv add --dev ruff mypy pytest
mkdir -p src/flrc/modules/system tests
touch src/flrc/__init__.py src/flrc/modules/__init__.py src/flrc/modules/system/__init__.py tests/__init__.py
```

Append to `apps/backend/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true

[tool.uv.build-backend]
module-name = "flrc"
```

(`I` = import sorting, `UP` = pyupgrade. Ruff will quietly modernize your Python as you write; that's a feature, so accept its fixes and read them.)

**Check:** `uv run python -c "import fastapi; print(fastapi.__version__)"` prints a version; `cat .python-version` shows 3.13.

### 1.3.2 Settings: the only place configuration exists

**What we're building:** `src/flrc/config.py`, a typed `Settings` object that reads environment variables (and a local `.env`), plus the `.env.example` that documents every knob.

**Why:** twelve-factor configuration. Every later step ("set `WORKER_HEALTH_URL`") assumes this single funnel; hardcoded values are how secrets leak and how demo/school deployments diverge invisibly.

**Layer 1 · Nudge:** one `BaseSettings` subclass, one field per knob from §12.1 of ARCH, `model_config` pointing at `.env`, one module-level instance.

**Layer 2 · Guide:** pydantic-settings maps field names to env vars case-insensitively (`database_url` ← `DATABASE_URL`). Give harmless dev defaults to non-secrets so a fresh clone runs against Compose with zero setup; leave secrets defaulting to empty strings so forgetting them fails loudly at Google's door, not silently.

**Layer 3 · Exact assembly:** `src/flrc/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | demo | school
    database_url: str = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc"
    database_url_direct: str = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc"
    redis_url: str = "redis://localhost:6379/0"
    session_secret: str = "dev-secret-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_google_domain: str = ""
    frontend_origin: str = "http://localhost:5173"
    worker_health_url: str = ""
    ops_token: str = "dev-ops-token"


settings = Settings()
```

`apps/backend/.env.example` (commit this; never commit `.env`):

```
ENV=dev
DATABASE_URL=postgresql+asyncpg://flrc:flrc@localhost:5432/flrc
DATABASE_URL_DIRECT=postgresql+asyncpg://flrc:flrc@localhost:5432/flrc
REDIS_URL=redis://localhost:6379/0
SESSION_SECRET=change-me-48-random-chars
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ALLOWED_GOOGLE_DOMAIN=yourschool.k12.tr
FRONTEND_ORIGIN=http://localhost:5173
WORKER_HEALTH_URL=
OPS_TOKEN=change-me
```

`cp .env.example .env` and fill in the Google values from Step 0.3 plus your school's real domain.

**Check:** `uv run python -c "from flrc.config import settings; print(settings.env, settings.allowed_google_domain)"` prints your values.

**If it breaks:** settings ignore your `.env` → you're running from the wrong directory (`env_file=".env"` is relative to the process CWD; run api commands from `apps/backend`). A value "won't change" → real environment variables beat `.env`; check `echo $DATABASE_URL`.

### 1.3.3 The app factory + healthz

**What we're building:** `src/flrc/main.py` with a `create_app()` factory and the first feature router in `src/flrc/modules/system/router.py`.

**Why the factory:** tests will build private app instances with overridden dependencies (fake users, scratch DBs); a module-level-only `app` makes that impossible. It also forces you to meet FastAPI's dependency-override mechanism early; Phase 2's permission tests live on it. **Why `/api` prefix even server-side:** the proxy forwards `/api/*` verbatim; if the backend also serves under `/api`, dev and prod paths are byte-identical and a whole class of "works locally" bugs never exists. Docs move under the prefix too, so `/api/docs` works through the proxy.

**Layer 3 · Exact assembly:** `src/flrc/modules/system/router.py`:

```python
from fastapi import APIRouter, Response

router = APIRouter(tags=["system"])


@router.get("/healthz", status_code=204, response_class=Response)
def healthz() -> Response:
    return Response(status_code=204)
```

Then `src/flrc/main.py` composes it:

```python
from fastapi import FastAPI

from flrc.modules.system.router import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="FL-ReportCard",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.include_router(system_router, prefix="/api")
    return app


app = create_app()
```

This establishes the rule used by later steps: a feature owns its router and schemas; the app
factory composes feature routers.

### 1.3.4 The Turborepo shim

**What we're building:** a tiny `apps/backend/package.json` so the one task runner drives Python too.

**Why:** `pnpm turbo run lint` should mean _the whole repo_, both languages, one command, one CI job graph. The shim is four script lines that translate Turbo's verbs into `uv run` verbs.

**Layer 3 · Exact assembly:** `apps/backend/package.json`:

```json
{
  "name": "@flrc/backend",
  "private": true,
  "scripts": {
    "dev": "uv run fastapi dev src/flrc/main.py",
    "lint": "uv run ruff check . && uv run ruff format --check .",
    "typecheck": "uv run mypy src/flrc",
    "test": "uv run pytest"
  }
}
```

Then from the repo root: `pnpm install` (so pnpm indexes the new workspace member).

**Check (for all of 1.3):**

```bash
pnpm --filter @flrc/backend dev        # in one terminal
curl -i localhost:8000/api/healthz    # → 204, empty body
```

Open `http://localhost:8000/api/docs`: Swagger UI with one endpoint. Then `pnpm turbo run lint typecheck` from the root: six packages, all green. Commit: `feat(backend): fastapi skeleton + settings`.

**If it breaks:** `fastapi: command not found` → the `[standard]` extra is missing. Turbo can't find the api tasks → you skipped the root `pnpm install`. mypy shouts about pydantic → you're on an ancient mypy; `uv lock --upgrade-package mypy`.

**Docs:** fastapi.tiangolo.com; read "First Steps" and "Settings and Environment Variables". **Why deeper:** ARCH §4/1.3.

## Step 1.4: Local services + the shipping container

### 1.4.1 Docker Compose: Postgres + Redis

**What we're building:** one command that raises the two stateful services the whole backend leans on, with health checks so "up" means _ready_.

**Why containers for these and not the API:** you edit the API constantly (host process, instant reload); you never edit Postgres; you just need version-pinned instances that reset cleanly. The compose file is also the repo's onboarding doc: any reviewer can run your stack with one command.

**Layer 1 · Nudge:** two services, pinned images, exposed default ports, a named volume for Postgres, health checks (`pg_isready`, `redis-cli ping`).

**Layer 3 · Exact assembly:** `infra/compose/compose.dev.yaml`:

```yaml
services:
  postgres:
    image: postgres:18-alpine
    environment:
      POSTGRES_USER: flrc
      POSTGRES_PASSWORD: flrc
      POSTGRES_DB: flrc
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U flrc"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:8-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

The root `pnpm dev` command runs Compose with `--wait` before it starts the API and SPAs. Use
`pnpm dev:apps` only when Postgres and Redis are already managed separately.

**Check:** `pnpm dev` then
`docker compose -f infra/compose/compose.dev.yaml ps` → both `healthy`.
`docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "select version();"`
prints PostgreSQL 18.x.

**If it breaks:** port 5432 already bound → a system postgres is running (`sudo systemctl stop postgresql`) or change the left side of the mapping to `5433:5432` _and_ your `.env` URLs to match. Volume from an older experiment with a different password → `docker compose -f infra/compose/compose.dev.yaml down -v` wipes it (dev data only!).

### 1.4.2 The Dockerfile (built now, shipped in 1.11)

**What we're building:** the exact multi-stage image Render will run: uv installs locked deps in a builder stage; the slim runtime stage carries only the venv and your code.

**Why now, not at deploy time:** building the artifact early means "runs in the container" is verified weeks before it matters, and Phase 4's WeasyPrint system libraries have a home waiting (one `apt-get` line into the runtime stage). Multi-stage because build tools don't belong in production images; layer-ordering (deps before code) because that's what makes rebuilds take seconds.

**Layer 2 · Guide:** the uv docs' Docker integration page is the canonical pattern: copy the uv binary from its official image, `uv sync --frozen` against just the lockfiles first (cacheable layer), then copy source and sync again. Runtime `CMD` must honor Render's `$PORT`.

**Layer 3 · Exact assembly:** `apps/backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "uvicorn flrc.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Add `apps/backend/.dockerignore`: `.venv`, `__pycache__`, `.env*`, `tests/`.

**Check:** `docker build -t flrc-api apps/backend` succeeds; `docker run --rm -p 8001:8000 flrc-api` → `curl localhost:8001/api/healthz` answers (healthz touches no DB; that's why it can).

**If it breaks:** `uv.lock not found` → you haven't run any `uv add` yet in this folder, or you're building from the wrong context path (the final `apps/backend` argument _is_ the context). `ModuleNotFoundError: flrc` → the project lacks its uv build-system declaration, or `COPY src ./src` is missing.

### 1.4.3 Five minutes of Turkish collation (an investment)

**What:** prove, in a throwaway table, that İ/ı/Ç/Ö sort correctly under an ICU `tr-TR` collation and wrongly without it.

**Why:** §3.1's student search and every roster sort depend on Turkish text behavior; meeting the fix _before_ the bug means Phase 3's version of you smiles instead of debugging.

**Layer 3 · Exact assembly:** `docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc`, then:

```sql
CREATE COLLATION IF NOT EXISTS turkish (provider = icu, locale = 'tr-TR');
CREATE TEMP TABLE demo(name text);
INSERT INTO demo VALUES ('İnci'), ('Irmak'), ('istanbul'), ('Çağla'), ('Ömer'), ('Ilgaz');
SELECT name FROM demo ORDER BY name;                    -- default: visibly wrong order
SELECT name FROM demo ORDER BY name COLLATE turkish;    -- correct Turkish order
\q
```

**Check:** the two orderings differ; the second one is the one a Turkish teacher would expect.

**If it breaks:** `ICU is not supported in this build` → rare on modern official images, but if it happens swap the compose image to `postgres:18` (Debian variant) and `docker compose -f infra/compose/compose.dev.yaml down -v && docker compose -f infra/compose/compose.dev.yaml up -d`.

Commit: `feat: compose + api dockerfile`.

**Docs:** docs.astral.sh/uv/guides/integration/docker · postgresql.org/docs/current/collation.html. **Why deeper:** ARCH §4/1.4.

## Step 1.5: SQLAlchemy 2.0 + Alembic + the first eight tables

### 1.5.1 Dependencies + the declarative base

**What we're building:** the foundation every model stands on: a `Base` class carrying a **naming convention**, and a timestamp mixin.

**Why the naming convention before anything else:** without it, Postgres invents constraint names (`semesters_number_check`) and Alembic's autogenerated migrations become undiffable noise; with it, every index/unique/check/FK gets a deterministic, readable name, and reading a migration diff becomes a two-minute code review instead of archaeology. This is the single highest-leverage five lines in the backend.

**Layer 1 · Nudge:** `uv add sqlalchemy asyncpg alembic`; a `MetaData(naming_convention=…)` with the standard five keys; `DeclarativeBase` bound to it; a mixin with `created_at`/`updated_at` using `func.now()`.

**Layer 3 · Exact assembly:**

```bash
uv add sqlalchemy asyncpg alembic
mkdir -p src/flrc/db && touch src/flrc/db/__init__.py
```

`src/flrc/db/base.py`:

```python
from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

### 1.5.2 The eight Phase-1 models

**What we're building:** `src/flrc/db/models.py`: users, years, semesters, classes, students, enrollments, student languages, teaching assignments. Grades/audit/grants wait for Phase 2, when needing them will make you understand them.

**Why each constraint is where it is:** the CHECKs make illegal states unrepresentable at the last line of defense (the app validates too, but apps have bugs); the composite UNIQUEs _are_ business rules ("one enrollment per student per year"; the sentence and the constraint are the same thing); `search_name` exists because Turkish İ/ı breaks naive case-insensitive search (Python's `casefold()` at write time is the fix; see ARCH §6/3.1); and note what's _absent_: no gender, no birthdate, no class FK anywhere near future grades.

**Layer 1 · Nudge:** eight classes, 2.0 style only (`Mapped[]`, `mapped_column`), `BigInteger + Identity()` PKs, constraints in `__table_args__` with explicit `name=` on every CheckConstraint (the convention needs it).

**Layer 2 · Guide:** field lists live in ARCH §3.1 and the step 1.5 spec of the old BUILD-STEPS, or just below. Statuses are `str` columns with IN-list CHECKs, defaults set Python-side (`default="setup"`), which is honest for an app that is its database's only writer.

**Layer 3 · Exact assembly:** `src/flrc/db/models.py`:

```python
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from flrc.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    full_name: Mapped[str]
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_coordinator: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class AcademicYear(TimestampMixin, Base):
    __tablename__ = "academic_years"
    __table_args__ = (
        CheckConstraint("status IN ('setup','active','archived')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    label: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="setup")


class Semester(TimestampMixin, Base):
    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("year_id", "number"),
        CheckConstraint("number IN (1, 2)", name="number_valid"),
        CheckConstraint("status IN ('open','locked')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(default="open")


class SchoolClass(TimestampMixin, Base):
    __tablename__ = "school_classes"
    __table_args__ = (
        UniqueConstraint("year_id", "grade_level", "section"),
        CheckConstraint("grade_level BETWEEN 1 AND 8", name="grade_level_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    grade_level: Mapped[int]
    section: Mapped[str]


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    full_name: Mapped[str]
    search_name: Mapped[str] = mapped_column(index=True)


class Enrollment(TimestampMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "year_id"),
        UniqueConstraint("year_id", "school_number"),
        CheckConstraint(
            "school_number IS NULL OR school_number > 0",
            name="school_number_positive",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    school_number: Mapped[int | None] = mapped_column(BigInteger)


class StudentLanguage(TimestampMixin, Base):
    __tablename__ = "student_languages"
    __table_args__ = (
        UniqueConstraint("student_id", "year_id"),
        CheckConstraint("language IN ('german','french')", name="language_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"))
    language: Mapped[str]


class TeachingAssignment(TimestampMixin, Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (
        UniqueConstraint("class_id", "role"),
        CheckConstraint("role IN ('main','skills','german','french')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    role: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

Read it back against ARCH §3.1 once (every table there, nothing extra), and say out loud why `enrollments` has a `class_id` but nothing else ever will.

### 1.5.3 The async session plumbing

**What we're building:** one engine, one sessionmaker, one dependency: the only three database objects FastAPI ever sees.

**Layer 3 · Exact assembly:** `src/flrc/db/session.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from flrc.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionMaker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionMaker() as session:
        yield session
```

`pool_pre_ping=True` is Neon insurance bought early: after its 5-minute autosuspend, dead pooled connections get detected and replaced transparently instead of throwing at a teacher. `expire_on_commit=False` keeps ORM objects readable after commit; the default (True) causes mystifying lazy-load errors in async code.

### 1.5.4 Alembic, the async template, and your first migration

**What we're building:** a migrations directory wired to your metadata and your settings, plus migration #0001 containing all eight tables.

**Why the ceremony matters:** migrations are the only schema change mechanism from now until forever, including against the archived years of 2030. The discipline (autogenerate → **read the diff line by line** → apply; one migration per PR; never edit an applied one) is what makes that safe. And the pooled/direct rule: **the app uses Neon's pooled URL, Alembic uses the direct one**; DDL through a transaction-mode pooler fails in ways that look like haunted hardware.

**Layer 1 · Nudge:** `alembic init -t async migrations` from `apps/backend`; point `env.py` at your metadata and your settings; autogenerate; read; upgrade.

**Layer 2 · Guide:** three edits in `migrations/env.py`: (1) import your models module _for its side effect_ (tables register on `Base.metadata` at import; miss this and autogenerate produces an empty migration); (2) set `target_metadata = Base.metadata`; (3) feed the URL from settings, with an env-var override hook for tests.

**Layer 3 · Exact assembly:**

```bash
uv run alembic init -t async migrations
```

In `migrations/env.py`: near the top, after `config = context.config`, add:

```python
import os

from flrc.config import settings
from flrc.db import models  # noqa: F401  - imported so tables register on the metadata
from flrc.db.base import Base

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("FLRC_MIGRATIONS_URL") or settings.database_url_direct,
)
```

and replace the template's `target_metadata = None` with `target_metadata = Base.metadata`. (Leave `sqlalchemy.url` in `alembic.ini` as-is; the code above overrides it.)

Then:

```bash
uv run alembic revision --autogenerate -m "core tables"
```

**Now read the generated file** in `migrations/versions/` against this checklist before applying: 8 `op.create_table` calls · every CheckConstraint present with a `ck_<table>_<name>` name · the composite uniques on semesters/school_classes/enrollments/student_languages/teaching_assignments · indexes on `users.email` and `students.search_name` · FKs named `fk_…`. Anything missing means a model typo: fix the model, delete the revision file, regenerate (never hand-patch revision #1).

```bash
uv run alembic upgrade head
```

**Check:**

```bash
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "\dt"        # 8 tables + alembic_version
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "\d semesters"  # shows ck_semesters_number_valid etc.
uv run alembic downgrade -1 && uv run alembic upgrade head    # round-trips clean
```

**If it breaks:** empty autogenerate → the models import in `env.py` is missing (the `noqa` line is load-bearing). `MissingGreenlet` / driver errors → your URL lost its `+asyncpg` (the async template needs an async driver). `Target database is not up to date` on revision → you edited models after upgrading; upgrade first, then autogenerate the delta.

### 1.5.5 The migration guard test

**What we're building:** a pytest that proves `upgrade head` works from an empty database: the cheap insurance that catches 90% of migration accidents in CI, forever.

**Layer 2 · Guide:** a scratch database (`flrc_test`), the Alembic _command API_ (`alembic.command.upgrade`) driven from Python, and the `FLRC_MIGRATIONS_URL` override you planted in env.py.

**Layer 3 · Exact assembly:** one-time (and again in CI, §1.11): `docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_test`. Then `tests/test_migrations.py`:

```python
import os

from alembic import command
from alembic.config import Config

TEST_URL = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test"


def test_migrations_apply_from_zero() -> None:
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
```

**Check:** `uv run pytest -q` → 1 passed. Commit: `feat(api): schema v1 + alembic`. Write **DECISIONS.md** entries: naming conventions, text+CHECK over native enums, pooled-vs-direct rule, bigint IDs (and the UUIDv7 paragraph; see ARCH decision #17).

**Docs:** the SQLAlchemy 2.0 ORM quickstart + Alembic's "Auto Generating Migrations" page (its list of what autogenerate _cannot_ detect is required reading). **Why deeper:** ARCH §4/1.5, §3.1.

## Step 1.6: The seed CLI and the fictional school

**What we're building:** `uv run flrc seed`: a deterministic four-year fake school. It contains three archived years plus active 2026-2027, 52 classes per year (A-F at every grade and G in grades 1, 3, 5, and 7), exactly 22 students per class, and 28 teachers. School numbers run from 1 through 1,144 independently in every year.

**Why it's a product feature, not a convenience:** this data _is_ the public demo, the screenshot source, and the test substrate. Determinism (fixed Faker seed) makes screenshots reproducible; the your-real-email trick is what lets Step 1.7's OAuth log you in before any admin UI exists; and the hard rule rides on top: **real student data never enters this system's repo, demo, or fixtures** (ARCH §8.5). Note it seeds no gender field because no gender field exists.

**Layer 1 · Nudge:** Typer app in `src/flrc/cli.py`, registered as a console script; a **sync** engine (a CLI has no event loop to win, and this is your first meeting with the two-engine reality of ARCH decision #6); Faker `tr_TR`; deterministic plans building teachers → years → classes → connected yearly enrollments.

**Layer 2 · Guide:** `uv add typer faker "psycopg[binary]"`: psycopg is the sync driver; derive the sync URL by swapping `+asyncpg` → `+psycopg`. Structure: `reset()` deletes child tables before parents (FK order); `seed_class_plans()` is the testable allocation contract; `seed()` flushes after inserting parents so generated ids exist for children. A-F rosters reuse the previous year's student identities at the next grade. Missing G destinations model departures, new grade/G rosters model arrivals, and every enrollment receives that year's sequential number. Register `flrc = "flrc.cli:app"` under `[project.scripts]`.

**Layer 3 · Exact assembly:** the maintained implementation is
`apps/backend/src/flrc/cli.py`; keeping a second full copy here caused the handbook to drift from the
executable generator. Its load-bearing constants and plan contract are:

```python
CORE_SECTIONS = ("A", "B", "C", "D", "E", "F")
G_SECTION_GRADES = frozenset({1, 3, 5, 7})
STUDENTS_PER_CLASS = 22
ACADEMIC_YEARS = ("2023-2024", "2024-2025", "2025-2026", "2026-2027")

PRIMARY_ENGLISH_KEYS = tuple(f"primary-{number:02d}" for number in range(1, 13))
SECONDARY_ENGLISH_KEYS = (
    "my-account",
    *(f"secondary-{number:02d}" for number in range(1, 12)),
)
GERMAN_KEYS = ("german-01", "german-02")
FRENCH_KEYS = ("french-01", "french-02")
```

`seed_class_plans()` assigns only primary English keys to grades 1-4, only secondary English keys
to grades 5-8, and language keys only to German/French roles in grades where L2 exists. The supplied
`--my-email` account occupies `my-account`, so all of its teaching assignments are middle-school
English `main` or `skills` roles. Past years have two filled, locked semesters; the current year has
a filled open semester 1 and a prepared locked semester 2. Written-note columns are populated in
every filled semester.

The deployed demo runs `flrc seed --demo` after migrations at API startup. This mode fills only an
empty academic database and reuses its single existing active, school-domain middle-school English
admin, preserving the account's Google identity and permissions. It skips existing years or
students, so redeployments retain demo edits. It requires `ENV=demo`; see
[demo startup](../infra/README.md#demo-database-migrations) for prerequisites.

```bash
uv sync   # installs the console script
uv run flrc reset
uv run flrc seed --my-email <your-real-school-email>
```

**Check:**

```bash
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "select count(*) from users;"                 # 28
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "select count(*) from school_classes;"        # 208
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c "select count(*) from enrollments;"           # 4576
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c \
  "select year_id, min(school_number), max(school_number), count(distinct school_number) from enrollments group by 1;" # 1 · 1144 · 1144
docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -c \
  "select teaching_field, count(*) from users group by 1;"                                # English 24 · German 2 · French 2
```

`tests/test_seed_plan.py` proves the class/staff boundaries and the complete A-F promotion path.
Run `seed` twice with the same seed value against a reset DB. Identical names, assignments, grades,
and notes both times: that's determinism working.

**If it breaks:** `flrc: command not found` → `uv sync` after adding `[project.scripts]` (scripts install at sync time). FK violation during reset → your delete order drifted from the list above. `psycopg` import error → the `[binary]` extra didn't install; re-run the add.

**Docs:** typer.tiangolo.com · faker.readthedocs.io (the `tr_TR` provider page). **Why deeper:** ARCH §4/1.6, the demo-data doctrine, worth re-reading now that it's real.

---

## Step 1.7: Google OAuth + Redis sessions (the centerpiece; budget 2-3 days)

**The one topology rule before any code:** the browser must **never see the Render domain**, not for API calls, and _not for the OAuth dance either_. Login starts at `<your-origin>/api/auth/login`, Google redirects back to `<your-origin>/api/auth/callback`, and the proxy carries both to FastAPI. That way the session cookie gets set on _your_ origin (localhost:5173 in dev, the Vercel/CF domain in prod), which is the only place it's any use. If you ever type `:8000` or `onrender.com` into a browser bar during auth, you're testing the wrong universe.

- [ ] **Console fix first (2 min):** in the Google console (Step 0.3 client), **add** the redirect URI `http://localhost:5173/api/auth/callback`. The `:8000` one can stay; you just won't use it.

### 1.7.1 Dependencies

```bash
uv add authlib itsdangerous httpx "redis[hiredis]"
mkdir -p src/flrc/modules/auth && touch src/flrc/modules/auth/__init__.py
```

### 1.7.2 The session store

**What we're building:** four small functions over Redis: the entire server side of "being logged in."

**Why sessions in Redis and not JWTs:** revocation. When a teacher leaves in October, you flip `is_active` and delete their keys: done, instantly, everywhere. A stateless JWT keeps working until expiry unless you build a denylist, at which point you've rebuilt sessions with extra steps. (ARCH decision #5; this is a top-five interview question and you're about to own it from experience.)

**Layer 1 · Nudge:** key `session:<random-id>` → value user-id, with an absolute expiry no later
than the end of one school day. Reading a session does not extend it indefinitely.

**Layer 2 · Guide:** `secrets.token_urlsafe(32)` creates the id. `SETEX` applies
`SESSION_TTL_SECONDS` at creation; `GET` reads without sliding. Maintain
`user_sessions:<user-id>` as a Redis set so admin deactivation can revoke every device
immediately without scanning unrelated sessions. Malformed Redis values are deleted and treated as
expired.

**Layer 3 · Exact assembly:** the maintained implementation is
`src/flrc/modules/auth/sessions.py`. Keep TTL ownership in settings, create the session and
per-user index in one transactional pipeline, and keep revocation idempotent. The focused security
tests are the executable assembly contract.

### 1.7.3 Cookie signing

**What we're building:** the browser-side half: the session id, cryptographically signed so it can't be forged, in an `HttpOnly` cookie.

**Why sign at all, if the id is random anyway:** defense in depth: a signature turns "guess a valid-looking key and make Redis do lookups" into "forge HMAC-SHA," and it gives you tamper-evidence for free. Why `HttpOnly`: JavaScript can never read it, so even an XSS hole can't exfiltrate the session. Why `SameSite=Lax`: cross-site POSTs won't carry it (CSRF layer one), but Google's top-level redirect back to you still will (which is exactly what login needs).

**Layer 3 · Exact assembly:** use the maintained
`src/flrc/modules/auth/cookies.py` implementation. School mode names the cookie
`__Host-flrc_session`, which requires `Secure`, `Path=/`, and no `Domain` attribute.
Development/test keeps a non-prefixed cookie because it runs over HTTP. Signing validation and the
cookie's `Max-Age` both use `SESSION_TTL_SECONDS` so the browser cannot outlive the Redis
record. Clearing the cookie must repeat its path/security attributes.

### 1.7.4 The OAuth routes

**What we're building:** `/api/auth/login`, `/api/auth/callback`, `/api/auth/logout`:
Authlib runs the protocol; _your_ code runs the domain, verified-email, allowlist, and stable-account
gates.

**Walkthrough (what actually happens when Ayşe clicks "Sign in"):** login generates a random `state`, stashes it in a short-lived cookie (that's what Starlette's SessionMiddleware is for here), and redirects her browser to Google's authorize endpoint carrying your client_id, the redirect_uri, the scopes, and that state. She consents on Google's page. Google redirects her browser to `<your-origin>/api/auth/callback?code=…&state=…`. Authlib checks the state matches (CSRF protection _on the flow itself_), then (server to server, browser uninvolved) POSTs the code plus your client secret to Google's token endpoint and receives tokens, **validating the ID token's signature and claims** against Google's published keys. Only now does your code run: is the `hd` claim your school's domain (the _claim_ is proof; the `hd` hint on the way out was cosmetics)? Is the email a pre-registered active user? Both yes → mint a session, set the cookie, land her on the app. Any no → bounce to `/login?error=<code>` and let i18n do the talking.

The final gate is stricter than the original two-gate walkthrough: require
`email_verified=true`, require the email itself to use the exact hosted domain, and bind the
allowlist row to Google's stable `sub` on first login. A later subject mismatch is denied even
when the same email has been reassigned.

**Layer 3 · Exact assembly:** `src/flrc/modules/auth/router.py`:

```python
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth import cookies, sessions
from flrc.config import settings
from flrc.db.models import User
from flrc.db.session import get_session
from flrc.modules.administration.names import normalize_email
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_origin}/login?error={code}")


@router.get("/login")
async def login(request: Request):
    redirect_uri = f"{settings.frontend_origin}/api/auth/callback"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, hd=settings.allowed_google_domain
    )


@router.get("/callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_session)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return _login_error("google_error")

    claims = token.get("userinfo") or {}
    email = normalize_email(str(claims.get("email", "")))
    subject = str(claims.get("sub", "")).strip()
    hosted_domain = str(claims.get("hd", "")).casefold().strip().rstrip(".")
    if hosted_domain != allowed_google_domain() or not email_is_in_school_domain(email):
        return _login_error("wrong_domain")
    if claims.get("email_verified") is not True:
        return _login_error("email_not_verified")
    if not subject:
        return _login_error("invalid_identity")

    result = await db.execute(select(User).where(User.email == email).with_for_update())
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return _login_error("not_registered")
    if user.google_subject is not None and user.google_subject != subject:
        return _login_error("identity_mismatch")
    if user.google_subject is None:
        user.google_subject = subject
        await db.commit()

    sid = await sessions.create_session(user.id)
    response = RedirectResponse(settings.frontend_origin)
    cookies.set_session_cookie(response, sid)
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(cookies.cookie_name())
    if token and (sid := cookies.unsign_sid(token)):
        await sessions.destroy_session(sid)
    cookies.clear_session_cookie(response)
```

Wire it into the factory; `src/flrc/main.py` gains, inside `create_app()` before `include_router`:

```python
from starlette.middleware.sessions import SessionMiddleware

from flrc.modules.auth.router import router as auth_router

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=(
            "__Host-flrc_oauth_state" if settings.env == "school" else "flrc_oauth_state"
        ),
        max_age=10 * 60,
        same_site="lax",
        https_only=settings.env != "dev",
        path="/api/auth",
    )
    app.include_router(auth_router, prefix="/api")
```

Two-cookies note, so devtools doesn't confuse you: `flrc_oauth_state` exists only to carry
Authlib's ten-minute `state` during the dance; `flrc_session` (or `__Host-flrc_session` in
school mode) is the actual login. Different jobs, both legitimate.

### 1.7.5 The `current_user` dependency

**What we're building:** the function every protected route depends on: cookie → signature → Redis → user row, with a distinct machine code at each failure.

**Why codes, not sentences:** the frontend translates codes through i18n; prose from the backend can't be translated and shouldn't be trusted for display. This is the error-contract pattern the whole app uses (ARCH invariant #7).

**Layer 3 · Exact assembly:** `src/flrc/modules/auth/dependencies.py`:

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth import cookies, sessions
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain
from flrc.db.models import User
from flrc.db.session import get_session


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": code})


async def current_user(
    request: Request, db: AsyncSession = Depends(get_session)
) -> User:
    token = request.cookies.get(cookies.cookie_name())
    if not token:
        raise _unauthorized("not_authenticated")
    sid = cookies.unsign_sid(token)
    if sid is None:
        raise _unauthorized("bad_session")
    user_id = await sessions.get_user_id(sid)
    if user_id is None:
        raise _unauthorized("session_expired")
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        await sessions.destroy_session(sid)
        raise _unauthorized("not_registered")
    if allowed_google_domain() and not email_is_in_school_domain(user.email):
        await sessions.destroy_session(sid)
        raise _unauthorized("wrong_domain")
    return user
```

### 1.7.6 The Origin-check middleware (your CSRF layer two)

**What we're building:** a gate on every state-changing request: same-origin traffic passes, cross-site traffic dies with `bad_origin`.

**Why this is enough:** with a same-origin proxy + `SameSite=Lax` cookies + this check on modern browsers' `Sec-Fetch-Site`/`Origin` headers, you meet current OWASP guidance without token-in-every-form gymnastics. Twenty lines you fully understand beat a library you don't.

**Layer 3 · Exact assembly:** `src/flrc/core/middleware.py`:

```python
from fastapi import Request
from fastapi.responses import JSONResponse

from flrc.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def origin_check_middleware(request: Request, call_next):
    if request.method not in SAFE_METHODS:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        allowed_origins = {settings.frontend_origin, settings.admin_origin}
        if settings.env == "school":
            allowed = origin in allowed_origins and site in {None, "same-origin", "none"}
        elif site is not None:
            allowed = site in ("same-origin", "none")
        else:
            allowed = origin in allowed_origins or (
                origin is None and settings.env in {"dev", "test"}
            )
        if not allowed:
            return JSONResponse(status_code=403, content={"code": "bad_origin"})
    return await call_next(request)
```

And in the factory: `app.middleware("http")(origin_check_middleware)`.

### 1.7.7 `GET /api/me`: the SPA's bootstrap

**Layer 3 · Exact assembly:** `src/flrc/modules/auth/me.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import current_user
from flrc.db.models import SchoolClass, TeachingAssignment, User
from flrc.db.session import get_session

router = APIRouter(tags=["me"])


class AssignmentOut(BaseModel):
    class_id: int
    class_name: str
    role: str


class MeOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_admin: bool
    is_coordinator: bool
    assignments: list[AssignmentOut]


@router.get("/me")
async def me(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> MeOut:
    rows = (
        await db.execute(
            select(
                TeachingAssignment.class_id,
                SchoolClass.grade_level,
                SchoolClass.section,
                TeachingAssignment.role,
            )
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(TeachingAssignment.user_id == user.id)
        )
    ).all()
    return MeOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_admin=user.is_admin,
        is_coordinator=user.is_coordinator,
        assignments=[
            AssignmentOut(
                class_id=r.class_id,
                class_name=f"{r.grade_level}/{r.section}",
                role=r.role,
            )
            for r in rows
        ],
    )
```

Import `router as me_router` from `flrc.modules.auth.me`, then include it in the factory with
`app.include_router(me_router, prefix="/api")`.

**Check 1.7 (in order; the API alone, before any frontend):**

1. `docker compose -f infra/compose/compose.dev.yaml up -d` · `uv run flrc seed --my-email <your-real-school-email>` · start the API.
2. There's no SPA yet, so simulate the proxy with the API origin _once_, knowingly: temporarily set `FRONTEND_ORIGIN=http://localhost:8000` in `.env`, add `http://localhost:8000/api/auth/callback` back in the console if you removed it, restart, and visit `http://localhost:8000/api/auth/login` **with your school account**. You should bounce through Google and land on a 404 at `:8000/` (irrelevant); open devtools → Application → Cookies: `flrc_session`, HttpOnly ✓.
3. `http://localhost:8000/api/me` in that same browser → your JSON, with your assignments from the seed.
4. `http://localhost:8000/api/docs` → try `POST /api/auth/logout` → `/api/me` now 401 `not_authenticated`.
5. Log in with a personal Gmail → redirected with `?error=wrong_domain` (no `hd` claim on personal accounts; working as intended).
6. Revert `FRONTEND_ORIGIN` to `http://localhost:5173`; the full proxied loop gets its real check in 1.10.

**If it breaks:** `redirect_uri_mismatch` → the console URI and `{frontend_origin}/api/auth/callback` differ by one character; read both aloud. `mismatching_state` → the SessionMiddleware isn't registered, or you started on one origin and finished on another (the topology rule again). `hd` always missing → you're testing with a personal account. Login loop with no cookie → `secure=True` on plain http; confirm `ENV=dev`. School account refused by Google itself → the Workspace admin restricts third-party apps; they must allowlist your client ID (a school-side toggle; note it for the pitch).

**Docs:** docs.authlib.org (Starlette client page) · the MDN `Set-Cookie` page; read the SameSite section properly once. **Why deeper:** ARCH §4/1.7, decisions #4 and #5.

Commit: `feat(api): google oauth, sessions, origin guard, /me`.

## Step 1.8: Role guards + the test harness

### 1.8.1 The guard dependencies

**What we're building:** `require_admin`, `require_coordinator_or_admin`, and the two status guards (`writable_semester`, `writable_year`): small now, load-bearing forever.

**Why 401 vs 403 is not pedantry:** 401 means "I don't know you" (client redirects to login); 403 means "I know you and no" (client shows _not permitted_). Mixing them breaks frontend logic and is a real interview probe. And the status guards are the entire archive feature wearing a two-function trench coat (ARCH §3.2): every write route that depends on them today is automatically read-only the day a year is archived.

**Layer 3 · Exact assembly:** append to `src/flrc/modules/auth/dependencies.py`:

```python
from sqlalchemy import select

from flrc.db.models import AcademicYear, Semester


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "forbidden"})


async def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise _forbidden()
    return user


async def require_coordinator_or_admin(user: User = Depends(current_user)) -> User:
    if not (user.is_admin or user.is_coordinator):
        raise _forbidden()
    return user


async def writable_semester(db: AsyncSession = Depends(get_session)) -> Semester:
    result = await db.execute(
        select(Semester)
        .join(AcademicYear, AcademicYear.id == Semester.year_id)
        .where(AcademicYear.status == "active", Semester.status == "open")
    )
    semester = result.scalar_one_or_none()
    if semester is None:
        raise HTTPException(status_code=409, detail={"code": "semester_locked"})
    return semester


async def writable_year(db: AsyncSession = Depends(get_session)) -> AcademicYear:
    result = await db.execute(
        select(AcademicYear)
        .where(AcademicYear.status != "archived")
        .order_by(AcademicYear.id.desc())
    )
    year = result.scalars().first()
    if year is None:
        raise HTTPException(status_code=409, detail={"code": "year_not_writable"})
    return year
```

Give the matrix something admin-only to bite on, in `src/flrc/modules/auth/admin.py`:

```python
from fastapi import APIRouter, Depends

from flrc.modules.auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(_=Depends(require_admin)) -> dict[str, bool]:
    return {"pong": True}
```

(Import `router as admin_router` from this module and include it with
`app.include_router(admin_router, prefix="/api")`.)

### 1.8.2 The harness + the matrix

**What we're building:** a `conftest.py` that can build the app _as anyone_ (no cookies, no Google, no server) and the first rows of the role × endpoint matrix that will grow every phase into the most valuable test file in the repo.

**Why dependency overrides are the trick:** `create_app()` returns a fresh app whose `dependency_overrides[current_user]` can be a lambda returning any `User` you like. The rest of the stack (routing, validation, your guards) runs for real. This is the payoff of the factory from 1.3.3.

**Layer 3 · Exact assembly:** `uv add --dev pytest-asyncio` and add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`tests/conftest.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from flrc.modules.auth.dependencies import current_user
from flrc.db.models import User
from flrc.main import create_app

USERS = {
    "teacher": User(id=1, email="t@x", full_name="T", is_admin=False, is_coordinator=False, is_active=True),
    "admin": User(id=2, email="a@x", full_name="A", is_admin=True, is_coordinator=False, is_active=True),
    "coordinator": User(id=3, email="c@x", full_name="C", is_admin=False, is_coordinator=True, is_active=True),
}


@pytest.fixture
def client_as():
    def make(role: str | None) -> AsyncClient:
        app = create_app()
        if role is not None:
            user = USERS[role]
            app.dependency_overrides[current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return make
```

`tests/test_guards.py`:

```python
import pytest

MATRIX = [
    ("GET", "/api/healthz", None, 204),
    ("GET", "/api/me", None, 401),
    ("GET", "/api/admin/ping", None, 401),
    ("GET", "/api/admin/ping", "teacher", 403),
    ("GET", "/api/admin/ping", "coordinator", 403),
    ("GET", "/api/admin/ping", "admin", 200),
]


@pytest.mark.parametrize("method,path,role,expected", MATRIX)
async def test_matrix(client_as, method, path, role, expected):
    async with client_as(role) as client:
        response = await client.request(method, path)
    assert response.status_code == expected
```

**Check:** `uv run pytest -q` → all green (plus the migration test from 1.5.5). Break `require_admin` on purpose (invert the condition), watch two rows fail, restore. That red run is the point: you just proved the matrix guards you.

**If it breaks:** `async def functions are not natively supported` → the `asyncio_mode = "auto"` block didn't land. `/api/me` as a role blows up on the DB → correct and expected later; today the override returns before any query; if it doesn't, check that your override targets `current_user` itself, not a copy.

Commit: `feat(api): guards + role matrix harness`. **Docs:** fastapi's "Testing Dependencies with Overrides" page.

## Step 1.9: The generated, typed API client

**What we're building:** `packages/api-client` filled by a machine: FastAPI's schema snapshot → a typed fetch client + TanStack Query helpers. The frontend will never hand-write a request type; CI will fail anyone who changes the API and forgets to regenerate.

**Why a snapshot file, not a live URL:** generating from a committed `openapi.json` keeps CI hermetic (no server to boot) and turns the schema itself into a reviewable diff in every PR: you _see_ the API change next to the code change.

### 1.9.1 Humane operation ids + the export script

**Layer 2 · Guide:** by default FastAPI mints operation ids like `me_api_me_get`, which become hook names like `useMeApiMeGetQuery`: legal, hideous. A `generate_unique_id_function` returning `route.name` (= the function name) fixes it, at the price of one rule: **endpoint function names must be unique across the whole app.** You've been following it accidentally; now it's law.

**Layer 3 · Exact assembly:** in `src/flrc/main.py`:

```python
from fastapi.routing import APIRoute


def _operation_id(route: APIRoute) -> str:
    return route.name
```

…and pass `generate_unique_id_function=_operation_id` in the `FastAPI(...)` call. Then `apps/backend/scripts/export_openapi.py`:

```python
import json
from pathlib import Path

from flrc.main import create_app

out = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
print(f"wrote {out}")
```

Add to `apps/backend/package.json` scripts: `"generate": "uv run python scripts/export_openapi.py"`.

### 1.9.2 The generator

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/api-client add @hey-api/client-fetch @tanstack/react-query
pnpm --filter @flrc/api-client add -D @hey-api/openapi-ts
```

`packages/api-client/openapi-ts.config.ts`:

```ts
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "openapi.json",
  output: "src",
  plugins: ["@hey-api/client-fetch", "@tanstack/react-query"],
});
```

Scripts in `packages/api-client/package.json`: `"generate": "openapi-ts"`. Root `package.json`: change the generate script to run them in order:

```json
"generate": "pnpm --filter @flrc/backend run generate && pnpm --filter @flrc/api-client run generate"
```

Run `pnpm generate`, then open `packages/api-client/src/` and **read what appeared**: a `types.gen.ts` (your Pydantic models as TS), an `sdk.gen.ts` (one typed function per endpoint), a client file, and a TanStack file exporting things like `meOptions()`. Make `src/index.ts` re-export exactly the files that exist (names shift slightly between hey-api versions; two minutes of looking beats any guide):

```ts
export * from "./types.gen";
export * from "./sdk.gen";
export * from "./@tanstack/react-query.gen";
export { client } from "./client.gen";
```

Commit everything generated, including `openapi.json`.

**Check:** run `pnpm generate` a second time → `git status` clean (determinism proven); `pnpm --filter @flrc/api-client typecheck` green; grep the generated types for `MeOut` and admire your Pydantic model speaking TypeScript.

**If it breaks:** plugin name errors → hey-api reshuffles plugin ids occasionally; their Getting Started page is a 2-minute read and authoritative over this handbook. Empty-looking output → the config's `input` path is relative to the package folder; run generate _from_ the package (the script does).

**Docs:** heyapi.dev. **Why deeper:** ARCH §4/1.9; the no-diff CI check lands in 1.11 and completes this contract.

Commit: `feat: generated api client`.

## Step 1.10: The frontend shells (proxy, Tailwind, router, i18n, login)

Build everything in `apps/teacher` first; 1.10.6 turns the admin app into a 30-minute echo.

### 1.10.1 The dev proxy (do this before anything renders)

**What / Why:** Vite forwards `/api/*` to FastAPI so the browser sees one origin, the local twin of the Vercel rewrite. From this moment, the SPA only ever calls relative `/api/...` paths; dev and prod become byte-identical to the browser, and the whole cookie story from 1.7 holds.

**Layer 3 · Exact assembly:** `apps/teacher/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
```

**Check:** with the API running, `curl localhost:5173/api/healthz` (yes, 5173) answers: Vite is now your reverse proxy.

### 1.10.2 Tailwind v4 + shadcn/ui

**What we're building:** styling that works across the monorepo: Tailwind v4 through its Vite plugin, shadcn components generated into `packages/ui` so both apps share them.

**Why the ceremony around shadcn:** it _copies source into your repo_ rather than installing a dependency, and in a monorepo the right home for that source is the shared package: set up once, imported twice.

**Layer 2 · Guide:** Tailwind v4 = two moves: the Vite plugin, and `@import "tailwindcss";` at the top of your CSS (no `tailwind.config.js`; v4 discovers classes by following the module graph, which is exactly why source-consumed `packages/ui` Just Works). For shadcn, their **Monorepo** docs page is the authority: it wants a `components.json` in the app _and_ in `packages/ui`, with aliases pointing component output at the package. Mirror their template with the `@flrc/ui` name.

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/teacher add tailwindcss @tailwindcss/vite
```

Add `tailwindcss()` to the Vite plugins array (import from `@tailwindcss/vite`). Replace `src/index.css` contents with:

```css
@import "tailwindcss";
```

Prepare `packages/ui` to host components; its `package.json` gains React as a peer plus subpath exports:

```json
{
  "name": "@flrc/ui",
  "private": true,
  "exports": {
    ".": "./src/index.tsx",
    "./components/*": "./src/components/*.tsx",
    "./lib/*": "./src/lib/*.ts"
  },
  "peerDependencies": { "react": "^19.0.0", "react-dom": "^19.0.0" },
  "devDependencies": { "@types/react": "^19.0.0", "typescript": "^5.6.0" },
  "scripts": { "lint": "eslint src", "typecheck": "tsc --noEmit" }
}
```

Then follow ui.shadcn.com/docs/monorepo (ten minutes) to run `pnpm dlx shadcn@latest init` from `apps/teacher`, answering so that components land in `packages/ui/src/components` under the `@flrc/ui` alias, and add your first component:

```bash
pnpm dlx shadcn@latest add button
```

**Check:** in `App.tsx`, `import { Button } from '@flrc/ui/components/button'` renders a styled button via the dev server. If Tailwind classes inside the package have no effect, your `@import "tailwindcss"` line is missing or the Vite plugin isn't registered.

**If it breaks:** shadcn's CLI questions drift between versions; when in doubt, answer to match their monorepo template's file layout, then verify by reading where `button.tsx` actually landed and fixing `components.json` aliases to agree. This is a config negotiation, not a correctness problem.

### 1.10.3 TanStack Router + Query + the auth guard

**What we're building:** file-based routes (`/login`, and a `_auth` layout that walls off everything else), a Query client, and a `beforeLoad` that turns 401s into redirects.

**Why `beforeLoad` + `ensureQueryData`:** the guard runs _before_ any protected component renders, and `ensureQueryData` means the `/api/me` result is fetched once and cached; the dashboard reads the same cache entry for free. One request, two consumers, zero flicker.

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/teacher add @tanstack/react-router @tanstack/react-query @flrc/api-client@workspace:* @flrc/i18n@workspace:*
pnpm --filter @flrc/teacher add -D @tanstack/router-plugin
```

Vite plugin order matters; router plugin first:

```ts
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
// plugins: [TanStackRouterVite(), react(), tailwindcss()]
```

`src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { client } from "@flrc/api-client";
import { initI18n } from "@flrc/i18n";
import { routeTree } from "./routeTree.gen";
import "./index.css";

client.setConfig({ baseUrl: "" }); // relative /api; the proxy is the origin
initI18n();

const queryClient = new QueryClient();
const router = createRouter({ routeTree, context: { queryClient } });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
```

`src/routes/__root.tsx`:

```tsx
import type { QueryClient } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: () => <Outlet />,
});
```

`src/routes/_auth.tsx`, the wall:

```tsx
import { Outlet, createFileRoute, redirect } from "@tanstack/react-router";
import { meOptions } from "@flrc/api-client";

export const Route = createFileRoute("/_auth")({
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData(meOptions());
      return { user };
    } catch {
      throw redirect({ to: "/login" });
    }
  },
  component: () => <Outlet />,
});
```

(`meOptions` is the generated name for your `me` operation; if your hey-api version names it differently, the generated TanStack file is one `grep me` away; trust the file over the handbook.)

`src/routes/login.tsx` and `src/routes/_auth/index.tsx`: the next step supplies their content alongside i18n. Run the dev server once now: the router plugin writes `src/routeTree.gen.ts` (gitignore it or commit it, but pick one and be consistent; committing is simpler).

### 1.10.4 The i18n package + the two pages

**What we're building:** `@flrc/i18n` initialized with four languages, and the first two screens written under the house rule that starts _now_: **no user-visible string literal in JSX, ever**; everything goes through `t()`.

**Why now and not "when we translate":** the rule costs nothing per component and saves a legendary refactor; §4.4 becomes translation work instead of surgery. The API's error _codes_ land here too: `?error=wrong_domain` becomes a Turkish sentence in the bundle, a German one next year, and the backend never knew.

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/i18n add i18next react-i18next i18next-browser-languagedetector
mkdir -p packages/i18n/src/locales
```

`packages/i18n/src/locales/tr.json`:

```json
{
  "appName": "FL-ReportCard",
  "greeting": "Merhaba, {{name}}",
  "goToAdmin": "Yönetim paneline geç",
  "logout": "Çıkış yap",
  "auth": {
    "signIn": "Google ile giriş yap",
    "errors": {
      "wrong_domain": "Lütfen okul hesabınızla giriş yapın.",
      "not_registered": "Bu e-posta sisteme kayıtlı değil. Yöneticinizle görüşün.",
      "google_error": "Google girişinde bir sorun oluştu. Lütfen tekrar deneyin."
    }
  }
}
```

`en.json` mirrors it in English (write it now); create `de.json` and `fr.json` as copies of `en.json` with a `"_TODO": "translate"` first key; §4.4 pays this debt on purpose.

`packages/i18n/src/index.ts`:

```ts
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import de from "./locales/de.json";
import en from "./locales/en.json";
import fr from "./locales/fr.json";
import tr from "./locales/tr.json";

export const initI18n = () =>
  i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: {
        tr: { common: tr },
        en: { common: en },
        de: { common: de },
        fr: { common: fr },
      },
      defaultNS: "common",
      fallbackLng: "tr",
      interpolation: { escapeValue: false },
    });

export { default as i18n } from "i18next";
```

(The teacher app needs `react-i18next` resolvable too: `pnpm --filter @flrc/teacher add react-i18next i18next`.)

`src/routes/login.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@flrc/ui/components/button";

export const Route = createFileRoute("/login")({
  validateSearch: (s): { error?: string } => ({
    error: typeof s.error === "string" ? s.error : undefined,
  }),
  component: LoginPage,
});

const LoginPage = () => {
  const { t } = useTranslation();
  const { error } = Route.useSearch();
  return (
    <main className="grid min-h-svh place-items-center">
      <div className="space-y-4 text-center">
        <h1 className="text-2xl font-semibold">{t("appName")}</h1>
        {error && <p className="text-red-600">{t(`auth.errors.${error}`)}</p>}
        <Button onClick={() => (window.location.href = "/api/auth/login")}>
          {t("auth.signIn")}
        </Button>
      </div>
    </main>
  );
};
```

`src/routes/_auth/index.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { i18n } from "@flrc/i18n";
import { Button } from "@flrc/ui/components/button";

export const Route = createFileRoute("/_auth/")({
  component: Dashboard,
});

const Dashboard = () => {
  const { user } = Route.useRouteContext();
  const { t } = useTranslation();
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  };
  return (
    <main className="space-y-4 p-8">
      <h1 className="text-xl">{t("greeting", { name: user.full_name })}</h1>
      <div className="flex gap-2">
        {(["tr", "en", "de", "fr"] as const).map((lng) => (
          <Button key={lng} variant="outline" size="sm" onClick={() => i18n.changeLanguage(lng)}>
            {lng.toUpperCase()}
          </Button>
        ))}
      </div>
      {user.is_admin && (
        <a
          className="underline"
          href={import.meta.env.VITE_ADMIN_URL ?? "http://localhost:5174/admin"}
        >
          {t("goToAdmin")}
        </a>
      )}
      <Button variant="secondary" onClick={logout}>
        {t("logout")}
      </Button>
    </main>
  );
};
```

### 1.10.5 The full-loop check (the Phase-1 money moment, locally)

Start `pnpm dev`; it waits for Postgres and Redis to become healthy, then starts the backend and both
SPAs. In a fresh browser profile: `localhost:5173` → bounced to `/login` → sign in with the school
account → dashboard greets you by name → refresh (still in) → switch language (greeting flips) →
logout (bounced out) → sign in with a personal Gmail → the _Turkish sentence_ for `wrong_domain`.
Every arrow in that sequence is a subsystem proving itself.

**If it breaks:** raw keys like `auth.errors.wrong_domain` on screen → `initI18n()` isn't called before render, or the JSON path doesn't match. Guard loops forever → `meOptions()` is hitting `:5173/api/me` (good) but the API isn't running, or the cookie died (check devtools → Network → the `me` request's cookie header). `routeTree.gen` import error → run dev once; the plugin generates it.

### 1.10.6 The admin app + its production-safe base path

**What we're building:** `apps/admin` as an echo of the teacher shell. It runs on its own Vite port
locally but owns `/admin` in the public deployment, so its static assets and client routes must be
base-path-safe from the beginning.

**Why one login surface:** authentication belongs to the teacher app. A logged-out visitor who
types `/admin` goes to the normal teacher login, signs in, lands on the teacher dashboard, and, if
authorized, uses the “Go to admin panel” link. The admin SPA has no login page and OAuth has no
admin return target. Local development still has two origins, so the Origin middleware must trust
both even though production composes them under one origin.

**Layer 3 · Exact assembly (frontend):** repeat the authenticated shell in `apps/admin`, but do not
create `routes/login.tsx`. Use Vite `base: "/admin/"` and `server.port: 5174`; give TanStack Router
`basepath: "/admin"`. In the admin `_auth` guard, `/api/me` failure redirects externally to
`${VITE_TEACHER_URL}/login`, an authenticated user without `is_admin` redirects to
`VITE_TEACHER_URL`, and only an admin returns `{ user }`. Admin logout also returns to the shared
teacher login. The teacher dashboard shows its admin link only when `user.is_admin`; its local
default is `http://localhost:5174/admin`.

**Layer 3 · Exact assembly (backend):** (1) `config.py` gains
`admin_origin: str = "http://localhost:5174"` (and `.env.example` follows). (2) `middleware.py`: build
`allowed_origins = {settings.frontend_origin, settings.admin_origin}` and check `origin in
allowed_origins` in the fallback branch. (3) `src/flrc/modules/auth/router.py` always uses the
teacher origin for its callback, errors, and success landing:

```python
redirect_uri = f"{settings.frontend_origin}/api/auth/callback"
```

Successful authentication redirects to `settings.frontend_origin`; every machine-coded error
redirects to `${settings.frontend_origin}/login?error=<code>`.

**Check:** logged out at `localhost:5174/admin` → redirected to `localhost:5173/login` → Google
returns through `localhost:5173/api/auth/callback` → teacher dashboard. An admin sees the link and
opens `localhost:5174/admin`; a teacher who types that URL returns to the teacher dashboard.
Logout inside admin returns to the teacher login. A POST logout from 5174 must still pass the
Origin middleware.

Commit: `feat(web): shells, i18n, auth loop, admin origin`. **Docs:** tanstack.com/router (file-based routing guide) · ui.shadcn.com/docs/monorepo · react.i18next.com. **Why deeper:** ARCH §4/1.10 and the site-vs-origin lesson.

## Step 1.11: Deploy the skeleton + CI (it ships today)

### 1.11.1 Neon

**What / Why:** the production database, EU-Frankfurt for the KVKK posture (ARCH §8), with the pooled/direct split you've been prepping for since 1.5.

**Layer 3 · Exact assembly:** neon.com → new project `flrc`, region **AWS eu-central-1 (Frankfurt)**, Postgres 18. From the dashboard copy **two** connection strings: the pooled one (host contains `-pooler`) and the direct one. Convert both for asyncpg: scheme `postgresql+asyncpg://` and, because asyncpg doesn't speak `sslmode`, change the query string to `ssl=require`:

```
postgresql+asyncpg://user:pass@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?ssl=require
```

One code amendment while you're here: the seed CLI's sync engine must translate both the driver _and_ the SSL knob (psycopg wants `sslmode`, asyncpg wants `ssl`; dialect trivia that costs an hour if unlearned). In `src/flrc/cli.py`:

```python
def sync_engine():
    url = settings.database_url.replace("+asyncpg", "+psycopg").replace(
        "ssl=require", "sslmode=require"
    )
    return create_engine(url, pool_pre_ping=True)
```

Migrate and seed the cloud (fake data only; this is the public demo):

```bash
FLRC_MIGRATIONS_URL="<direct-url>" uv run alembic upgrade head
DATABASE_URL="<pooled-url>" uv run flrc seed --my-email <your-school-email>
```

Also create a `dev` branch in Neon's UI for future experiments; `main` is sacred.

**Check:** Neon's table view shows 8 tables; `select count(*) from students` → 720.

### 1.11.2 Upstash

**Layer 3:** console.upstash.com → create Redis → region EU (Frankfurt/Ireland, nearest to Render's Frankfurt) → copy the **TLS** URL (`rediss://…`). That's it until env-var time.

### 1.11.3 Render (plus one Dockerfile fix)

**What / Why:** the API goes live as a Docker web service; the committed `infra/render/render.yaml` blueprint makes the setup reproducible: infrastructure as code, and the school-side redeploy story.

**The startup command:** the Dockerfile runs `bin/start-api.sh`. In `ENV=demo`, this script first
applies pending Alembic migrations through `DATABASE_URL_DIRECT`, then starts Uvicorn with trusted
forwarded headers so HTTPS cookies and Authlib work behind Render and Vercel. Leave Render's
Docker Command override empty so it uses this default:

```dockerfile
CMD ["sh", "./bin/start-api.sh"]
```

**Layer 3 · Exact assembly:** the following is the synthetic demo profile. The committed
`infra/render/render.yaml` is now the managed school profile (`ENV=school`) and requires the
Cloudflare gateway described in `docs/SECURITY.md`; use `ENV=demo` for this Vercel demo service:

```yaml
services:
  - type: web
    name: flrc-api
    runtime: docker
    rootDir: apps/backend
    plan: free
    healthCheckPath: /api/healthz
    envVars:
      - key: ENV
        value: demo
      - key: DATABASE_URL
        sync: false
      - key: DATABASE_URL_DIRECT
        sync: false
      - key: REDIS_URL
        sync: false
      - key: SESSION_SECRET
        sync: false
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: ALLOWED_GOOGLE_DOMAIN
        sync: false
      - key: FRONTEND_ORIGIN
        sync: false
      - key: ADMIN_ORIGIN
        sync: false
```

dashboard.render.com → New → **Blueprint** → your repo → it reads the file; fill every
`sync: false` secret (`SESSION_SECRET`: `openssl rand -base64 48`; the origins are finalized after
the Vercel gateway below). Deploy.

**Check:** `curl -i https://flrc-api.onrender.com/api/healthz` → 204 with an empty body. Then
watch it sleep: wait 20 minutes, curl again, feel the cold start; that's the free tier you
budgeted for (ARCH §2.2).

**If it breaks:** blueprint rejects `runtime` → older accounts want `env: docker`; flip the key. Build can't find `uv.lock` → `rootDir` missing. Healthcheck failing forever → the CMD isn't honoring `$PORT`.

### 1.11.4 Vercel: two app projects behind one public gateway

**Current checkout amendment (ADR-064):** the demo now runs as one Vercel project rooted at
`infra/vercel`. Its workspace package `@flrc/demo-web` builds both apps and assembles the teacher
output at `/` and the admin output at `/admin/`; its `vercel.json` rewrites `/api/*` to Render and
sets `trailingSlash: false`. Production builds link the panels to `/admin/` and `/`, so the
`VITE_ADMIN_URL` and `VITE_TEACHER_URL` variables below are only for layouts with two origins. The
three-project assembly that follows is the original learning sequence; do not recreate it.

**What / Why:** teacher and admin stay independently deployed, but the browser sees one origin:

```text
https://flrc.suatsulun.com/        teacher
https://flrc.suatsulun.com/admin   admin
https://flrc.suatsulun.com/api/*   Render API through the gateway
```

One host-only `flrc_session` cookie now covers both panels without a broad cookie `Domain`.

**Layer 3 · Exact assembly (app projects):** create the teacher and admin Vercel projects from the
same repo with Root Directories `apps/teacher` and `apps/admin`. Keep the SPA fallbacks in each
app's `vercel.json`. Confirm the admin app builds with Vite base `/admin/` and TanStack Router
basepath `/admin`. Record both stable production `*.vercel.app` deployment domains; these are
gateway upstreams, not user-facing URLs.

Set frontend cross-link environment variables on both app projects:

```text
teacher: VITE_ADMIN_URL=https://flrc.suatsulun.com/admin
admin:   VITE_TEACHER_URL=https://flrc.suatsulun.com
```

**Layer 3 · Exact assembly (gateway):** add `infra/vercel-gateway/vercel.json` with the stable
app/API domains:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://flrc-api.onrender.com/api/:path*"
    },
    {
      "source": "/admin",
      "destination": "https://flrc-admin.vercel.app/"
    },
    {
      "source": "/admin/:path*",
      "destination": "https://flrc-admin.vercel.app/:path*"
    },
    {
      "source": "/",
      "destination": "https://flrc-teacher.vercel.app/"
    },
    {
      "source": "/:path*",
      "destination": "https://flrc-teacher.vercel.app/:path*"
    }
  ]
}
```

Create a third Vercel project with Root Directory `infra/vercel-gateway` and attach only
`flrc.suatsulun.com` to it. In Cloudflare DNS, point `flrc` to the Vercel target shown for this
gateway project. Do not attach the custom domain to either upstream app project.

The gateway also commits `infra/vercel-gateway/public/gateway.txt` as a build marker because
Vercel's `Other` framework preset requires the configured `public` output directory to exist. Do
not put an `index.html` in this directory: Vercel can serve that filesystem match for `/` before
the external teacher rewrite. The marker keeps the output directory non-empty without shadowing a
browser route.

Close the auth loop:

```text
Render FRONTEND_ORIGIN=https://flrc.suatsulun.com
Render ADMIN_ORIGIN=https://flrc.suatsulun.com
Google callback=https://flrc.suatsulun.com/api/auth/callback
```

Remove the old teacher/admin custom-domain callback URIs after the new loop passes. Keep the
Vercel preview domains only for deployment diagnostics; separate preview hosts do not promise a
shared login.

**Check (the deployed money moment):** in a fresh browser profile, open `/admin` and confirm it
redirects to `/login`. Sign in, land on the teacher dashboard, use the admin-only link, and confirm
`/api/me` succeeds without another Google redirect. Log out from admin, then revisit `/`; it must
show the teacher login page. DevTools must show one host-only `flrc_session` cookie for
`flrc.suatsulun.com` with no `Domain` attribute.

**If it breaks:** admin HTML loads but assets return HTML → the admin Vite base or `/admin/*`
prefix-stripping rewrite is wrong. `/admin` does not send an anonymous user to `/login` → the admin
guard or `VITE_TEACHER_URL` is wrong. OAuth state mismatch → login and callback used different
public hosts. Teacher appears at `/admin` → the teacher catch-all was placed before the admin
rules. A POST returns `bad_origin` → Render's two origin settings are not both the exact public
origin.

### 1.11.5 CI

**What / Why:** every PR proves lint, types, tests, and the API↔client contract: the robot that makes solo development safe.

**Layer 3 · Exact assembly:** `.github/workflows/ci.yml`:

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

jobs:
  js:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: .node-version
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run lint typecheck build

  python:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/backend
    services:
      postgres:
        image: postgres:18-alpine
        env:
          POSTGRES_USER: flrc
          POSTGRES_PASSWORD: flrc
          POSTGRES_DB: flrc
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U flrc"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
      redis:
        image: redis:8-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy src/flrc
      - run: PGPASSWORD=flrc psql -h localhost -U flrc -d postgres -c "create database flrc_test;"
      - run: uv run pytest -q

  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: .node-version
          cache: pnpm
      - uses: astral-sh/setup-uv@v5
      - run: pnpm install --frozen-lockfile
      - run: uv sync --frozen
        working-directory: apps/backend
      - run: pnpm generate
      - run: git diff --exit-code packages/api-client
```

Add `.github/dependabot.yml` for npm, Python, Docker, and GitHub Actions. Add the security
workflow with CodeQL's `security-extended` queries and GitHub's dependency-review action. Mark
the normal CI and security checks as required before merging to `main`.

GitHub Advanced Security is not available on every private-repository plan. Keep the independent
locked-dependency audit required everywhere, and gate CodeQL/dependency review on either a public
repository or the repository variable `GHAS_ENABLED=true`. Leave the variable unset until the
feature is actually enabled; unsupported scanners should skip, not make every PR falsely red.

**Check:** open a trivial PR → normal CI and the locked-dependency audit are green; GHAS-only jobs
are green when enabled or skipped when unavailable. Then sabotage on a branch: change `/api/me`'s
response model without regenerating → the **contract** job fails exactly as designed.

### 1.11.6 Keep-alive (the cold-start budget, executed)

**Layer 3 · Exact assembly:** `.github/workflows/keepalive.yml`:

```yaml
name: keepalive
on:
  schedule:
    - cron: "*/10 5-14 * * 1-5" # every 10 min, 05:00-14:59 UTC, weekdays = Turkish school hours
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -fsS https://flrc-api.onrender.com/api/healthz
```

The math this encodes lives in ARCH §2.2 (~480 of 750 shared hours once the worker exists). Outside the window, the first request eats the cold start; say so honestly in the README and in a small footer note on the login page (a `t()` key, naturally).

### Phase 1 exit checklist

- ✅ Deployed login works with your real school account, on your phone, through the proxy
- ✅ A personal Gmail gets the translated `wrong_domain` message
- ✅ CI: js + python + contract all green on a PR; contract job proven to fail on drift
- ✅ `infra/render/render.yaml`, gateway config, CI/security workflows, and
  `.github/dependabot.yml` committed
- ✅ `uv run pytest` locally: migrations test + guard matrix green
- ✅ DECISIONS.md holds at least: monorepo shape · proxy topology & the never-see-Render rule · sessions-not-JWT · text+CHECK enums · pooled-vs-direct · operation-id naming rule

```bash
git tag phase-1 && git push --tags
```

Take the evening off. You have a deployed, authenticated, contract-tested, bilingual-ready skeleton; most "learn full-stack" journeys never reach this sentence.

---

# Part V. Phase 2: The grade grid

**Phase goal:** two teachers edit 5/A simultaneously without ever silently overwriting each other; foreign columns demand (and grant) one-hour permission; undo restores a batch; the admin reads everything in the audit log; and a phone gets a layout thumbs can actually use. This phase is where the app earns its existence; budget the full two and a half weeks and enjoy it.

**One structural note before 2.1:** all five Phase-2 tables (column definitions, grade values, save batches, audit entries, override grants) arrive in **one migration** at the start, because ARCH §3.4-3.5 designed them as one interlocking mechanism: the save path writes audit rows, audit rows power undo, grants annotate audit. Creating them together also means the columns API can implement its delete-or-disable branch honestly from day one instead of carrying a TODO.

## Step 2.1: Column definitions (schema, API, seed, editor)

**Current school rules (ADR-060, amended by pending ADR-063):** Grade 4 German/French accept
`scale3` and `text`, never numeric scores or averages. Primary English and all configured L2
programmes retain comments. Grades 5-8 English have eleven default scores and no opinion field.
`academics/programme.py` supplies shared checks for create/update, seed, copy and rollover.

Migration `f4b82d903e61` historically disabled grade-4 L2 non-scale columns in non-archived years.
`7d26cb91a540` later supplied missing comment definitions without reactivating disabled ones.
Pending migration `82a91f4c6d30` retires middle-English text definitions across years while
preserving definitions, values, versions and audits. Its downgrade does not reactivate them.
Live/archive/history/report projections omit the retired fields; audit and workbook exports
retain underlying history. These are successive migrations, not reasons to edit applied files.

### 2.1.1 The Phase-2 schema (one migration, five tables)

**What we're building:** the tables from ARCH §3.3-3.5, exactly as designed: columns as _data_, one row per student × column, batches, audit, grants.

**Why the shapes are what they are (the 60-second recap):** a `column_definition` row is what the admin's + button creates; no migration, ever (invariant #2). A `grade_value` is unique per (student, column) and knows nothing about classes (invariant #1); that ignorance is why moved students keep grades. `version` is the optimistic-concurrency counter (invariant #4). Audit rows store both old and new values so undo is just the audit log replayed backwards; `old_existed` distinguishes "was 0" from "was empty", a distinction schools care about. Grants live in Postgres, not Redis-with-TTL, because _who had permission when_ is itself audit data (ARCH §3.5).

**Layer 1 · Nudge:** five models in `models.py`, JSONB for the four-language labels, CHECKs everywhere a bare string could lie, then one autogenerate you actually read.

**Layer 3 · Exact assembly:** append to `src/flrc/db/models.py` (new imports: `SmallInteger`, `datetime` from datetime, and `from sqlalchemy.dialects.postgresql import JSONB`):

```python
class ColumnDefinition(TimestampMixin, Base):
    __tablename__ = "column_definitions"
    __table_args__ = (
        CheckConstraint("grade_level BETWEEN 1 AND 8", name="grade_level_valid"),
        CheckConstraint("subject IN ('english','german','french')", name="subject_valid"),
        CheckConstraint("value_type IN ('score','scale3','text')", name="value_type_valid"),
        CheckConstraint(
            "owner_role IN ('main','skills','german','french')", name="owner_role_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    grade_level: Mapped[int]
    subject: Mapped[str]
    value_type: Mapped[str]
    owner_role: Mapped[str]
    labels: Mapped[dict[str, str]] = mapped_column(JSONB)
    group_labels: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    counts_in_average: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class GradeValue(TimestampMixin, Base):
    __tablename__ = "grade_values"
    __table_args__ = (
        UniqueConstraint("student_id", "column_definition_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("scale BETWEEN 1 AND 3", name="scale_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    column_definition_id: Mapped[int] = mapped_column(
        ForeignKey("column_definitions.id"), index=True
    )
    score: Mapped[int | None] = mapped_column(SmallInteger)
    scale: Mapped[int | None] = mapped_column(SmallInteger)
    text_value: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SaveBatch(TimestampMixin, Base):
    __tablename__ = "save_batches"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    is_undo: Mapped[bool] = mapped_column(default=False)
    undone: Mapped[bool] = mapped_column(default=False)


class AuditEntry(TimestampMixin, Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("save_batches.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    column_definition_id: Mapped[int] = mapped_column(ForeignKey("column_definitions.id"))
    old_existed: Mapped[bool]
    old_score: Mapped[int | None] = mapped_column(SmallInteger)
    old_scale: Mapped[int | None] = mapped_column(SmallInteger)
    old_text: Mapped[str | None]
    new_score: Mapped[int | None] = mapped_column(SmallInteger)
    new_scale: Mapped[int | None] = mapped_column(SmallInteger)
    new_text: Mapped[str | None]
    forced: Mapped[bool] = mapped_column(default=False)
    via_grant_id: Mapped[int | None] = mapped_column(ForeignKey("override_grants.id"))


class OverrideGrant(TimestampMixin, Base):
    __tablename__ = "override_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "class_id", "role"),
        CheckConstraint("role IN ('main','skills','german','french')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"))
    role: Mapped[str]
    expires_at: Mapped[datetime]
```

```bash
uv run alembic revision --autogenerate -m "grid tables"
```

Read the diff against: 5 create_table · the composite unique on grade_values · CHECKs named `ck_grade_values_score_range` etc. · the index on `column_definition_id` · JSONB columns. Then `uv run alembic upgrade head` (locally _and_, with `FLRC_MIGRATIONS_URL`, against Neon).

**Check:** `\d grade_values` shows the unique constraint and both range CHECKs. **If it breaks:** autogenerate wrote `sa.JSON` instead of JSONB → your import is `sqlalchemy.JSON`, not the postgresql dialect one.

### 2.1.2 The columns API

**What we're building:** admin-only CRUD plus two operations CRUD doesn't have: **reorder** (the up/down arrows) and **copy** (September's sanity: duplicating a column set to another grade or the twin language).

**Why the delete branch has two outcomes:** a column with grades is _history_; the minus button hides it (`is_active=false`) instead of destroying data, and tells the admin which case happened. Cascade-deleting grades from a UI button is a résumé-ending feature (ARCH §3.3).

**Layer 1 · Nudge:** one router; every write depends on `require_admin` _and_ `writable_semester` (column edits target the open semester only, per your spec); server-side rule: an L2 column must be owned by its own language's teacher.

**Layer 3 · Exact assembly:** `src/flrc/modules/academics/columns.py`:

```python
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import require_admin, writable_semester
from flrc.db.models import ColumnDefinition, GradeValue, Semester, User
from flrc.db.session import get_session

router = APIRouter(prefix="/columns", tags=["columns"])

Subject = Literal["english", "german", "french"]
Role = Literal["main", "skills", "german", "french"]
ValueType = Literal["score", "scale3", "text"]


class LabelSet(BaseModel):
    tr: str = Field(min_length=1)
    en: str = ""
    de: str = ""
    fr: str = ""


class ColumnCreate(BaseModel):
    grade_level: int = Field(ge=1, le=8)
    subject: Subject
    value_type: ValueType
    owner_role: Role
    labels: LabelSet
    group_labels: LabelSet | None = None
    counts_in_average: bool = False


class ColumnPatch(BaseModel):
    labels: LabelSet | None = None
    group_labels: LabelSet | None = None
    counts_in_average: bool | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade_level: int
    subject: str
    value_type: str
    owner_role: str
    labels: LabelSet
    group_labels: LabelSet | None
    counts_in_average: bool
    position: int
    is_active: bool


class DeleteResult(BaseModel):
    deleted: bool
    disabled: bool


class ReorderBody(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class CopyBody(BaseModel):
    source_grade_level: int = Field(ge=1, le=8)
    source_subject: Subject
    target_grade_level: int = Field(ge=1, le=8)
    target_subject: Subject


def _check_owner_rule(subject: str, owner_role: str) -> None:
    is_l2 = subject in ("german", "french")
    if is_l2 and owner_role != subject:
        raise HTTPException(422, {"code": "owner_subject_mismatch"})
    if not is_l2 and owner_role not in ("main", "skills"):
        raise HTTPException(422, {"code": "owner_subject_mismatch"})


@router.get("")
async def list_columns(
    grade_level: int,
    subject: Subject,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> list[ColumnOut]:
    result = await db.execute(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.semester_id == semester.id,
            ColumnDefinition.grade_level == grade_level,
            ColumnDefinition.subject == subject,
        )
        .order_by(ColumnDefinition.position)
    )
    return [ColumnOut.model_validate(c) for c in result.scalars()]


@router.post("", status_code=201)
async def create_column(
    body: ColumnCreate,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ColumnOut:
    _check_owner_rule(body.subject, body.owner_role)
    max_pos = (
        await db.execute(
            select(func.coalesce(func.max(ColumnDefinition.position), 0)).where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == body.grade_level,
                ColumnDefinition.subject == body.subject,
            )
        )
    ).scalar_one()
    column = ColumnDefinition(
        semester_id=semester.id, position=max_pos + 1, **body.model_dump()
    )
    db.add(column)
    await db.commit()
    await db.refresh(column)
    return ColumnOut.model_validate(column)


@router.patch("/{column_id}")
async def update_column(
    column_id: int,
    body: ColumnPatch,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ColumnOut:
    column = await db.get(ColumnDefinition, column_id)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(column, key, value)
    await db.commit()
    await db.refresh(column)
    return ColumnOut.model_validate(column)


@router.delete("/{column_id}")
async def delete_column(
    column_id: int,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> DeleteResult:
    column = await db.get(ColumnDefinition, column_id)
    if column is None or column.semester_id != semester.id:
        raise HTTPException(404, {"code": "unknown_column"})
    has_data = (
        await db.execute(
            select(func.count())
            .select_from(GradeValue)
            .where(GradeValue.column_definition_id == column_id)
        )
    ).scalar_one() > 0
    if has_data:
        column.is_active = False
        await db.commit()
        return DeleteResult(deleted=False, disabled=True)
    await db.delete(column)
    await db.commit()
    return DeleteResult(deleted=True, disabled=False)


@router.post("/reorder")
async def reorder_columns(
    body: ReorderBody,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    result = await db.execute(
        select(ColumnDefinition).where(
            ColumnDefinition.id.in_(body.ordered_ids),
            ColumnDefinition.semester_id == semester.id,
        )
    )
    columns = {c.id: c for c in result.scalars()}
    if set(columns) != set(body.ordered_ids):
        raise HTTPException(422, {"code": "reorder_mismatch"})
    for pos, cid in enumerate(body.ordered_ids, start=1):
        columns[cid].position = pos
    await db.commit()
    return {"ok": True}


@router.post("/copy")
async def copy_columns(
    body: CopyBody,
    semester: Semester = Depends(writable_semester),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    same_family = (body.source_subject == "english") == (body.target_subject == "english")
    if not same_family:
        raise HTTPException(422, {"code": "copy_family_mismatch"})
    target_count = (
        await db.execute(
            select(func.count())
            .select_from(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == semester.id,
                ColumnDefinition.grade_level == body.target_grade_level,
                ColumnDefinition.subject == body.target_subject,
            )
        )
    ).scalar_one()
    if target_count > 0:
        raise HTTPException(409, {"code": "target_not_empty"})
    result = await db.execute(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.semester_id == semester.id,
            ColumnDefinition.grade_level == body.source_grade_level,
            ColumnDefinition.subject == body.source_subject,
        )
        .order_by(ColumnDefinition.position)
    )
    sources = list(result.scalars())
    is_l2_target = body.target_subject in ("german", "french")
    for src in sources:
        db.add(
            ColumnDefinition(
                semester_id=semester.id,
                grade_level=body.target_grade_level,
                subject=body.target_subject,
                value_type=src.value_type,
                owner_role=body.target_subject if is_l2_target else src.owner_role,
                labels=src.labels,
                group_labels=src.group_labels,
                counts_in_average=src.counts_in_average,
                position=src.position,
            )
        )
    await db.commit()
    return {"copied": len(sources)}
```

Include the router in the factory, then (the reflex that never skips) `pnpm generate` and commit the client diff. From now on the handbook stops reminding you; the contract CI job does it instead.

**Check:** in `/api/docs` as no one, `GET /columns` → 401; the guard matrix in `test_guards.py` gains four rows for `/api/columns` (401 / teacher 403 / coordinator 403 / admin 200; the admin case needs the DB-backed harness from 2.6.3, so add the first three now and leave a TODO row).

### 2.1.3 Seed the real column sets

**Maintenance note:** the compact seed assembly below teaches column storage and predates the
expanded report rubrics. Current defaults are `ENGLISH_58`, `L2_SCORE_ITEMS`, `KARNE_ROWS`,
`PRIMARY_ROWS`, and `seed_columns()` in `src/flrc/cli.py`; do not replace them with this shorter
sample. The active programme rules in Step 2.1 apply before definitions are added. Never use
`flrc reset` against an existing school dataset.

**What / Why:** every `flrc reset && flrc seed` should yield playable grids: the real 5-8 English set (from ARCH §1.3 and your Card A photo), an L2 set for grades 4-8 in both languages, and the primary grouped-scale set for 1-4. Without this, every grid test starts with ten minutes of admin clicking.

**Why the seed uses semantic keys:** names such as `active_class_participation` make the
fixture readable and stable, but they are seed-code identifiers only. The values written to
`ColumnDefinition.labels` and `group_labels` contain the actual four-locale text because report
labels are school-configurable data. Do not put these strings in `packages/i18n`; that package owns
fixed UI chrome, while an administrator must be able to change a report label without a deploy.

**Layer 3 · Exact assembly:** add to `src/flrc/cli.py` (module level):

```python
REPORT_LABELS = {
    "progress_exam_1": {
        "tr": "Gelişim Sınavı 1", "en": "Progress Exam 1",
        "de": "Lernfortschrittstest 1", "fr": "Évaluation de progression 1",
    },
    "progress_exam_2": {
        "tr": "Gelişim Sınavı 2", "en": "Progress Exam 2",
        "de": "Lernfortschrittstest 2", "fr": "Évaluation de progression 2",
    },
    "quiz_1": {
        "tr": "Kısa Sınav 1", "en": "Quiz 1", "de": "Kurztest 1", "fr": "Quiz 1",
    },
    "quiz_2": {
        "tr": "Kısa Sınav 2", "en": "Quiz 2", "de": "Kurztest 2", "fr": "Quiz 2",
    },
    "reader_1": {
        "tr": "Okuma 1", "en": "Reader 1", "de": "Lektüre 1", "fr": "Lecture 1",
    },
    "reader_2": {
        "tr": "Okuma 2", "en": "Reader 2", "de": "Lektüre 2", "fr": "Lecture 2",
    },
    "homework_1": {
        "tr": "Ödev 1", "en": "Homework 1", "de": "Hausaufgabe 1", "fr": "Devoir 1",
    },
    "homework_2": {
        "tr": "Ödev 2", "en": "Homework 2", "de": "Hausaufgabe 2", "fr": "Devoir 2",
    },
    "highlights": {
        "tr": "Öne Çıkanlar", "en": "Highlights",
        "de": "Besondere Leistungen", "fr": "Points forts",
    },
    "book_reading": {
        "tr": "Kitap Okuma", "en": "Book Reading",
        "de": "Buchlektüre", "fr": "Lecture de livre",
    },
    "performance_1": {
        "tr": "Performans 1", "en": "Performance 1",
        "de": "Leistung 1", "fr": "Performance 1",
    },
    "performance_2": {
        "tr": "Performans 2", "en": "Performance 2",
        "de": "Leistung 2", "fr": "Performance 2",
    },
    "exam_1": {
        "tr": "Sınav 1", "en": "Exam 1", "de": "Prüfung 1", "fr": "Examen 1",
    },
    "exam_2": {
        "tr": "Sınav 2", "en": "Exam 2", "de": "Prüfung 2", "fr": "Examen 2",
    },
    "active_class_participation": {
        "tr": "Derse aktif olarak katılır", "en": "Participates actively in class",
        "de": "Nimmt aktiv am Unterricht teil", "fr": "Participe activement en classe",
    },
    "regular_homework": {
        "tr": "Ödevlerini düzenli yapar", "en": "Completes homework regularly",
        "de": "Erledigt regelmäßig die Hausaufgaben", "fr": "Fait régulièrement ses devoirs",
    },
    "uses_learned_vocabulary": {
        "tr": "Öğrendiği kelimeleri kullanır", "en": "Uses learned vocabulary",
        "de": "Verwendet den erlernten Wortschatz", "fr": "Utilise le vocabulaire appris",
    },
    "teacher_comments": {
        "tr": "Öğretmen görüşü", "en": "Teacher comments",
        "de": "Bemerkungen der Lehrkraft", "fr": "Commentaires de l’enseignant",
    },
    "willing_class_participation": {
        "tr": "Derslere istekli katılır", "en": "Participates willingly in lessons",
        "de": "Nimmt motiviert am Unterricht teil", "fr": "Participe volontiers aux cours",
    },
    "follows_instructions": {
        "tr": "Yönergeleri anlar ve uygular", "en": "Understands and follows instructions",
        "de": "Versteht und befolgt Anweisungen", "fr": "Comprend et suit les consignes",
    },
    "reads_simple_texts": {
        "tr": "Basit metinleri okur ve anlar", "en": "Reads and understands simple texts",
        "de": "Liest und versteht einfache Texte", "fr": "Lit et comprend des textes simples",
    },
    "oral_expression": {
        "tr": "Kendini sözlü ifade eder", "en": "Expresses themselves orally",
        "de": "Drückt sich mündlich aus", "fr": "S’exprime oralement",
    },
    "writes_learned_vocabulary": {
        "tr": "Öğrendiği kelimeleri yazar", "en": "Writes learned vocabulary",
        "de": "Schreibt den erlernten Wortschatz", "fr": "Écrit le vocabulaire appris",
    },
    "attitudes_toward_course": {
        "tr": "Derse Karşı Tutumlar", "en": "Attitudes Toward the Course",
        "de": "Einstellung zum Unterricht", "fr": "Attitudes envers le cours",
    },
    "listening_comprehension": {
        "tr": "Dinleme-Anlama", "en": "Listening Comprehension",
        "de": "Hörverstehen", "fr": "Compréhension orale",
    },
    "reading_comprehension": {
        "tr": "Okuma-Anlama", "en": "Reading Comprehension",
        "de": "Leseverstehen", "fr": "Compréhension écrite",
    },
    "speaking": {
        "tr": "Konuşma", "en": "Speaking", "de": "Sprechen", "fr": "Expression orale",
    },
    "writing": {
        "tr": "Yazma", "en": "Writing", "de": "Schreiben", "fr": "Expression écrite",
    },
}

ENGLISH_58 = [
    ("progress_exam_1", "main", "score", True),
    ("progress_exam_2", "main", "score", True),
    ("quiz_1", "main", "score", False),
    ("quiz_2", "main", "score", False),
    ("reader_1", "skills", "score", False),
    ("reader_2", "skills", "score", False),
    ("homework_1", "main", "score", False),
    ("homework_2", "main", "score", False),
    ("highlights", "main", "score", False),
    ("book_reading", "skills", "score", False),
    ("performance_1", "main", "score", False),
    ("performance_2", "skills", "score", False),
]

L2_ITEMS = [
    ("exam_1", "score"),
    ("exam_2", "score"),
    ("homework_1", "score"),
    ("homework_2", "score"),
    ("active_class_participation", "scale3"),
    ("regular_homework", "scale3"),
    ("uses_learned_vocabulary", "scale3"),
    ("teacher_comments", "text"),
]

PRIMARY_ITEMS = [
    ("willing_class_participation", "scale3", "attitudes_toward_course"),
    ("follows_instructions", "scale3", "listening_comprehension"),
    ("reads_simple_texts", "scale3", "reading_comprehension"),
    ("oral_expression", "scale3", "speaking"),
    ("writes_learned_vocabulary", "scale3", "writing"),
    ("teacher_comments", "text", None),
]


def _labels(key: str) -> dict[str, str]:
    return REPORT_LABELS[key]


def seed_columns(db: Session, semester_id: int) -> None:
    for grade in range(5, 9):
        for pos, (key, role, vtype, avg) in enumerate(ENGLISH_58, start=1):
            db.add(m.ColumnDefinition(
                semester_id=semester_id, grade_level=grade, subject="english",
                value_type=vtype, owner_role=role, labels=_labels(key),
                counts_in_average=avg, position=pos,
            ))
    for grade in range(4, 9):
        for lang in ("german", "french"):
            for pos, (key, vtype) in enumerate(L2_ITEMS, start=1):
                db.add(m.ColumnDefinition(
                    semester_id=semester_id, grade_level=grade, subject=lang,
                    value_type=vtype, owner_role=lang, labels=_labels(key), position=pos,
                ))
    for grade in range(1, 5):
        for pos, (key, vtype, group_key) in enumerate(PRIMARY_ITEMS, start=1):
            db.add(m.ColumnDefinition(
                semester_id=semester_id, grade_level=grade, subject="english",
                value_type=vtype, owner_role="main", labels=_labels(key),
                group_labels=_labels(group_key) if group_key else None, position=pos,
            ))
```

In `seed()`, keep a handle on semester 1 (assign it to a variable before `add_all`, flush, then `seed_columns(db, sem1.id)` right after). Use the current seed only in a confirmed disposable synthetic environment; do not reset a
shared development, demo, or school database as part of a documentation check.

**Check:** inspect active definitions per semester, subject and grade rather than summing
all four seeded years. Middle-English defaults contain eleven scores and no text; grade-4 L2
contains ratings and comments but no scores. Check `tests/test_seed_plan.py` and
`tests/test_assessment_programme.py` against the current constants. Some rubric labels store
Turkish plus the report language and use fallback; do not require four keys on every database
label. Have fluent school staff review the configured labels before production.

### 2.1.4 The admin column editor

**What we're building:** the +/- screen from your original spec: pick a grade and subject, see the columns, add one through a validated dialog, reorder with arrows, remove with honest feedback about the delete-vs-disable outcome.

**Why RHF + Zod arrive here:** this is the first real form, and the pattern you establish (Zod schema → resolver → typed `useForm`) repeats through every admin dialog in Phase 3. One scope cut remains for newly created custom columns: the dialog edits the **Turkish label only** and mirrors it into the other three languages until §4.4 adds full four-language editing. The built-in seed catalog is already translated in all four locales; custom content uses Turkish fallback until an admin supplies its translations.

**Layer 1 · Nudge:** a route whose grade/subject live in _typed search params_ (bookmarkable state, the TanStack Router way), a query for the list, four mutations, one dialog.

**Layer 2 · Guide:** generated names follow the operation ids: `listColumnsOptions` / `listColumnsQueryKey`, `createColumnMutation`, `deleteColumnMutation`, `reorderColumnsMutation`, `copyColumnsMutation`. If your hey-api version styles them differently, the generated TanStack file is the authority; grep it once. Reorder UX: swap locally, send the _full_ id order. Delete UX: run the mutation, then toast whichever of `{deleted, disabled}` came back.

**Layer 3 · Exact assembly:**

```bash
pnpm --filter @flrc/admin add react-hook-form @hookform/resolvers zod @tanstack/react-table
pnpm dlx shadcn@latest add dialog input label checkbox select sonner   # run from apps/admin
```

Mount sonner's `<Toaster />` once in `__root.tsx`. Then `apps/admin/src/routes/_auth/columns.tsx`:

```tsx
import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  createColumnMutation,
  deleteColumnMutation,
  listColumnsOptions,
  listColumnsQueryKey,
  reorderColumnsMutation,
} from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Checkbox } from "@flrc/ui/components/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@flrc/ui/components/dialog";
import { Input } from "@flrc/ui/components/input";
import { Label } from "@flrc/ui/components/label";

const GRADES = [1, 2, 3, 4, 5, 6, 7, 8];
const SUBJECTS = ["english", "german", "french"] as const;
type Subject = (typeof SUBJECTS)[number];

export const Route = createFileRoute("/_auth/columns")({
  validateSearch: (s): { grade: number; subject: Subject } => ({
    grade: GRADES.includes(Number(s.grade)) ? Number(s.grade) : 5,
    subject: SUBJECTS.includes(s.subject as Subject) ? (s.subject as Subject) : "english",
  }),
  component: ColumnsPage,
});

const formSchema = z.object({
  label_tr: z.string().min(1),
  value_type: z.enum(["score", "scale3", "text"]),
  owner_role: z.enum(["main", "skills", "german", "french"]),
  counts_in_average: z.boolean(),
});
type FormValues = z.infer<typeof formSchema>;

const ColumnsPage = () => {
  const { grade, subject } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { t } = useTranslation();
  const qc = useQueryClient();
  const query = { grade_level: grade, subject };
  const listKey = listColumnsQueryKey({ query });
  const { data: columns = [] } = useQuery(listColumnsOptions({ query }));
  const invalidate = () => qc.invalidateQueries({ queryKey: listKey });

  const reorder = useMutation({ ...reorderColumnsMutation(), onSuccess: invalidate });
  const remove = useMutation({
    ...deleteColumnMutation(),
    onSuccess: (res) => {
      toast(res.disabled ? t("columns.disabledInfo") : t("columns.deletedInfo"));
      invalidate();
    },
  });

  const move = (index: number, dir: -1 | 1) => {
    const ids = columns.map((c) => c.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    reorder.mutate({ body: { ordered_ids: ids } });
  };

  return (
    <main className="space-y-4 p-8">
      <div className="flex items-center gap-3">
        <select
          className="rounded border p-2"
          value={grade}
          onChange={(e) => navigate({ search: { grade: Number(e.target.value), subject } })}
        >
          {GRADES.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
        <select
          className="rounded border p-2"
          value={subject}
          onChange={(e) => navigate({ search: { grade, subject: e.target.value as Subject } })}
        >
          {SUBJECTS.map((s) => (
            <option key={s} value={s}>
              {t(`subjects.${s}`)}
            </option>
          ))}
        </select>
        <CreateDialog grade={grade} subject={subject} onCreated={invalidate} />
      </div>

      <ul className="max-w-2xl divide-y rounded border">
        {columns.map((col, i) => (
          <li
            key={col.id}
            className={`flex items-center gap-2 p-2 ${col.is_active ? "" : "opacity-50"}`}
          >
            <span className="w-8 text-sm text-muted-foreground">{col.position}</span>
            <span className="flex-1">{col.labels.tr}</span>
            <span className="w-16 text-xs">{col.value_type}</span>
            <span className="w-16 text-xs">{col.owner_role}</span>
            {col.counts_in_average && <span className="text-xs">Ø</span>}
            <Button size="sm" variant="ghost" onClick={() => move(i, -1)}>
              ↑
            </Button>
            <Button size="sm" variant="ghost" onClick={() => move(i, 1)}>
              ↓
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => remove.mutate({ path: { column_id: col.id } })}
            >
              -
            </Button>
          </li>
        ))}
      </ul>
    </main>
  );
};

const CreateDialog = ({
  grade,
  subject,
  onCreated,
}: {
  grade: number;
  subject: Subject;
  onCreated: () => void;
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const isL2 = subject !== "english";
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      label_tr: "",
      value_type: "score",
      owner_role: isL2 ? subject : "main",
      counts_in_average: false,
    },
  });
  const create = useMutation({
    ...createColumnMutation(),
    onSuccess: () => {
      onCreated();
      setOpen(false);
      form.reset();
    },
  });
  const submit = form.handleSubmit((v) => {
    const label = { tr: v.label_tr, en: v.label_tr, de: v.label_tr, fr: v.label_tr };
    create.mutate({
      body: {
        grade_level: grade,
        subject,
        value_type: v.value_type,
        owner_role: v.owner_role,
        labels: label,
        counts_in_average: v.counts_in_average,
      },
    });
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>+ {t("columns.add")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("columns.add")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>{t("columns.labelTr")}</Label>
            <Input {...form.register("label_tr")} />
            {form.formState.errors.label_tr && (
              <p className="text-sm text-red-600">{t("forms.required")}</p>
            )}
          </div>
          <div>
            <Label>{t("columns.valueType")}</Label>
            <select className="w-full rounded border p-2" {...form.register("value_type")}>
              <option value="score">0-100</option>
              <option value="scale3">🙁 😐 🙂</option>
              <option value="text">{t("columns.text")}</option>
            </select>
          </div>
          <div>
            <Label>{t("columns.ownerRole")}</Label>
            <select className="w-full rounded border p-2" {...form.register("owner_role")}>
              {(isL2 ? [subject] : ["main", "skills"]).map((r) => (
                <option key={r} value={r}>
                  {t(`roles.${r}`)}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2">
            <Checkbox
              checked={form.watch("counts_in_average")}
              onCheckedChange={(v) => form.setValue("counts_in_average", v === true)}
            />
            {t("columns.countsInAverage")}
          </label>
          <Button onClick={submit} disabled={create.isPending}>
            {t("forms.save")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

Add the new i18n keys (`columns.*`, `subjects.*`, `roles.*`, `forms.*`) to `tr.json`/`en.json` as you hit them; the missing-key console warnings are your checklist.

**Check:** open `/columns?grade=5&subject=english` → the twelve seeded columns; add "Deneme" (appears last), move it up twice, delete it (`deletedInfo` toast). Change subject to German → owner-role dropdown collapses to just `german`. Bookmark the URL and reopen: same view, with search params carrying state as promised.

**If it breaks:** mutations 403 → you're logged into the _teacher_ app's session as a non-admin seed user; log in as yourself. Query never refetches after create → your `listColumnsQueryKey` call doesn't include the same `{ query }` object shape the options call used.

## Step 2.2: Teaching assignments

**What we're building:** the data that makes column _ownership_ real: per class, four dropdowns (main / skills / german / french) choosing a teacher, plus the three tiny read endpoints the admin screens keep reusing (classes, users, a class's assignments).

**Why an upsert:** `unique (class_id, role)` means "assign" and "reassign" are one statement, Postgres's `INSERT … ON CONFLICT DO UPDATE`, which you'll meet again in the save path. History of _who owned when_ rides on the audit trail's `updated_by`, good enough for v1 (ARCH §5/2.2).

**Layer 3 · Exact assembly:** `src/flrc/modules/academics/assignments.py`:

```python
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import require_admin, require_coordinator_or_admin, writable_year
from flrc.db.models import AcademicYear, SchoolClass, TeachingAssignment, User
from flrc.db.session import get_session

router = APIRouter(tags=["assignments"])

Role = Literal["main", "skills", "german", "french"]


class ClassOut(BaseModel):
    id: int
    grade_level: int
    section: str
    name: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool


class AssignmentSlotOut(BaseModel):
    role: str
    user_id: int | None
    user_name: str | None


class AssignBody(BaseModel):
    user_id: int


@router.get("/classes")
async def list_classes(
    _: User = Depends(require_coordinator_or_admin),
    year: AcademicYear = Depends(writable_year),
    db: AsyncSession = Depends(get_session),
) -> list[ClassOut]:
    result = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.year_id == year.id)
        .order_by(SchoolClass.grade_level, SchoolClass.section)
    )
    return [
        ClassOut(id=c.id, grade_level=c.grade_level, section=c.section,
                 name=f"{c.grade_level}/{c.section}")
        for c in result.scalars()
    ]


@router.get("/users")
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.full_name))
    return [UserOut.model_validate(u, from_attributes=True) for u in result.scalars()]


@router.get("/classes/{class_id}/assignments")
async def get_assignments(
    class_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> list[AssignmentSlotOut]:
    result = await db.execute(
        select(TeachingAssignment.role, User.id, User.full_name)
        .join(User, User.id == TeachingAssignment.user_id)
        .where(TeachingAssignment.class_id == class_id)
    )
    found = {r.role: r for r in result.all()}
    return [
        AssignmentSlotOut(
            role=role,
            user_id=found[role].id if role in found else None,
            user_name=found[role].full_name if role in found else None,
        )
        for role in ("main", "skills", "german", "french")
    ]


@router.put("/classes/{class_id}/assignments/{role}")
async def upsert_assignment(
    class_id: int,
    role: Role,
    body: AssignBody,
    _: User = Depends(require_admin),
    __: AcademicYear = Depends(writable_year),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    teacher = await db.get(User, body.user_id)
    if teacher is None or not teacher.is_active:
        raise HTTPException(422, {"code": "unknown_user"})
    if await db.get(SchoolClass, class_id) is None:
        raise HTTPException(404, {"code": "unknown_class"})
    stmt = (
        pg_insert(TeachingAssignment)
        .values(class_id=class_id, role=role, user_id=body.user_id)
        .on_conflict_do_update(
            index_elements=["class_id", "role"], set_={"user_id": body.user_id}
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}
```

Register, `pnpm generate`. The admin UI is your first solo flight: `_auth/assignments.tsx` = a class `<select>` (from `listClassesOptions`), then four labeled `<select>`s over `listUsersOptions` data, each firing `upsertAssignmentMutation` on change and invalidating `getAssignmentsQueryKey`; structurally, a smaller `columns.tsx`. Build it from that sentence before peeking back at 2.1.4.

**Check:** reassign 5/A's skills teacher; `select * from teaching_assignments where class_id=<class-id-for-5/A>;` shows the new user; log in as that seeded teacher (you can't, as there's no Google account, so verify via `/api/me` in 2.6's test world instead, or just trust psql today and let the grid's `owner_name` prove it visually in 2.4).

## Step 2.3: The grid read endpoint

**What we're building:** one GET that returns everything a class-grid render needs in a single round trip: localized columns with ownership flags, the roster (L2-filtered when the subject is a language), every existing cell with its `version`, and the meta the UI's chrome feeds on (statuses, live grants, your last batch).

**Why the payload is designed before the code:** the response shape _is_ the contract between three consumers: the desktop grid, the phone stepper, and (later) the card assembler's cousin. Design it on paper, then make the code match. Two conventions carry the whole concurrency story: **a missing cell key means version 0**, and every present cell carries the version the client must echo back at save time. And no pagination, deliberately: a class is physically capped around 30 students; knowing when _not_ to paginate is also a skill (ARCH §5/2.3).

**Layer 1 · Nudge:** load class → its year's current semester → active columns for (semester, grade, subject) → roster via enrollments (∩ student_languages when L2) → one query for all grade_values in (roster × columns) → assemble.

**Layer 2 · Guide:** ownership per column = "does the teaching assignment for this class's `owner_role` point at me"; `owner_name` comes along for the grant dialog's wording. Label resolution: pick `labels[locale]` with TR fallback. `my_last_batch.undoable` is true only if the batch isn't consumed and the semester is still open: the undo button's enable logic, computed server-side once.

**Layer 3 · Exact assembly:** `src/flrc/modules/grades/router.py`:

```python
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import current_user
from flrc.db.models import (
    AcademicYear, AuditEntry, ColumnDefinition, Enrollment, GradeValue,
    OverrideGrant, SaveBatch, SchoolClass, Semester, Student, StudentLanguage,
    TeachingAssignment, User,
)
from flrc.db.session import get_session

router = APIRouter(tags=["grid"])

Subject = Literal["english", "german", "french"]

VALUE_FIELD = {"score": "score", "scale3": "scale", "text": "text_value"}


def cell_value(gv: GradeValue, value_type: str) -> int | str | None:
    return getattr(gv, VALUE_FIELD[value_type])


class CellOut(BaseModel):
    value: int | str | None
    version: int


class GridColumnOut(BaseModel):
    id: int
    label: str
    group: str | None
    value_type: str
    owner_role: str
    owner_name: str | None
    owned_by_you: bool
    position: int


class GridRowOut(BaseModel):
    student_id: int
    full_name: str
    cells: dict[str, CellOut]


class GrantOut(BaseModel):
    role: str
    expires_at: datetime


class LastBatchOut(BaseModel):
    id: int
    created_at: datetime
    cell_count: int
    undoable: bool


class GridMetaOut(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    subject: str
    semester_status: str
    year_status: str
    my_grants: list[GrantOut]
    my_last_batch: LastBatchOut | None


class GridOut(BaseModel):
    meta: GridMetaOut
    columns: list[GridColumnOut]
    rows: list[GridRowOut]


def pick_label(labels: dict[str, str], locale: str) -> str:
    return labels.get(locale) or labels.get("tr") or next(iter(labels.values()), "")


@router.get("/classes/{class_id}/grid")
async def get_grid(
    class_id: int,
    subject: Subject,
    locale: str = "tr",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> GridOut:
    cls = await db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await db.get(AcademicYear, cls.year_id)

    semesters = (
        await db.execute(select(Semester).where(Semester.year_id == year.id))
    ).scalars().all()
    current = next((s for s in semesters if s.status == "open"), None) or max(
        semesters, key=lambda s: s.number
    )

    columns = (
        await db.execute(
            select(ColumnDefinition)
            .where(
                ColumnDefinition.semester_id == current.id,
                ColumnDefinition.grade_level == cls.grade_level,
                ColumnDefinition.subject == subject,
                ColumnDefinition.is_active.is_(True),
            )
            .order_by(ColumnDefinition.position)
        )
    ).scalars().all()

    owners = {
        row.role: row
        for row in (
            await db.execute(
                select(TeachingAssignment.role, User.id.label("uid"), User.full_name)
                .join(User, User.id == TeachingAssignment.user_id)
                .where(TeachingAssignment.class_id == class_id)
            )
        ).all()
    }

    grants = (
        await db.execute(
            select(OverrideGrant).where(
                OverrideGrant.user_id == user.id,
                OverrideGrant.class_id == class_id,
                OverrideGrant.expires_at > func.now(),
            )
        )
    ).scalars().all()

    roster_query = (
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == class_id)
        .order_by(Student.search_name)
    )
    if subject in ("german", "french"):
        roster_query = roster_query.join(
            StudentLanguage, StudentLanguage.student_id == Student.id
        ).where(
            StudentLanguage.year_id == year.id,
            StudentLanguage.language == subject,
        )
    students = (await db.execute(roster_query)).scalars().all()

    column_ids = [c.id for c in columns]
    student_ids = [s.id for s in students]
    values = (
        await db.execute(
            select(GradeValue).where(
                GradeValue.column_definition_id.in_(column_ids),
                GradeValue.student_id.in_(student_ids),
            )
        )
    ).scalars().all() if column_ids and student_ids else []
    by_type = {c.id: c.value_type for c in columns}
    cell_map: dict[tuple[int, int], GradeValue] = {
        (gv.student_id, gv.column_definition_id): gv for gv in values
    }

    batch_row = (
        await db.execute(
            select(SaveBatch)
            .where(SaveBatch.user_id == user.id, SaveBatch.class_id == class_id)
            .order_by(SaveBatch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_batch = None
    if batch_row is not None:
        count = (
            await db.execute(
                select(func.count()).select_from(AuditEntry).where(
                    AuditEntry.batch_id == batch_row.id
                )
            )
        ).scalar_one()
        last_batch = LastBatchOut(
            id=batch_row.id,
            created_at=batch_row.created_at,
            cell_count=count,
            undoable=not batch_row.undone and current.status == "open",
        )

    return GridOut(
        meta=GridMetaOut(
            class_id=class_id,
            class_name=f"{cls.grade_level}/{cls.section}",
            grade_level=cls.grade_level,
            subject=subject,
            semester_status=current.status,
            year_status=year.status,
            my_grants=[GrantOut(role=g.role, expires_at=g.expires_at) for g in grants],
            my_last_batch=last_batch,
        ),
        columns=[
            GridColumnOut(
                id=c.id,
                label=pick_label(c.labels, locale),
                group=pick_label(c.group_labels, locale) if c.group_labels else None,
                value_type=c.value_type,
                owner_role=c.owner_role,
                owner_name=owners[c.owner_role].full_name if c.owner_role in owners else None,
                owned_by_you=(
                    c.owner_role in owners and owners[c.owner_role].uid == user.id
                ),
                position=c.position,
            )
            for c in columns
        ],
        rows=[
            GridRowOut(
                student_id=s.id,
                full_name=s.full_name,
                cells={
                    str(cid): CellOut(
                        value=cell_value(cell_map[(s.id, cid)], by_type[cid]),
                        version=cell_map[(s.id, cid)].version,
                    )
                    for cid in column_ids
                    if (s.id, cid) in cell_map
                },
            )
            for s in students
        ],
    )
```

Register the router, `pnpm generate`.

**Check:** find a class you teach (`select class_id, role from teaching_assignments ta join users u on u.id=ta.user_id where u.email='<you>';`) and plant one cell by hand so the payload has something to say:

```sql
insert into grade_values (student_id, column_definition_id, score, version, updated_by, created_at, updated_at)
select e.student_id, cd.id, 87, 1, (select id from users where is_admin limit 1), now(), now()
from enrollments e, column_definitions cd
where e.class_id = <your-class-id> and cd.grade_level = <its-grade> and cd.subject='english' and cd.position = 1
limit 1;
```

Then, logged into the teacher app, run in the browser console: `fetch('/api/classes/<id>/grid?subject=english').then(r => r.json()).then(console.log)`. Inspect: your columns carry `owned_by_you` correctly per your seeded roles; exactly one row has a `cells` entry with `version: 1`; switch `subject=german` on a grade-5 class and watch the roster shrink to the German kids. That shrink is `student_language` doing its one job.

**If it breaks:** every `owned_by_you` false → you're checking a class you don't teach (the seed round-robins assignments; use the SQL above, don't guess). `cells` empty despite the insert → the insert's column belonged to a different semester/grade than the grid asked for.

## Step 2.4: The grid UI (TanStack Table, three cells, keyboard-first)

**Current notes and bulk editing (ADR-059 through ADR-063):** primary English and German/French
include a final notes filter in both table and stepper. Grades 5-8 English have no notes
filter. Their wide numeric overview reserves room for the last angled heading without a comment
column. Pupil/class 1-2-3 controls stage all rating columns, including hidden categories, in
Zustand; only Save submits them. Scores and written comments are left intact.

**Readable assessment navigation (ADR-049, capacity updated in ADR-061):** show four sentence
columns at a 1280px viewport and five at 1366px or wider, with category filters and previous/next
controls in configured order. Narrow screens show fewer columns. Keep complete normal-case
labels and student names visible, explain the 1-2-3 scale,
and retain drafts across assessment pages. Save includes hidden draft cells. Check with
`pnpm exec playwright test e2e/assessment-grid.spec.ts` against the teacher dev server.

**What we're building:** the screen teachers will judge the whole project by: grouped headers, an always-visible student identity column, per-type editable cells, and Enter-moves-down-the-column keyboard flow (the grade-entry motion you know from Excel). Foreign columns render locked; edits into them are _intercepted before a keystroke is lost_ (the grant dialog plugs in at 2.7; today a toast holds its place).

**Why headless was the right call, felt concretely:** TanStack Table computes header groups and row models; every `<td>` is yours, which is precisely what lets a cell be a Zustand-connected input instead of a string. The cells live in `packages/ui` as _presentational_ components (value in, `onCommit` out) so the phone stepper reuses them untouched in 2.10; all state wiring stays in the page.

**Layer 1 · Nudge:** three components keyed on `value_type`; a `refs` map keyed `"row:col"` plus one keydown handler = the whole navigation system; build TanStack column defs from the API's `columns`, nesting them under `columnHelper.group` when `group` labels run.

**Layer 3 · Exact assembly (the cells):**

```bash
pnpm --filter @flrc/teacher add @tanstack/react-table zustand
pnpm dlx shadcn@latest add popover textarea   # from apps/teacher → lands in packages/ui
```

Add to `packages/ui/package.json` `exports`: `"./grid/*": "./src/grid/*.tsx"`. Then `packages/ui/src/grid/cells.tsx`:

```tsx
import { useEffect, useState, type KeyboardEvent, type Ref } from "react";
import { Button } from "../components/button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/popover";
import { Textarea } from "../components/textarea";
import { cn } from "../lib/utils";

export type CellValue = number | string | null;

export type CellProps = {
  value: CellValue;
  dirty: boolean;
  onCommit: (value: CellValue) => void;
  onNavKey?: (e: KeyboardEvent) => void;
  cellRef?: Ref<never>;
};

const dirtyClass = "border-amber-400 bg-amber-50";

export const ScoreCell = ({ value, dirty, onCommit, onNavKey, cellRef }: CellProps) => {
  const server = value === null || value === undefined ? "" : String(value);
  const [draft, setDraft] = useState(server);
  useEffect(() => setDraft(server), [server]);
  const commit = () => {
    if (draft === "") return onCommit(null);
    const n = Number(draft);
    if (Number.isInteger(n) && n >= 0 && n <= 100) onCommit(n);
    else setDraft(server);
  };
  return (
    <input
      ref={cellRef as Ref<HTMLInputElement>}
      inputMode="numeric"
      className={cn("h-9 w-16 rounded border px-2 text-center text-sm", dirty && dirtyClass)}
      value={draft}
      onChange={(e) => {
        if (/^\d{0,3}$/.test(e.target.value)) setDraft(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        onNavKey?.(e);
      }}
    />
  );
};

const FACES: Record<1 | 2 | 3, string> = { 1: "🙁", 2: "😐", 3: "🙂" };

export const Scale3Cell = ({ value, dirty, onCommit, onNavKey, cellRef }: CellProps) => {
  const current = typeof value === "number" ? (value as 1 | 2 | 3) : null;
  const cycle = () => onCommit(current === null ? 1 : current === 3 ? null : current + 1);
  return (
    <button
      type="button"
      ref={cellRef as Ref<HTMLButtonElement>}
      className={cn("h-9 w-16 rounded border text-lg", dirty && dirtyClass)}
      onClick={cycle}
      onKeyDown={(e) => {
        if (e.key === " ") {
          e.preventDefault();
          cycle();
        }
        onNavKey?.(e);
      }}
    >
      {current ? FACES[current] : "—"}
    </button>
  );
};

export const TextCell = ({ value, dirty, onCommit, cellRef }: CellProps) => {
  const server = typeof value === "string" ? value : "";
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(server);
  useEffect(() => setDraft(server), [server]);
  const done = () => onCommit(draft.trim() === "" ? null : draft.trim());
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) done();
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          ref={cellRef as Ref<HTMLButtonElement>}
          className={cn(
            "h-9 w-40 truncate rounded border px-2 text-left text-sm",
            dirty && dirtyClass,
          )}
        >
          {draft || "…"}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-2">
        <Textarea rows={4} autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button size="sm" onClick={() => setOpen(false)}>
          OK
        </Button>
      </PopoverContent>
    </Popover>
  );
};

export const LockedCell = ({ value, onAttempt }: { value: CellValue; onAttempt: () => void }) => (
  <button
    type="button"
    className="h-9 w-16 rounded border bg-muted text-sm text-muted-foreground"
    onClick={onAttempt}
    onKeyDown={(e) => {
      if (e.key.length === 1 || e.key === "Enter") {
        e.preventDefault();
        onAttempt();
      }
    }}
  >
    {value ?? "🔒"}
  </button>
);
```

**Layer 3 · Exact assembly (the page).** First the store it leans on (built fully in 2.5, needed as a stub now), `apps/teacher/src/grid/dirty-store.ts`:

```ts
import { create } from "zustand";

export type CellKey = `${number}:${number}`;
export const dirtyKey = (studentId: number, columnId: number): CellKey =>
  `${studentId}:${columnId}`;

export type DirtyCell = {
  studentId: number;
  columnId: number;
  value: number | string | null;
  expectedVersion: number;
};

type DirtyState = {
  cells: Record<CellKey, DirtyCell>;
  setCell: (cell: DirtyCell) => void;
  clearCells: (keys: CellKey[]) => void;
  clearAll: () => void;
};

export const useDirtyStore = create<DirtyState>((set) => ({
  cells: {},
  setCell: (cell) =>
    set((s) => ({ cells: { ...s.cells, [dirtyKey(cell.studentId, cell.columnId)]: cell } })),
  clearCells: (keys) =>
    set((s) => {
      const next = { ...s.cells };
      keys.forEach((k) => delete next[k]);
      return { cells: next };
    }),
  clearAll: () => set({ cells: {} }),
}));
```

Then `apps/teacher/src/routes/_auth/classes.$classId.$subject.tsx`:

```tsx
import { useMemo, useRef, type KeyboardEvent } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getGridOptions } from "@flrc/api-client";
import type { GridColumnOut, GridRowOut } from "@flrc/api-client";
import { LockedCell, Scale3Cell, ScoreCell, TextCell } from "@flrc/ui/grid/cells";
import { dirtyKey, useDirtyStore } from "../../grid/dirty-store";

export const Route = createFileRoute("/_auth/classes/$classId/$subject")({
  component: GridPage,
});

const useGridNav = () => {
  const refs = useRef(new Map<string, HTMLElement>());
  const register = (r: number, c: number) => (el: HTMLElement | null) => {
    const key = `${r}:${c}`;
    if (el) refs.current.set(key, el);
    else refs.current.delete(key);
  };
  const navKey = (r: number, c: number) => (e: KeyboardEvent) => {
    const go = (dr: number) => {
      const target = refs.current.get(`${r + dr}:${c}`);
      if (target) {
        e.preventDefault();
        target.focus();
      }
    };
    if (e.key === "Enter" || e.key === "ArrowDown") go(1);
    else if (e.key === "ArrowUp") go(-1);
  };
  return { register, navKey };
};

const GridPage = () => {
  const { classId, subject } = Route.useParams();
  const { t, i18n } = useTranslation();
  const { data } = useQuery(
    getGridOptions({
      path: { class_id: Number(classId) },
      query: { subject: subject as never, locale: i18n.language },
    }),
  );
  const { register, navKey } = useGridNav();
  const grantRoles = useMemo(() => new Set(data?.meta.my_grants.map((g) => g.role) ?? []), [data]);

  const columns = useMemo<ColumnDef<GridRowOut, never>[]>(() => {
    if (!data) return [];
    const helper = createColumnHelper<GridRowOut>();
    const defs: ColumnDef<GridRowOut, never>[] = [
      helper.accessor("full_name", {
        id: "student",
        header: t("grid.student"),
        cell: (ctx) => (
          <span className="block max-w-44 truncate font-medium">{ctx.getValue()}</span>
        ),
      }) as ColumnDef<GridRowOut, never>,
    ];
    let group: { label: string; columns: ColumnDef<GridRowOut, never>[] } | null = null;
    data.columns.forEach((col, i) => {
      const def = helper.display({
        id: String(col.id),
        header: () => (
          <span className={col.owned_by_you ? "" : "text-muted-foreground"}>
            {col.label} {col.owned_by_you ? "" : "🔒"}
          </span>
        ),
        cell: (ctx) => (
          <Cell col={col} row={ctx.row.original} rowIndex={ctx.row.index} colIndex={i + 1} />
        ),
      }) as ColumnDef<GridRowOut, never>;
      if (col.group) {
        if (!group || group.label !== col.group) {
          group = { label: col.group, columns: [] };
          defs.push(
            helper.group({ id: `g${i}`, header: col.group, columns: group.columns }) as never,
          );
        }
        group.columns.push(def);
      } else {
        group = null;
        defs.push(def);
      }
    });
    return defs;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, grantRoles, i18n.language]);

  const Cell = ({
    col,
    row,
    rowIndex,
    colIndex,
  }: {
    col: GridColumnOut;
    row: GridRowOut;
    rowIndex: number;
    colIndex: number;
  }) => {
    const key = dirtyKey(row.student_id, col.id);
    const dirtyCell = useDirtyStore((s) => s.cells[key]);
    const serverCell = row.cells[String(col.id)];
    const value = dirtyCell ? dirtyCell.value : (serverCell?.value ?? null);
    const locked = !col.owned_by_you && !grantRoles.has(col.owner_role);
    if (locked) {
      return (
        <LockedCell
          value={value}
          onAttempt={() => toast(t("grid.lockedInfo", { name: col.owner_name ?? "?" }))}
        />
      );
    }
    const commit = (next: number | string | null) => {
      const serverValue = serverCell?.value ?? null;
      if (next === serverValue) useDirtyStore.getState().clearCells([key]);
      else
        useDirtyStore.getState().setCell({
          studentId: row.student_id,
          columnId: col.id,
          value: next,
          expectedVersion: serverCell?.version ?? 0,
        });
    };
    const props = {
      value,
      dirty: !!dirtyCell,
      onCommit: commit,
      onNavKey: navKey(rowIndex, colIndex),
      cellRef: register(rowIndex, colIndex) as never,
    };
    if (col.value_type === "score") return <ScoreCell {...props} />;
    if (col.value_type === "scale3") return <Scale3Cell {...props} />;
    return <TextCell {...props} />;
  };

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (!data) return <main className="p-8">{t("loading")}</main>;

  return (
    <main className="space-y-3 p-4">
      <header className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">
          {data.meta.class_name} · {t(`subjects.${data.meta.subject}`)}
        </h1>
        {data.meta.semester_status === "locked" && (
          <span className="rounded bg-muted px-2 py-1 text-sm">{t("grid.locked")}</span>
        )}
        {/* SaveAll mounts here in 2.5 */}
      </header>
      <div className="w-full min-w-0 overflow-visible rounded border">
        <table className="w-full table-fixed border-collapse text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    colSpan={h.colSpan}
                    className="border-b bg-background px-1 py-2 text-left break-words"
                  >
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b last:border-0">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="min-w-0 px-1 py-1 break-words">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
};
```

Link the dashboard to it: on `_auth/index.tsx`, render the user's `assignments` as links to `/classes/$classId/$subject` (role `main`/`skills` → subject `english`; `german`/`french` → that subject): a five-line `map`, your solo flight.

**Check:** open one of your classes. Type a full column of scores using only Enter; eyes never leave the numbers. Space-cycle a scale cell on an L2 grid (🙁 → 😐 → 🙂 → blank). Open a text popover, type, click away: the cell shows the preview with the amber unsaved tint. Retype a cell back to its planted server value: the tint _disappears_ (the equal-to-server branch working). Columns owned by colleagues wear 🔒 and answer with the toast naming them. Nothing persists on refresh yet, which is correct; persistence is the next two steps.

**If it breaks:** every column locked including yours → you're viewing a class you don't teach (grid tells the truth; check via the dashboard links, not a typed URL). A second scrollbar appears → remove overflow sizing from the table wrapper and keep `w-full table-fixed`; the document owns row scrolling. A field disappears sideways → a child still has a fixed/minimum width; make the control `w-full min-w-0` and allow its header to wrap. Enter jumps two rows → your keydown handler runs on both the input and a parent; it belongs on the cell only.

**Docs:** tanstack.com/table, the "Column Groups" and "Editable Data" guides. **Why deeper:** ARCH §5/2.4 (including why virtualization is _deliberately_ absent at 30 rows; leave that comment in the code, as reviewers notice chosen omissions).

## Step 2.5: Save All (draining the dirty map)

**What we're building:** the header button that sends only what changed, four visible states (idle → saving → saved ✓ → error), cache-merge without a refetch flash, and two leave-guards so unsaved grades can't be lost to a stray click.

**Why the merge instead of an invalidate:** an invalidate refetches the whole grid and repaints every cell: a visible blink and a wasted query. `setQueryData` surgically writes the returned new versions (and the values you already know, from the dirty map) into the cache; the grid re-renders only the touched cells and the amber tints melt away. This is the "Query owns server truth" boundary earning rent (invariant #6).

**Layer 1 · Nudge:** one `useSaveGrid` hook owning the mutation, the conflict list, and the accept/cancel handlers; the button and the dialog become dumb consumers of it.

**Layer 3 · Exact assembly:** `apps/teacher/src/grid/use-save-grid.ts`:

```tsx
import { useState } from "react";
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { saveGridMutation, type ConflictOut, type SaveResponse } from "@flrc/api-client";
import { dirtyKey, useDirtyStore } from "./dirty-store";

type Args = { classId: number; subject: string; gridKey: QueryKey };

export const useSaveGrid = ({ classId, subject, gridKey }: Args) => {
  const qc = useQueryClient();
  const [conflicts, setConflicts] = useState<ConflictOut[]>([]);
  const [flash, setFlash] = useState(false);

  const merge = (res: SaveResponse) => {
    const dirty = useDirtyStore.getState().cells;
    qc.setQueryData(gridKey, (old: any) => {
      if (!old) return old;
      const byStudent = new Map<number, typeof res.applied>();
      res.applied.forEach((a) => {
        byStudent.set(a.student_id, [...(byStudent.get(a.student_id) ?? []), a]);
      });
      return {
        ...old,
        rows: old.rows.map((row: any) => {
          const updates = byStudent.get(row.student_id);
          if (!updates) return row;
          const cells = { ...row.cells };
          updates.forEach((a) => {
            const d = dirty[dirtyKey(a.student_id, a.column_id)];
            cells[String(a.column_id)] = {
              value: d ? d.value : (cells[String(a.column_id)]?.value ?? null),
              version: a.version,
            };
          });
          return { ...row, cells };
        }),
      };
    });
    useDirtyStore
      .getState()
      .clearCells(res.applied.map((a) => dirtyKey(a.student_id, a.column_id)));
  };

  const mutation = useMutation({
    ...saveGridMutation(),
    onSuccess: (res) => {
      merge(res);
      if (res.rejected.length) toast.error(`✗ ${res.rejected.length}`);
      if (res.conflicts.length) setConflicts(res.conflicts);
      else {
        setFlash(true);
        setTimeout(() => setFlash(false), 2000);
      }
    },
  });

  const toWire = (c: {
    studentId: number;
    columnId: number;
    value: unknown;
    expectedVersion: number;
  }) => ({
    student_id: c.studentId,
    column_id: c.columnId,
    value: c.value as never,
    expected_version: c.expectedVersion,
  });

  const saveAll = () =>
    mutation.mutate({
      path: { class_id: classId },
      body: {
        subject: subject as never,
        force: false,
        cells: Object.values(useDirtyStore.getState().cells).map(toWire),
      },
    });

  const acceptConflicts = () => {
    const dirty = useDirtyStore.getState().cells;
    const cells = conflicts.map((c) => {
      const d = dirty[dirtyKey(c.student_id, c.column_id)];
      return {
        student_id: c.student_id,
        column_id: c.column_id,
        value: (d?.value ?? c.your_value) as never,
        expected_version: 0,
      };
    });
    setConflicts([]);
    mutation.mutate({
      path: { class_id: classId },
      body: { subject: subject as never, force: true, cells },
    });
  };

  const cancelConflicts = () => {
    useDirtyStore.getState().clearCells(conflicts.map((c) => dirtyKey(c.student_id, c.column_id)));
    setConflicts([]);
    qc.invalidateQueries({ queryKey: gridKey });
  };

  return {
    saveAll,
    acceptConflicts,
    cancelConflicts,
    conflicts,
    flash,
    isPending: mutation.isPending,
  };
};
```

In the grid page: hold the query key once (`const gridKey = getGridQueryKey({ path: …, query: … })`; use the same object shapes as the options call), call the hook, and mount in the header:

```tsx
const dirtyCount = useDirtyStore((s) => Object.keys(s.cells).length);
const save = useSaveGrid({ classId: Number(classId), subject, gridKey });
// header:
<Button
  onClick={save.saveAll}
  disabled={dirtyCount === 0 || save.isPending || data.meta.semester_status !== "open"}
>
  {save.isPending
    ? t("grid.saving")
    : save.flash
      ? t("grid.saved")
      : t("grid.saveAll", { count: dirtyCount })}
</Button>;
```

The leave-guards, in the page component:

```tsx
useBlocker({
  shouldBlockFn: () =>
    Object.keys(useDirtyStore.getState().cells).length > 0 &&
    !window.confirm(t("grid.unsavedLeave")),
});

useEffect(() => {
  const handler = (e: BeforeUnloadEvent) => {
    if (Object.keys(useDirtyStore.getState().cells).length > 0) e.preventDefault();
  };
  window.addEventListener("beforeunload", handler);
  return () => {
    window.removeEventListener("beforeunload", handler);
    useDirtyStore.getState().clearAll(); // dirty edits are per-grid; leaving discards (the blocker already asked)
  };
}, [classId, subject, t]);
```

(`useBlocker`'s exact option shape has shifted between TanStack Router minors; if the signature disagrees, its "Navigation Blocking" docs page settles it in one minute.)

**Check (limited until 2.6 exists):** edit three cells → the button reads "Save (3)"; retype one back to server value → "(2)"; try navigating to the dashboard → the confirm fires; hard-refresh → the browser's own dialog fires. Saving itself 404s; the endpoint is next.

## Step 2.6: Batch save, the algorithm the whole app pivots on

**What we're building:** `POST /classes/{id}/grid/save` implementing ARCH §3.5 exactly: per-cell structural gates, optimistic version compare, insert-vs-update paths, force semantics, one batch + audit rows per request, and a response the dialog can render verbatim. Then the tests that make it trustworthy, then the dialog.

**Why `SELECT … FOR UPDATE` + version compare (and how it relates to the WHERE-clause idiom):** ARCH teaches `UPDATE … WHERE version = :expected`: compare-and-set in one statement. Here you'll implement its equally correct sibling: lock the row (`with_for_update`), compare versions in Python, write. The row lock closes the same race the WHERE clause closes, _and_ hands you the old values for the audit entry in the same read: one trip instead of two. Say both versions of this sentence in interviews; knowing they're equivalent is the point. New cells can't be locked (no row yet), so the insert path uses Postgres's `ON CONFLICT DO NOTHING` + rowcount; a lost insert race _is_ the "two people filled an empty cell" conflict from your spec, reported, never silent.

**Layer 1 · Nudge:** gates in order: column known and active? student in this roster? value legal for the type? caller owns the role or holds a grant (admins own everything)? Reject cells structurally before touching rows; then per cell: existing row → lock, compare-or-force, write, audit; no row → conditional insert; collect three lists; one batch if anything applied; hydrate conflict author names after the loop.

**Layer 3 · Exact assembly:** append to `src/flrc/modules/grades/router.py` (new imports: `IntegrityError` not needed; add `insert as pg_insert` from the postgresql dialect, `Field` from pydantic, and `writable_semester`):

```python
class SaveCellIn(BaseModel):
    student_id: int
    column_id: int
    value: int | str | None
    expected_version: int = Field(ge=0)


class SaveRequest(BaseModel):
    subject: Subject
    force: bool = False
    cells: list[SaveCellIn] = Field(min_length=1, max_length=2000)


class AppliedOut(BaseModel):
    student_id: int
    column_id: int
    version: int


class ConflictOut(BaseModel):
    student_id: int
    student_name: str
    column_id: int
    column_label: str
    your_value: int | str | None
    current_value: int | str | None
    updated_by: str | None
    updated_at: datetime | None


class RejectedOut(BaseModel):
    student_id: int
    column_id: int
    code: str


class SaveResponse(BaseModel):
    applied: list[AppliedOut]
    conflicts: list[ConflictOut]
    rejected: list[RejectedOut]


def _valid_value(value_type: str, value: int | str | None) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if value_type == "score":
        return isinstance(value, int) and 0 <= value <= 100
    if value_type == "scale3":
        return isinstance(value, int) and 1 <= value <= 3
    return isinstance(value, str) and len(value) <= 2000


def _value_fields(value_type: str, value: int | str | None) -> dict[str, int | str | None]:
    fields: dict[str, int | str | None] = {"score": None, "scale": None, "text_value": None}
    fields[VALUE_FIELD[value_type]] = value
    return fields


async def _roster_ids(db: AsyncSession, class_id: int, subject: str, year_id: int) -> set[int]:
    q = (
        select(Student.id)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == class_id)
    )
    if subject in ("german", "french"):
        q = q.join(StudentLanguage, StudentLanguage.student_id == Student.id).where(
            StudentLanguage.year_id == year_id, StudentLanguage.language == subject
        )
    return set((await db.execute(q)).scalars().all())


@router.post("/classes/{class_id}/grid/save")
async def save_grid(
    class_id: int,
    body: SaveRequest,
    user: User = Depends(current_user),
    semester: Semester = Depends(writable_semester),
    db: AsyncSession = Depends(get_session),
) -> SaveResponse:
    cls = await db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(404, {"code": "unknown_class"})

    columns = {
        c.id: c
        for c in (
            await db.execute(
                select(ColumnDefinition).where(
                    ColumnDefinition.semester_id == semester.id,
                    ColumnDefinition.grade_level == cls.grade_level,
                    ColumnDefinition.subject == body.subject,
                    ColumnDefinition.is_active.is_(True),
                )
            )
        ).scalars()
    }
    roster = await _roster_ids(db, class_id, body.subject, cls.year_id)
    assignments = {
        a.role: a.user_id
        for a in (
            await db.execute(
                select(TeachingAssignment).where(TeachingAssignment.class_id == class_id)
            )
        ).scalars()
    }
    grants = {
        g.role: g.id
        for g in (
            await db.execute(
                select(OverrideGrant).where(
                    OverrideGrant.user_id == user.id,
                    OverrideGrant.class_id == class_id,
                    OverrideGrant.expires_at > func.now(),
                )
            )
        ).scalars()
    }

    applied: list[AppliedOut] = []
    rejected: list[RejectedOut] = []
    raw_conflicts: list[dict] = []
    audit_rows: list[AuditEntry] = []

    for cell in body.cells:
        col = columns.get(cell.column_id)
        if col is None:
            rejected.append(RejectedOut(student_id=cell.student_id, column_id=cell.column_id, code="unknown_column"))
            continue
        if cell.student_id not in roster:
            rejected.append(RejectedOut(student_id=cell.student_id, column_id=cell.column_id, code="unknown_student"))
            continue
        if not _valid_value(col.value_type, cell.value):
            rejected.append(RejectedOut(student_id=cell.student_id, column_id=cell.column_id, code="invalid_value"))
            continue
        is_owner = user.is_admin or assignments.get(col.owner_role) == user.id
        if not is_owner and col.owner_role not in grants:
            rejected.append(RejectedOut(student_id=cell.student_id, column_id=cell.column_id, code="not_owner"))
            continue
        grant_id = None if is_owner else grants.get(col.owner_role)
        fields = _value_fields(col.value_type, cell.value)

        current = (
            await db.execute(
                select(GradeValue)
                .where(
                    GradeValue.student_id == cell.student_id,
                    GradeValue.column_definition_id == cell.column_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if current is None:
            if cell.expected_version == 0 or body.force:
                stmt = (
                    pg_insert(GradeValue)
                    .values(
                        student_id=cell.student_id,
                        column_definition_id=cell.column_id,
                        version=1,
                        updated_by=user.id,
                        **fields,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["student_id", "column_definition_id"]
                    )
                    .returning(GradeValue.id)
                )
                inserted = (await db.execute(stmt)).first()
                if inserted:
                    applied.append(AppliedOut(student_id=cell.student_id, column_id=cell.column_id, version=1))
                    audit_rows.append(AuditEntry(
                        actor_id=user.id, student_id=cell.student_id,
                        column_definition_id=cell.column_id,
                        old_existed=False, old_score=None, old_scale=None, old_text=None,
                        new_score=fields["score"], new_scale=fields["scale"],
                        new_text=fields["text_value"],
                        forced=body.force and cell.expected_version != 0,
                        via_grant_id=grant_id,
                    ))
                    continue
                current = (
                    await db.execute(
                        select(GradeValue).where(
                            GradeValue.student_id == cell.student_id,
                            GradeValue.column_definition_id == cell.column_id,
                        )
                    )
                ).scalar_one()  # the racer's row; falls through to conflict
            else:
                raw_conflicts.append({
                    "cell": cell, "col": col, "current_value": None,
                    "updated_by_id": None, "updated_at": None,
                })
                continue

        if body.force or current.version == cell.expected_version:
            audit_rows.append(AuditEntry(
                actor_id=user.id, student_id=cell.student_id,
                column_definition_id=cell.column_id,
                old_existed=True, old_score=current.score, old_scale=current.scale,
                old_text=current.text_value,
                new_score=fields["score"], new_scale=fields["scale"],
                new_text=fields["text_value"],
                forced=body.force and current.version != cell.expected_version,
                via_grant_id=grant_id,
            ))
            current.score = fields["score"]           # type: ignore[assignment]
            current.scale = fields["scale"]           # type: ignore[assignment]
            current.text_value = fields["text_value"] # type: ignore[assignment]
            current.version += 1
            current.updated_by = user.id
            applied.append(AppliedOut(student_id=cell.student_id, column_id=cell.column_id, version=current.version))
        else:
            raw_conflicts.append({
                "cell": cell, "col": col,
                "current_value": cell_value(current, col.value_type),
                "updated_by_id": current.updated_by, "updated_at": current.updated_at,
            })

    if applied:
        batch = SaveBatch(user_id=user.id, class_id=class_id)
        db.add(batch)
        await db.flush()
        for entry in audit_rows:
            entry.batch_id = batch.id
            db.add(entry)
    await db.commit()

    author_ids = {c["updated_by_id"] for c in raw_conflicts if c["updated_by_id"]}
    student_ids = {c["cell"].student_id for c in raw_conflicts}
    authors = dict(
        (await db.execute(select(User.id, User.full_name).where(User.id.in_(author_ids)))).all()
    ) if author_ids else {}
    student_names = dict(
        (await db.execute(select(Student.id, Student.full_name).where(Student.id.in_(student_ids)))).all()
    ) if student_ids else {}

    conflicts = [
        ConflictOut(
            student_id=c["cell"].student_id,
            student_name=student_names.get(c["cell"].student_id, "?"),
            column_id=c["cell"].column_id,
            column_label=pick_label(c["col"].labels, "tr"),
            your_value=c["cell"].value,
            current_value=c["current_value"],
            updated_by=authors.get(c["updated_by_id"]),
            updated_at=c["updated_at"],
        )
        for c in raw_conflicts
    ]
    return SaveResponse(applied=applied, conflicts=conflicts, rejected=rejected)
```

`pnpm generate`, commit.

### 2.6.3 The tests: before the dialog, on purpose

**What / Why:** the algorithm's scary paths become executable facts. This needs a real database (locks, `ON CONFLICT`, transactions), so the harness grows: session-scoped migration onto `flrc_test`, a wipe-between-tests fixture, and a `get_session` override pointing at the test engine.

**Layer 3 · Exact assembly:** append to `tests/conftest.py`:

```python
import os
from collections.abc import AsyncIterator
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from flrc.db import models as m
from flrc.db.session import get_session

TEST_URL = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_test"
TEST_URL_SYNC = TEST_URL.replace("+asyncpg", "+psycopg")

WIPE_ORDER = (
    m.AuditEntry, m.SaveBatch, m.OverrideGrant, m.GradeValue, m.ColumnDefinition,
    m.TeachingAssignment, m.StudentLanguage, m.Enrollment, m.Student,
    m.SchoolClass, m.Semester, m.AcademicYear, m.User,
)


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    os.environ["FLRC_MIGRATIONS_URL"] = TEST_URL
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def _clean(_migrated):
    with Session(create_engine(TEST_URL_SYNC)) as db:
        for table in WIPE_ORDER:
            db.execute(delete(table))
        db.commit()


test_engine = create_async_engine(TEST_URL)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def _test_session() -> AsyncIterator[AsyncSession]:
    async with TestSession() as session:
        yield session


@pytest.fixture
def api():
    def make(user: m.User | None) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_session] = _test_session
        if user is not None:
            app.dependency_overrides[current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return make


@pytest.fixture
async def world():
    async with TestSession() as db:
        year = m.AcademicYear(label="T", status="active")
        db.add(year); await db.flush()
        sem = m.Semester(year_id=year.id, number=1, status="open")
        cls = m.SchoolClass(year_id=year.id, grade_level=5, section="A")
        db.add_all([sem, cls]); await db.flush()
        k = m.User(email="k@t", full_name="Kıvılcım")
        a = m.User(email="a@t", full_name="Armağan")
        p = m.User(email="p@t", full_name="Principal", is_admin=True)
        db.add_all([k, a, p]); await db.flush()
        db.add_all([
            m.TeachingAssignment(class_id=cls.id, role="main", user_id=k.id),
            m.TeachingAssignment(class_id=cls.id, role="skills", user_id=a.id),
        ])
        pe = m.ColumnDefinition(semester_id=sem.id, grade_level=5, subject="english",
                                value_type="score", owner_role="main",
                                labels={"tr": "PE1"}, position=1)
        rd = m.ColumnDefinition(semester_id=sem.id, grade_level=5, subject="english",
                                value_type="score", owner_role="skills",
                                labels={"tr": "Reader 1"}, position=2)
        s1 = m.Student(full_name="Öykü Bir", search_name="öykü bir")
        s2 = m.Student(full_name="Çınar İki", search_name="çınar i̇ki")
        db.add_all([pe, rd, s1, s2]); await db.flush()
        db.add_all([
            m.Enrollment(student_id=s1.id, class_id=cls.id, year_id=year.id, school_number=1),
            m.Enrollment(student_id=s2.id, class_id=cls.id, year_id=year.id, school_number=2),
        ])
        await db.commit()
        return SimpleNamespace(cls=cls.id, k=k, a=a, p=p, pe=pe.id, rd=rd.id, s1=s1.id, s2=s2.id)
```

`tests/test_save.py`:

```python
from sqlalchemy import select, update

from flrc.db import models as m
from tests.conftest import TestSession


def cell(student_id, column_id, value, expected=0):
    return {"student_id": student_id, "column_id": column_id,
            "value": value, "expected_version": expected}


async def save(api, user, class_id, cells, force=False):
    async with api(user) as client:
        return await client.post(
            f"/api/classes/{class_id}/grid/save",
            json={"subject": "english", "force": force, "cells": cells},
        )


async def test_clean_save_inserts_and_audits(api, world):
    res = await save(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    body = res.json()
    assert body["applied"] == [{"student_id": world.s1, "column_id": world.pe, "version": 1}]
    assert body["conflicts"] == [] and body["rejected"] == []
    async with TestSession() as db:
        entries = (await db.execute(select(m.AuditEntry))).scalars().all()
    assert len(entries) == 1 and entries[0].old_existed is False


async def test_stale_version_conflicts_with_author_named(api, world):
    await save(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    res = await save(api, world.p, world.cls, [cell(world.s1, world.pe, 90)])  # stale: still expects 0
    body = res.json()
    assert body["applied"] == []
    conflict = body["conflicts"][0]
    assert conflict["current_value"] == 85
    assert conflict["updated_by"] == "Kıvılcım"


async def test_force_overwrites_and_marks_forced(api, world):
    await save(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    res = await save(api, world.p, world.cls, [cell(world.s1, world.pe, 90)], force=True)
    assert res.json()["applied"][0]["version"] == 2
    async with TestSession() as db:
        forced = (await db.execute(select(m.AuditEntry).where(m.AuditEntry.forced))).scalars().all()
    assert len(forced) == 1


async def test_not_owner_rejected(api, world):
    res = await save(api, world.a, world.cls, [cell(world.s1, world.pe, 70)])
    assert res.json()["rejected"][0]["code"] == "not_owner"


async def test_locked_semester_409(api, world):
    async with TestSession() as db:
        await db.execute(update(m.Semester).values(status="locked"))
        await db.commit()
    res = await save(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "semester_locked"


async def test_invalid_value_rejected(api, world):
    res = await save(api, world.k, world.cls, [cell(world.s1, world.pe, "abc")])
    assert res.json()["rejected"][0]["code"] == "invalid_value"
```

**Check:** `uv run pytest -q`, all green (guards, migrations, six save tests). Break the version compare on purpose (`==` → `>=`), watch `test_stale_version…` fail, restore. That red run is the contract.

### 2.6.4 The conflict dialog

**What / Why:** your answer 13, rendered: every conflicted cell listed by student and column, _yours vs current_, the other author named; **Accept all** resends exactly those cells with `force=true`; **Cancel** returns them to database truth (invalidate + clear). Warning-amber, not danger-red: colleagues colliding is normal life, not an incident.

**Layer 3 · Exact assembly:** `apps/teacher/src/grid/conflict-dialog.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import type { ConflictOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@flrc/ui/components/dialog";

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

export const ConflictDialog = ({
  conflicts,
  onAccept,
  onCancel,
}: {
  conflicts: ConflictOut[];
  onAccept: () => void;
  onCancel: () => void;
}) => {
  const { t } = useTranslation();
  return (
    <Dialog
      open={conflicts.length > 0}
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-amber-700">{t("grid.conflictTitle")}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{t("grid.conflictBody")}</p>
        <ul className="max-h-64 space-y-2 overflow-y-auto text-sm">
          {conflicts.map((c) => (
            <li key={`${c.student_id}:${c.column_id}`}>
              <span className="font-medium">{c.student_name}</span> — {c.column_label}:{" "}
              {t("grid.yours")} <b>{show(c.your_value)}</b> · {t("grid.current")}{" "}
              <b>{show(c.current_value)}</b>
              {c.updated_by && <span className="text-muted-foreground"> ({c.updated_by})</span>}
            </li>
          ))}
        </ul>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            {t("grid.keepDb")}
          </Button>
          <Button className="bg-amber-600 hover:bg-amber-700" onClick={onAccept}>
            {t("grid.overwrite")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

Mount it in the grid page fed by the hook: `<ConflictDialog conflicts={save.conflicts} onAccept={save.acceptConflicts} onCancel={save.cancelConflicts} />`.

**Check, the money moment (record it):** two browser profiles. Profile A = you (Google login). Profile B needs a second real account… which you don't have, so cheat honestly for the demo: temporarily give one seeded teacher your _personal_ Gmail via psql (`update users set email='<your-gmail>' where email='teacher00@example-school.k12.tr';`) and add that Gmail as a test user in the console. The wrong-domain check blocks it, though (`hd` gate). Cleaner: flip _yourself_ between roles instead. In profile B, log in as you, but first swap the class's `main` assignment to teacher00 and grant yourself nothing; hmm, simplest of all: use the **API docs as the second writer**. In profile A, edit a cell but _don't save_. In a terminal, force the collision as the seeded main teacher via pytest's world?… Stop: the honest tool for a second human is **Playwright's bypass in Phase 4**. For _today_, the two-window demo works with A = browser, B = `psql` playing the colleague:

```sql
update grade_values set score = 90, version = version + 1,
  updated_by = (select user_id from teaching_assignments where class_id=<id> and role='main')
where student_id=<s> and column_definition_id=<c>;
```

Now press Save in profile A → the dialog lists that cell, current **90**, author named. **Overwrite** wins (version jumps again); repeat and **Keep database values** refetches 90 into the cell and drops your edit. Screen-record the second run: 30 seconds, portfolio gold. (Phase 4's two-context Playwright test makes this collision fully automatic with two real "users"; the note about why lives there.)

**If it breaks:** dialog opens but Accept silently no-ops → `acceptConflicts` built cells from an empty dirty map because Cancel-then-Accept ordering cleared it; Accept must read the dirty map _before_ clearing (the hook above does; check you didn't reorder). Conflict shows `updated_by: null` for the psql write → you set `updated_by` to a user id that isn't in `users`; the join found nobody, which is the code telling the truth.

Commit: `feat: batch save with optimistic concurrency + conflict dialog`. **DECISIONS.md** entries now, while it's hot: partial-apply over all-or-nothing · FOR-UPDATE-plus-compare vs WHERE-clause CAS (equivalent, chose the one that feeds audit) · clearing a cell nulls the field but keeps the row+version (a deliberate refinement of "empty = no row": _never-touched_ = no row; _cleared_ = null; undo and audit both need the distinction).

---

## Step 2.7: The one-hour grant

**What we're building:** the speed bump from your answer 11, end to end: first keystroke into a colleague's column opens a dialog _naming the owner_; Accept mints a one-hour permission; the columns unlock with a countdown chip; the server re-checks on every save regardless.

**Why the dialog names the owner and wears amber:** the social function is a speed bump, not a lock: helping colleagues is legitimate; mistaken columns are the enemy. Naming Kıvılcım makes the teacher _think of Kıvılcım_ for one second, which is the entire mechanism. Danger-red would tell a lie about severity. And why a Postgres row instead of a Redis TTL key, one more time out loud: expiry-by-deletion destroys the evidence, and _who had permission to touch whose columns, when_ is itself audit data (ARCH §3.5).

**Layer 1 · Nudge:** one upsert endpoint returning the expiry; the save path from 2.6 already honors live grants; you built the consumer before the producer, on purpose. Client side: a `pendingCol` state, one dialog, a chip ticking off `meta.my_grants`.

**Layer 2 · Guide (the timezone lesson hiding here):** `expires_at` compares against `func.now()` _inside Postgres_. So compute the expiry in Postgres too (`now() + interval '1 hour'`): one clock, no naive-vs-aware datetime fights between Python and asyncpg. This also means Python time-freezing libraries can't test expiry (they freeze the wrong clock); the honest test rewinds the row itself.

**Layer 3 · Exact assembly: backend** (append to `src/flrc/modules/grades/router.py`; new imports: `text` from sqlalchemy):

```python
class GrantBody(BaseModel):
    role: Literal["main", "skills", "german", "french"]


@router.post("/classes/{class_id}/grants")
async def request_grant(
    class_id: int,
    body: GrantBody,
    user: User = Depends(current_user),
    _: Semester = Depends(writable_semester),
    db: AsyncSession = Depends(get_session),
) -> GrantOut:
    if await db.get(SchoolClass, class_id) is None:
        raise HTTPException(404, {"code": "unknown_class"})
    one_hour_out = func.now() + text("interval '1 hour'")
    stmt = (
        pg_insert(OverrideGrant)
        .values(user_id=user.id, class_id=class_id, role=body.role, expires_at=one_hour_out)
        .on_conflict_do_update(
            index_elements=["user_id", "class_id", "role"],
            set_={"expires_at": one_hour_out},
        )
        .returning(OverrideGrant.expires_at)
    )
    expires_at = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return GrantOut(role=body.role, expires_at=expires_at)
```

`pnpm generate`. Then lift `cell()` and the `save()` helper out of `test_save.py` into `tests/conftest.py` (rename `save` → `save_grid`) so every grid test shares them, and add `tests/test_grants.py`:

```python
from sqlalchemy import select, text, update

from flrc.db import models as m
from tests.conftest import TestSession, cell, save_grid


async def grant(api, user, class_id, role):
    async with api(user) as client:
        return await client.post(f"/api/classes/{class_id}/grants", json={"role": role})


async def test_grant_allows_foreign_write_and_is_audited(api, world):
    res = await grant(api, world.a, world.cls, "main")
    assert res.status_code == 200
    saved = await save_grid(api, world.a, world.cls, [cell(world.s1, world.pe, 70)])
    assert saved.json()["applied"][0]["version"] == 1
    async with TestSession() as db:
        entry = (await db.execute(select(m.AuditEntry))).scalars().one()
    assert entry.via_grant_id is not None


async def test_expired_grant_is_rejected(api, world):
    await grant(api, world.a, world.cls, "main")
    async with TestSession() as db:
        await db.execute(
            update(m.OverrideGrant).values(expires_at=text("now() - interval '1 minute'"))
        )
        await db.commit()
    saved = await save_grid(api, world.a, world.cls, [cell(world.s1, world.pe, 70)])
    assert saved.json()["rejected"][0]["code"] == "not_owner"
```

(Notice what the second test does _not_ use: a time-freezing library. The check lives on Postgres's clock; rewinding the row is the only honest lever.)

**Layer 3 · Exact assembly: frontend.** `apps/teacher/src/grid/grant-dialog.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import type { GridColumnOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@flrc/ui/components/dialog";

export const GrantDialog = ({
  col,
  onAccept,
  onClose,
}: {
  col: GridColumnOut | null;
  onAccept: (role: string) => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation();
  return (
    <Dialog
      open={col !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-amber-700">{t("grid.grantTitle")}</DialogTitle>
        </DialogHeader>
        <p className="text-sm">
          {t("grid.grantBody", { name: col?.owner_name ?? "?", label: col?.label ?? "" })}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("grid.cancel")}
          </Button>
          <Button
            className="bg-amber-600 hover:bg-amber-700"
            onClick={() => col && onAccept(col.owner_role)}
          >
            {t("grid.grantAccept")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
```

Wire into the grid page: replace 2.4's toast with `setPendingCol(col)` in `LockedCell`'s `onAttempt`; add the mutation + a ticking chip:

```tsx
const [pendingCol, setPendingCol] = useState<GridColumnOut | null>(null);
const grantMutation = useMutation({
  ...requestGrantMutation(),
  onSuccess: () => {
    setPendingCol(null);
    qc.invalidateQueries({ queryKey: gridKey }); // refreshed my_grants unlock the columns
  },
});
const requestGrant = (role: string) =>
  grantMutation.mutate({ path: { class_id: Number(classId) }, body: { role: role as never } });

// countdown that also re-locks on expiry:
const [, forceTick] = useState(0);
useEffect(() => {
  const id = setInterval(() => {
    forceTick((n) => n + 1);
    const expired = data?.meta.my_grants.some((g) => new Date(g.expires_at) <= new Date());
    if (expired) qc.invalidateQueries({ queryKey: gridKey });
  }, 30_000);
  return () => clearInterval(id);
}, [data, qc, gridKey]);

const chips = data?.meta.my_grants.map((g) => {
  const mins = Math.max(0, Math.round((new Date(g.expires_at).getTime() - Date.now()) / 60_000));
  return (
    <span key={g.role} className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-800">
      {t(`roles.${g.role}`)} · {mins} {t("grid.min")}
    </span>
  );
});
// header: {chips}  ·  page bottom: <GrantDialog col={pendingCol} onAccept={requestGrant} onClose={() => setPendingCol(null)} />
```

One server nuance the naive version misses: `expires_at` arrives as a naive-UTC ISO string (no `Z`), and `new Date("…")` would read it as _local_ time. Fix at the source: teach FastAPI to serialize it honestly by declaring `GrantOut.expires_at: datetime` and appending a serializer, or simplest: change the response model field to string via `expires_at.isoformat() + "Z"` in a field_serializer. Add to `GrantOut`:

```python
from pydantic import field_serializer

class GrantOut(BaseModel):
    role: str
    expires_at: datetime

    @field_serializer("expires_at")
    def _z(self, dt: datetime) -> str:
        return dt.isoformat() + "Z"
```

(Do the same on `LastBatchOut.created_at`; same disease. This naive-UTC-plus-Z convention is a pragmatic v1 stance; note it in DECISIONS.md with the `timezone=True` column upgrade as the road not taken _yet_.)

**Check:** as yourself, open a class where you hold `main`; the skills columns wear 🔒. Press a key in one → the dialog names the skills teacher → Accept → columns unlock, chip reads "skills · 60 min", entering values works, and the audit (2.9 will show it; psql today) carries `via_grant_id`. Rewind the grant in psql (the test's `update`), wait for the 30-second tick → columns re-lock. `uv run pytest -q` → the two grant tests green.

**If it breaks:** columns never unlock after Accept → the grid invalidate used a different query-key shape than the options call. Chip shows a huge negative number → the `Z`-serializer isn't applied and your timezone is ahead of UTC, exactly the bug the serializer exists for; nice to have met it.

## Step 2.8: Undo, the audit log replayed backwards

**What we're building:** one button, "Undo my last save (12 cells, 14:02)", that restores the previous values of your most recent batch _in this class_, using the same optimistic machinery as save: cells someone else touched since are reported, never clobbered. An undo is itself a batch (`is_undo=true`), so undoing an undo is redo, for free.

**Why there's no undo storage:** the audit entries already hold `old_*` and `new_*`. Undo = "for each entry of my last batch, if the cell still shows my `new`, put back my `old`." Restoring an insert (`old_existed=false`) _deletes_ the row: true absence returns, and the grid's version-0 convention picks it up untouched (ARCH §3.5).

**Layer 1 · Nudge:** find the caller's newest batch for the class → 409 `nothing_to_undo` if none or already consumed → per entry: lock the row, value-compare against the entry's `new_*`, restore or report → wrap restorations in a new batch → mark the old one `undone`.

**Layer 2 · Guide:** the "did it change since?" check is a **value** compare, not a version compare: the entry doesn't know which version its write produced, but it knows exactly what it wrote. Extract the conflict-hydration tail of 2.6 (author + student name lookups) into a module-level `_hydrate_conflicts(db, raw)` and reuse it here; the refactor is five minutes and the reuse is the design vindicating itself.

**Layer 3 · Exact assembly** (append to `src/flrc/modules/grades/router.py`; first do the `_hydrate_conflicts` extraction so both endpoints share it):

```python
def _entry_new(entry: AuditEntry) -> tuple[int | None, int | None, str | None]:
    return (entry.new_score, entry.new_scale, entry.new_text)


def _entry_old(entry: AuditEntry) -> tuple[int | None, int | None, str | None]:
    return (entry.old_score, entry.old_scale, entry.old_text)


def _gv_tuple(gv: GradeValue) -> tuple[int | None, int | None, str | None]:
    return (gv.score, gv.scale, gv.text_value)


@router.post("/classes/{class_id}/grid/undo")
async def undo_grid(
    class_id: int,
    user: User = Depends(current_user),
    _: Semester = Depends(writable_semester),
    db: AsyncSession = Depends(get_session),
) -> SaveResponse:
    batch = (
        await db.execute(
            select(SaveBatch)
            .where(SaveBatch.user_id == user.id, SaveBatch.class_id == class_id)
            .order_by(SaveBatch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if batch is None or batch.undone:
        raise HTTPException(409, {"code": "nothing_to_undo"})

    entries = (
        await db.execute(select(AuditEntry).where(AuditEntry.batch_id == batch.id))
    ).scalars().all()

    applied: list[AppliedOut] = []
    raw_conflicts: list[dict] = []
    new_audit: list[AuditEntry] = []
    labels = {
        c.id: c.labels
        for c in (
            await db.execute(
                select(ColumnDefinition).where(
                    ColumnDefinition.id.in_({e.column_definition_id for e in entries})
                )
            )
        ).scalars()
    }

    for entry in entries:
        current = (
            await db.execute(
                select(GradeValue)
                .where(
                    GradeValue.student_id == entry.student_id,
                    GradeValue.column_definition_id == entry.column_definition_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        untouched = current is not None and _gv_tuple(current) == _entry_new(entry)
        if not untouched:
            raw_conflicts.append({
                "student_id": entry.student_id,
                "column_id": entry.column_definition_id,
                "labels": labels.get(entry.column_definition_id, {}),
                "your_value": None,
                "current_value": _first_non_null(_gv_tuple(current)) if current else None,
                "updated_by_id": current.updated_by if current else None,
                "updated_at": current.updated_at if current else None,
            })
            continue

        new_audit.append(AuditEntry(
            actor_id=user.id,
            student_id=entry.student_id,
            column_definition_id=entry.column_definition_id,
            old_existed=True,
            old_score=entry.new_score, old_scale=entry.new_scale, old_text=entry.new_text,
            new_score=entry.old_score, new_scale=entry.old_scale, new_text=entry.old_text,
            forced=False, via_grant_id=None,
        ))
        if entry.old_existed:
            current.score, current.scale, current.text_value = _entry_old(entry)  # type: ignore[assignment]
            current.version += 1
            current.updated_by = user.id
            applied.append(AppliedOut(
                student_id=entry.student_id,
                column_id=entry.column_definition_id,
                version=current.version,
            ))
        else:
            await db.delete(current)
            applied.append(AppliedOut(
                student_id=entry.student_id,
                column_id=entry.column_definition_id,
                version=0,
            ))

    batch.undone = True
    if applied:
        undo_batch = SaveBatch(user_id=user.id, class_id=class_id, is_undo=True)
        db.add(undo_batch)
        await db.flush()
        for entry in new_audit:
            entry.batch_id = undo_batch.id
            db.add(entry)
    await db.commit()

    conflicts = await _hydrate_conflicts(db, raw_conflicts)
    return SaveResponse(applied=applied, conflicts=conflicts, rejected=[])
```

(`_first_non_null` is the two-line helper picking the populated member of the value triple; `_hydrate_conflicts` is your 2.6 extraction; adjust its input to these dict keys while extracting, so both callers pass the same shape. Yes, this means revisiting 2.6's tail for ten minutes; that's what extraction means.)

`pnpm generate`. Frontend: next to Save All:

```tsx
const undo = useMutation({
  ...undoGridMutation(),
  onSuccess: (res) => {
    qc.invalidateQueries({ queryKey: gridKey }); // undo is rare; a refetch is honest here
    if (res.conflicts.length) toast.warning(t("grid.undoPartial", { count: res.conflicts.length }));
    else toast(t("grid.undone"));
  },
});
const lastBatch = data.meta.my_last_batch;
{
  lastBatch?.undoable && (
    <Button variant="outline" onClick={() => undo.mutate({ path: { class_id: Number(classId) } })}>
      {t("grid.undoLast", {
        count: lastBatch.cell_count,
        time: new Date(lastBatch.created_at).toLocaleTimeString(i18n.language, {
          hour: "2-digit",
          minute: "2-digit",
        }),
      })}
    </Button>
  );
}
```

`tests/test_undo.py`:

```python
from sqlalchemy import select

from flrc.db import models as m
from tests.conftest import TestSession, cell, save_grid


async def undo(api, user, class_id):
    async with api(user) as client:
        return await client.post(f"/api/classes/{class_id}/grid/undo")


async def test_undo_restores_previous_value(api, world):
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 90, expected=1)])
    res = await undo(api, world.k, world.cls)
    assert res.json()["applied"][0]["version"] == 3
    async with TestSession() as db:
        gv = (await db.execute(select(m.GradeValue))).scalars().one()
    assert gv.score == 85


async def test_undo_of_fresh_insert_deletes_the_row(api, world):
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    res = await undo(api, world.k, world.cls)
    assert res.json()["applied"][0]["version"] == 0
    async with TestSession() as db:
        assert (await db.execute(select(m.GradeValue))).scalars().all() == []


async def test_undo_blocked_by_later_edit_reports_conflict(api, world):
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    await save_grid(api, world.p, world.cls, [cell(world.s1, world.pe, 90)], force=True)
    res = await undo(api, world.k, world.cls)  # k's last batch is the 85-write
    body = res.json()
    assert body["applied"] == []
    assert body["conflicts"][0]["current_value"] == 90


async def test_undo_of_undo_is_redo(api, world):
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 85)])
    await save_grid(api, world.k, world.cls, [cell(world.s1, world.pe, 90, expected=1)])
    await undo(api, world.k, world.cls)   # back to 85
    await undo(api, world.k, world.cls)   # redo → 90
    async with TestSession() as db:
        gv = (await db.execute(select(m.GradeValue))).scalars().one()
    assert gv.score == 90
```

**Check:** pytest green (four new); in the browser, save three cells, press Undo: values revert, tints stay clean, the button disappears (batch consumed) and _reappears_ pointing at the undo batch itself (redo, discovered rather than built). Have psql "colleague" edit one cell between save and undo → the partial-undo toast counts it.

**If it breaks:** redo test finds score 85 → you marked the _undo_ batch `undone=True` too; only the batch being consumed flips. `version: 0` cells refuse re-entry in the UI → the grid cache still holds the old version; the invalidate-on-undo exists precisely for this.

Commit: `feat: grants + undo`.

## Step 2.9: The audit viewer

**What we're building:** the admin page that makes the whole trust story visible (every change, filterable by class/teacher/student/date, old → new, forced flag, grant reference), plus a CSV export, paged with a **keyset cursor**.

**Why keyset and not offset:** `OFFSET 5000` re-counts five thousand rows to show page 101, and rows inserted _while paging_ shift everything (the classic drift-under-writes bug). Keyset ("give me 50 rows with `id <` the last one I saw") is O(page), stable under writes, and the modern default. Your `bigint identity` ids are time-ordered, so id alone is a valid cursor; note in DECISIONS.md that non-monotonic ids would need the composite `(created_at, id)` form (ARCH §5/2.9).

**Layer 1 · Nudge:** one joined select over five tables, ordered `id DESC`, `LIMIT 51` (fetch one extra = the cheapest `has_more`), a `cursor` query param feeding `id < :cursor`; the CSV endpoint is the same query without limits, streamed.

**Layer 3 · Exact assembly:** `src/flrc/modules/audit/router.py`:

```python
import csv
import io
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import require_admin
from flrc.db.models import AuditEntry, ColumnDefinition, SaveBatch, Student, User
from flrc.db.session import get_session

router = APIRouter(prefix="/audit", tags=["audit"])

PAGE = 50


def _rendered(score: int | None, scale: int | None, text: str | None) -> str | None:
    for candidate in (score, scale, text):
        if candidate is not None:
            return str(candidate)
    return None


class AuditItemOut(BaseModel):
    id: int
    created_at: datetime
    class_id: int
    actor: str
    student: str
    column_label: str
    old_value: str | None       # None here means "cell was empty"
    new_value: str | None
    old_existed: bool
    forced: bool
    via_grant: bool


class AuditPageOut(BaseModel):
    items: list[AuditItemOut]
    next_cursor: int | None


def _base_query(
    class_id: int | None, actor_id: int | None, student_id: int | None,
    date_from: datetime | None, date_to: datetime | None,
) -> Select:
    q = (
        select(
            AuditEntry,
            SaveBatch.class_id,
            User.full_name.label("actor"),
            Student.full_name.label("student"),
            ColumnDefinition.labels,
        )
        .join(SaveBatch, SaveBatch.id == AuditEntry.batch_id)
        .join(User, User.id == AuditEntry.actor_id)
        .join(Student, Student.id == AuditEntry.student_id)
        .join(ColumnDefinition, ColumnDefinition.id == AuditEntry.column_definition_id)
        .order_by(AuditEntry.id.desc())
    )
    if class_id is not None:
        q = q.where(SaveBatch.class_id == class_id)
    if actor_id is not None:
        q = q.where(AuditEntry.actor_id == actor_id)
    if student_id is not None:
        q = q.where(AuditEntry.student_id == student_id)
    if date_from is not None:
        q = q.where(AuditEntry.created_at >= date_from)
    if date_to is not None:
        q = q.where(AuditEntry.created_at <= date_to)
    return q


def _to_item(row) -> AuditItemOut:
    entry: AuditEntry = row.AuditEntry
    return AuditItemOut(
        id=entry.id,
        created_at=entry.created_at,
        class_id=row.class_id,
        actor=row.actor,
        student=row.student,
        column_label=row.labels.get("tr", "?"),
        old_value=_rendered(entry.old_score, entry.old_scale, entry.old_text),
        new_value=_rendered(entry.new_score, entry.new_scale, entry.new_text),
        old_existed=entry.old_existed,
        forced=entry.forced,
        via_grant=entry.via_grant_id is not None,
    )


@router.get("")
async def list_audit(
    class_id: int | None = None,
    actor_id: int | None = None,
    student_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: int | None = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AuditPageOut:
    q = _base_query(class_id, actor_id, student_id, date_from, date_to)
    if cursor is not None:
        q = q.where(AuditEntry.id < cursor)
    rows = (await db.execute(q.limit(PAGE + 1))).all()
    has_more = len(rows) > PAGE
    items = [_to_item(r) for r in rows[:PAGE]]
    return AuditPageOut(items=items, next_cursor=items[-1].id if has_more and items else None)


@router.get("/export.csv")
async def export_audit_csv(
    class_id: int | None = None,
    actor_id: int | None = None,
    student_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    rows = (await db.execute(_base_query(class_id, actor_id, student_id, date_from, date_to))).all()

    def stream() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "id", "when", "class_id", "actor", "student", "column",
            "old", "new", "was_empty", "forced", "via_grant",
        ])
        for row in rows:
            item = _to_item(row)
            writer.writerow([
                item.id, item.created_at.isoformat(), item.class_id, item.actor,
                item.student, item.column_label,
                item.old_value if item.old_existed else "∅",
                item.new_value ?? "" if False else (item.new_value or ""),
                not item.old_existed, item.forced, item.via_grant,
            ])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=flrc-audit.csv"},
    )
```

One deliberate bug above: the `?? ` line is TypeScript syntax that a copy-paste habit smuggled into Python; it will not parse. Fix it yourself to `item.new_value or ""` and delete the dead branch. (Yes, this is a planted exercise: the fastest way to prove you _read_ Layer 3 instead of pasting it. From here on, assume everything, and read everything.)

Register, `pnpm generate`.

**Layer 3: the UI**, `apps/admin/src/routes/_auth/audit.tsx`, the `useInfiniteQuery` pattern (the generated helpers are single-page; infinite paging composes the generated _SDK function_ manually, a good seam to understand):

```tsx
import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listAudit, listClassesOptions } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";

export const Route = createFileRoute("/_auth/audit")({ component: AuditPage });

const AuditPage = () => {
  const { t } = useTranslation();
  const [classId, setClassId] = useState<number | undefined>();
  const { data: classes = [] } = useQuery(listClassesOptions());

  const query = useInfiniteQuery({
    queryKey: ["audit", classId],
    queryFn: async ({ pageParam }) => {
      const res = await listAudit({ query: { class_id: classId, cursor: pageParam } });
      if (res.error) throw res.error;
      return res.data!;
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const exportUrl = `/api/audit/export.csv${classId ? `?class_id=${classId}` : ""}`;

  return (
    <main className="space-y-4 p-8">
      <div className="flex items-center gap-3">
        <select
          className="rounded border p-2"
          value={classId ?? ""}
          onChange={(e) => setClassId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">{t("audit.allClasses")}</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button variant="outline" onClick={() => window.open(exportUrl)}>
          {t("audit.exportCsv")}
        </Button>
      </div>

      <table className="w-full max-w-5xl text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2">{t("audit.when")}</th>
            <th>{t("audit.actor")}</th>
            <th>{t("audit.student")}</th>
            <th>{t("audit.column")}</th>
            <th>{t("audit.change")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b last:border-0">
              <td className="py-1">{new Date(item.created_at + "Z").toLocaleString()}</td>
              <td>{item.actor}</td>
              <td>{item.student}</td>
              <td>{item.column_label}</td>
              <td>
                {item.old_existed ? (item.old_value ?? "—") : "∅"} → {item.new_value ?? "—"}
              </td>
              <td className="space-x-1">
                {item.forced && <span title={t("audit.forced")}>⚑</span>}
                {item.via_grant && <span title={t("audit.viaGrant")}>🔑</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {query.hasNextPage && (
        <Button
          variant="outline"
          onClick={() => query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
        >
          {t("audit.loadMore")}
        </Button>
      )}
    </main>
  );
};
```

**Check:** generate ~120 entries by saving in a loop from the grid (or a quick psql `insert … select`), page through with Load more; then, while a next page exists, make one _new_ save in another tab and keep paging: no row duplicates, no skips. That non-event is keyset pagination working; offset pagination would have stuttered. Open the CSV: Turkish characters intact (UTF-8), `∅` marking was-empty cells. Filter by class; the admin can now answer "who entered this 90 and when" in ten seconds. Say that sentence in the school pitch.

**If it breaks:** `SyntaxError` on the export module → you found the planted bug; well met. `created_at` renders shifted by your UTC offset → the `+ 'Z'` on the client is doing the same repair as 2.7's serializer; pick one approach (serializers server-side is the cleaner ADR) and make it uniform across `AuditItemOut` too.

## Step 2.10: The phone stepper

**What we're building:** the same grid, projected for thumbs: below 640 px (or on demand via a toggle), the class renders as _one student at a time_: their editable fields stacked as a labeled form, prev/next navigation, "7 / 30", and the same Save All in a sticky footer. Same query, same dirty store, same cells.

**Why a different projection instead of a squeezed grid:** nobody types 0-100 into a 40-px cell with thumbs. Because 2.4 kept the cells presentational and 2.5 kept unsaved edits in a store _outside_ the view, the stepper is mostly composition: switching views mid-edit keeps every dirty cell, which is the architecture demonstrating itself. Ship the manual toggle even on desktop and watch which view colleagues choose in September: that observation is a genuine "user research on a live product" interview story (ARCH §5/2.10).

**Layer 1 · Nudge:** a `useIsPhone()` matchMedia hook + a `view` state (`auto | grid | stepper`); extract the 2.4 table into `<GridTable />`; a `<StepperView />` maps one row's columns through the same cell dispatch, minus keyboard nav.

**Layer 2 · Guide:** the only refactor with teeth: 2.4's `Cell` closure captured `navKey`/`register`. Split it: a pure `cellCommit(row, col)` factory and a `CellSwitch` that takes optional nav props. Table passes nav; stepper doesn't. Locked columns render read-only in the stepper too, tapping into the same grant dialog.

**Layer 3 · Exact assembly:** the hook and the view, `apps/teacher/src/grid/stepper.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GridColumnOut, GridOut, GridRowOut } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";

export const useIsPhone = () => {
  const [phone, setPhone] = useState(() => window.matchMedia("(max-width: 639px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const onChange = (e: MediaQueryListEvent) => setPhone(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return phone;
};

export const StepperView = ({
  data,
  renderCell,
}: {
  data: GridOut;
  renderCell: (col: GridColumnOut, row: GridRowOut) => React.ReactNode;
}) => {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const row = data.rows[index];
  if (!row) return null;
  return (
    <div className="mx-auto max-w-md space-y-4 pb-24">
      <div className="flex items-center justify-between">
        <Button variant="outline" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          ← {t("stepper.prev")}
        </Button>
        <div className="text-center">
          <div className="font-semibold">{row.full_name}</div>
          <div className="text-xs text-muted-foreground">
            {index + 1} / {data.rows.length}
          </div>
        </div>
        <Button
          variant="outline"
          disabled={index === data.rows.length - 1}
          onClick={() => setIndex(index + 1)}
        >
          {t("stepper.next")} →
        </Button>
      </div>
      <div className="space-y-3">
        {data.columns.map((col) => (
          <label key={col.id} className="flex items-center justify-between gap-3">
            <span className="text-sm">
              {col.group && (
                <span className="block text-xs text-muted-foreground">{col.group}</span>
              )}
              {col.label}
            </span>
            {renderCell(col, row)}
          </label>
        ))}
      </div>
    </div>
  );
};
```

In the grid page: `const isPhone = useIsPhone();` + `const [view, setView] = useState<'auto' | 'grid' | 'stepper'>('auto');` + `const showStepper = view === 'stepper' || (view === 'auto' && isPhone);`. The header gains a small toggle button; the body renders `showStepper ? <StepperView data={data} renderCell={(col, row) => <CellSwitch col={col} row={row} />} /> : <GridTable … />`; the Save All / Undo header goes `sticky bottom-0` on phones (a `fixed inset-x-0 bottom-0 border-t bg-background p-3 sm:static sm:border-0 sm:p-0` wrapper does it). The `CellSwitch` extraction: identical body to 2.4's `Cell`, with `onNavKey`/`cellRef` passed only when the table calls it.

**Check, on your actual phone**, against the deployed preview (push the branch; Vercel gives you a preview URL): open a class, enter one full student's grades with thumbs only, tap next, rotate the phone, and nothing overflows; toggle to grid view and back, and the dirty count survives the switch (watch the badge); Save All from the sticky footer. Then the toggle on desktop: notice the stepper is… actually pleasant. File that feeling for September.

**If it breaks:** dirty cells vanish on view switch → a view is holding its own copy of values instead of reading the store (a `useState(value)` initialized once; the cells already handle this via the `useEffect` sync, so check you didn't wrap them). The fixed footer covers the last field → the stepper's `pb-24` exists for exactly that; keep them in sync.

## Step 2.11: Phase 2 test pass + exit

**Existing-checkout amendment:** the Vitest setup below is part of the original learning plan;
current teacher/admin manifests do not contain a `test` script or that test-runner dependency.
Use the implemented backend regressions and root Playwright suite. Do not install an additional
runner merely to make a historical command work. Read the app READMEs for current commands.

**What we're building:** the frontend's first tests (the three cells and the store, the pieces whose regressions would silently corrupt grades), plus the grown backend matrix, plus the exit ritual.

**Layer 3 · Exact assembly (Vitest):**

```bash
pnpm --filter @flrc/teacher add -D vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
```

In `apps/teacher/vite.config.ts` add (and a triple-slash `/// <reference types="vitest/config" />` at top):

```ts
  test: {
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
  },
```

`src/test-setup.ts`: `import '@testing-library/jest-dom/vitest';`, and set the package script `"test": "vitest run"` so Turborepo's `test` task picks it up. Two files to write:

`src/grid/dirty-store.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { dirtyKey, useDirtyStore } from "./dirty-store";

const cell = (studentId: number, columnId: number, value: number) => ({
  studentId,
  columnId,
  value,
  expectedVersion: 0,
});

describe("dirty store", () => {
  beforeEach(() => useDirtyStore.getState().clearAll());

  it("keys cells by student and column", () => {
    useDirtyStore.getState().setCell(cell(1, 2, 85));
    expect(useDirtyStore.getState().cells[dirtyKey(1, 2)]?.value).toBe(85);
  });

  it("clearCells removes exactly the given keys", () => {
    useDirtyStore.getState().setCell(cell(1, 2, 85));
    useDirtyStore.getState().setCell(cell(1, 3, 90));
    useDirtyStore.getState().clearCells([dirtyKey(1, 2)]);
    expect(Object.keys(useDirtyStore.getState().cells)).toEqual([dirtyKey(1, 3)]);
  });
});
```

`packages/ui/src/grid/cells.test.tsx` (give `packages/ui` the same dev-deps + a vitest config, or simpler: put this file in the teacher app importing from `@flrc/ui/grid/cells`; fewer configs, same coverage):

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Scale3Cell, ScoreCell } from "@flrc/ui/grid/cells";

describe("ScoreCell", () => {
  it("commits a valid integer on blur", async () => {
    const onCommit = vi.fn();
    render(<ScoreCell value={null} dirty={false} onCommit={onCommit} />);
    await userEvent.type(screen.getByRole("textbox"), "87");
    await userEvent.tab();
    expect(onCommit).toHaveBeenCalledWith(87);
  });

  it("refuses out-of-range input at the keystroke level", async () => {
    const onCommit = vi.fn();
    render(<ScoreCell value={null} dirty={false} onCommit={onCommit} />);
    const input = screen.getByRole("textbox");
    await userEvent.type(input, "1234"); // 4th digit blocked by the regex
    expect(input).toHaveValue("123");
    await userEvent.tab(); // 123 > 100 → revert, no commit
    expect(input).toHaveValue("");
    expect(onCommit).not.toHaveBeenCalled();
  });
});

describe("Scale3Cell", () => {
  it("cycles 🙁 → 😐 → 🙂 → empty", async () => {
    const onCommit = vi.fn();
    const { rerender } = render(<Scale3Cell value={null} dirty={false} onCommit={onCommit} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onCommit).toHaveBeenLastCalledWith(1);
    rerender(<Scale3Cell value={3} dirty={false} onCommit={onCommit} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onCommit).toHaveBeenLastCalledWith(null);
  });
});
```

An MSW-driven test of the whole conflict-dialog flow is the natural next rung. It's deliberately _not_ required for the phase exit (Playwright covers the flow end-to-end in Phase 4 with a real backend); if the itch strikes, mswjs.io's Vitest quickstart is a one-evening add, and the ADR either way is worth a line.

**Backend matrix growth:** add rows to `test_guards.py` for `POST /api/columns` (401 / teacher 403 / coordinator 403), `GET /api/audit` (same trio), `POST /api/classes/1/grid/save` (401), `POST /api/classes/1/grants` (401). The admin-200 cases live in the DB-backed suites already.

### Phase 2 exit checklist

- ✅ The collision screen-recording exists (browser + psql-colleague, dialog naming the author, Overwrite and Keep-database both demonstrated)
- ✅ `uv run pytest -q`: migrations + matrix + 6 save + 2 grant + 4 undo tests green; `pnpm turbo run test`: store + cell tests green
- ✅ Grant flow live: dialog names the owner, chip counts down, expiry re-locks
- ✅ Undo restores, deletes fresh inserts, reports blocked cells, and redoes
- ✅ Audit viewer pages under concurrent writes without dupes; CSV opens with Turkish intact
- ✅ Phone stepper used on a real phone; dirty count survives the view toggle
- ✅ Run the app in German for ten minutes: every string you meet is a `t()` key (leaks go on a list, fixed now, not in §4.4)
- ✅ DECISIONS.md: grants-in-Postgres · undo-as-audit-replay · FOR-UPDATE-vs-CAS equivalence · cleared-vs-never-touched · keyset pagination · naive-UTC-plus-Z serialization stance · stepper-as-projection
- ✅ `git tag phase-2 && git push --tags`

The hardest engineering in the project is now behind you. Phases 3 and 4 are broader, not deeper.

---

# Part VI. Phase 3: The admin lifecycle

**Phase goal:** by the end, the school can run the boring, consequential work around the grid without touching SQL: maintain students and teachers, move one child or thirty between classes without losing grades, switch the second language, import a hostile school workbook with a dry-run first, advance semesters and years through explicit state transitions, browse archives, and answer “what happened to this student?” from one history screen.

**The architectural relief before we start:** Phase 3 adds **no new tables**. The thirteen tables already on disk are enough. That is not an omission; it is the payoff of the domain model. Student identity is stable across years, enrollments locate students for a particular year, languages are year-scoped, grades point at students rather than classes, and users already carry active/admin/coordinator state. Every feature in this phase is a controlled mutation or projection of those facts.

**The rule for every destructive admin action:** preview first, mutate second, audit the consequential result, never infer intent from a button click alone. That means bulk moves show the exact children who will move; the importer dry-runs the same parser it later commits; closing a year requires the label typed back and the audit export fetched first.

> **Current table-first amendment (2026-08-20):** ADR-035 through ADR-037 supersede the
> original Step 3.1 and 3.3 screen assembly below. A school number now belongs to
> `Enrollment` and is unique within an academic year; `Student.id` is the stable identity. Student
> creation, number editing, class moves, second language, column setup, and class teacher assignment
> live in the `/classes` table workspace. The separate `/students` route redirects there. The old
> CRUD walkthrough remains below as design history, not as code to copy. Closing a standard year
> creates the next setup year automatically and promotes grades 1-3 and 5-7 (ADR-066) with empty numbers; activation
> requires those numbers to be filled. See the current models, migration
> `a4f93b7c2d10`, and ADRs for exact assembly.

## Step 3.1: The admin resource pattern, built once on students

**What we're building:** the first admin roster projection and the backend pattern the rest of this phase copies: year-filtered students with Turkish-safe search, create, edit, and a history link. The production UI now places these controls directly in the class table. We deliberately do **not** add “delete student”: historical identity is not disposable.

**Why students first:** this resource exercises every recurring concern at once: search, pagination, uniqueness within one academic year, forms, server validation, URL search params, empty states, and a dangerous temptation to delete. Solve that pattern once and teachers/classes become repetition instead of invention.

**Layer 1 · Nudge:** backend first: `GET /api/admin/students?year_id=&q=&cursor=&limit=` plus year/class-aware POST/PATCH. Normalize names with the same `casefold()` rule the seed used. Search by `search_name` and `Enrollment.school_number`. Frontend: the class table is the primary workspace; the standalone route may remain only as a compatibility redirect.

**Layer 2 · Guide:** keyset pagination is by `(search_name, id)`, not offset. `q` becomes `q.casefold().strip()`; if it is all digits, search the selected year's enrollment number exactly _or_ names containing the text. The API returns `next_cursor` as an opaque base64 JSON token. POST rejects a number already used in the same year with `409 duplicate_school_number`; the same number in another year is valid. PATCH updates `search_name` whenever `full_name` changes, while number edits update only the selected enrollment. The class-table row exposes Edit and History; no Delete action exists.

**Layer 3 · Exact assembly:** create `apps/backend/src/flrc/modules/administration/names.py`:

```python
import unicodedata


def search_key(value: str) -> str:
    # NFC first so visually identical Turkish names become byte-identical,
    # then casefold for İ/I/ı-safe application-side search.
    return unicodedata.normalize("NFC", value).casefold().strip()
```

Create `apps/backend/src/flrc/modules/administration/students.py`:

```python
import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth.dependencies import require_admin
from flrc.db.models import AcademicYear, Enrollment, SchoolClass, Student, User
from flrc.db.session import get_session
from flrc.modules.administration.names import search_key

router = APIRouter(prefix="/admin/students", tags=["admin-students"])


class StudentOut(BaseModel):
    id: int
    school_number: int | None
    full_name: str
    year_id: int
    class_id: int


class StudentPage(BaseModel):
    items: list[StudentOut]
    next_cursor: str | None


class StudentCreate(BaseModel):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    year_id: int
    class_id: int


class StudentPatch(BaseModel):
    school_number: int | None = Field(default=None, gt=0)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)


def encode_cursor(search_name: str, student_id: int) -> str:
    raw = json.dumps([search_name, student_id], ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[str, int]:
    try:
        padded = token + "=" * (-len(token) % 4)
        name, student_id = json.loads(base64.urlsafe_b64decode(padded))
        return str(name), int(student_id)
    except Exception as exc:
        raise HTTPException(400, {"code": "bad_cursor"}) from exc


@router.get("")
async def list_students(
    year_id: int,
    q: str = "",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StudentPage:
    stmt = (
        select(Student, Enrollment)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.year_id == year_id)
    )
    needle = search_key(q)
    if needle:
        predicates = [Student.search_name.contains(needle)]
        if needle.isdigit():
            predicates.append(Enrollment.school_number == int(needle))
        stmt = stmt.where(or_(*predicates))
    if cursor:
        last_name, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Student.search_name > last_name,
                and_(Student.search_name == last_name, Student.id > last_id),
            )
        )
    rows = (
        await db.execute(stmt.order_by(Student.search_name, Student.id).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    visible = rows[:limit]
    return StudentPage(
        items=[
            StudentOut(
                id=student.id,
                school_number=enrollment.school_number,
                full_name=student.full_name,
                year_id=enrollment.year_id,
                class_id=enrollment.class_id,
            )
            for student, enrollment in visible
        ],
        next_cursor=(
            encode_cursor(visible[-1][0].search_name, visible[-1][0].id)
            if has_more and visible
            else None
        ),
    )


@router.post("", status_code=201)
async def create_student(
    body: StudentCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StudentOut:
    school_class = await db.get(SchoolClass, body.class_id)
    year = await db.get(AcademicYear, body.year_id)
    if school_class is None or school_class.year_id != body.year_id:
        raise HTTPException(422, {"code": "invalid_class"})
    if year is None or year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    exists = await db.scalar(select(Enrollment.id).where(
        Enrollment.year_id == body.year_id,
        Enrollment.school_number == body.school_number,
    ))
    if exists is not None:
        raise HTTPException(409, {"code": "duplicate_school_number"})
    student = Student(
        full_name=body.full_name.strip(),
        search_name=search_key(body.full_name),
    )
    db.add(student)
    await db.flush()
    db.add(Enrollment(
        student_id=student.id,
        year_id=body.year_id,
        class_id=body.class_id,
        school_number=body.school_number,
    ))
    await db.commit()
    return StudentOut(
        id=student.id,
        school_number=body.school_number,
        full_name=student.full_name,
        year_id=body.year_id,
        class_id=body.class_id,
    )


@router.patch("/{student_id}")
async def patch_student(
    student_id: int,
    body: StudentPatch,
    year_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StudentOut:
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(404, {"code": "unknown_student"})
    enrollment = await db.scalar(select(Enrollment).where(
        Enrollment.student_id == student_id,
        Enrollment.year_id == year_id,
    ))
    if enrollment is None:
        raise HTTPException(404, {"code": "unknown_enrollment"})
    if body.school_number is not None and body.school_number != enrollment.school_number:
        duplicate = await db.scalar(
            select(Enrollment.id).where(
                Enrollment.year_id == year_id,
                Enrollment.school_number == body.school_number,
            )
        )
        if duplicate is not None:
            raise HTTPException(409, {"code": "duplicate_school_number"})
        enrollment.school_number = body.school_number
    if body.full_name is not None:
        student.full_name = body.full_name.strip()
        student.search_name = search_key(body.full_name)
    await db.commit()
    return StudentOut(
        id=student.id,
        school_number=enrollment.school_number,
        full_name=student.full_name,
        year_id=enrollment.year_id,
        class_id=enrollment.class_id,
    )
```

Register the router in `create_app()`, regenerate the client.

**Frontend exact shape:** create `apps/admin/src/admin/AdminPage.tsx` as the reusable shell (`title`, optional `description`, `actions`, children); `apps/admin/src/students/StudentDialog.tsx` with RHF + Zod; `apps/admin/src/routes/_authenticated/students.tsx` with typed `q` search param. Debounce only the network update, not the input itself:

```ts
const studentSchema = z.object({
  school_number: z.coerce.number().int().positive(),
  full_name: z.string().trim().min(2).max(160),
});
```

The table columns are **School no. · Full name · Actions**. Search placeholder: `t('students.search')`. Query key includes `{ q, cursor }`. Reset cursor to `undefined` whenever `q` changes. Keep a Back stack of visited cursors in component state so pagination is reversible without inventing offset math.

**Check:** create `İpek Işık`, search `ipek`, `İPEK`, `ışık`, and her numeric school number; every form finds the same row. Attempt a duplicate school number → localized 409 toast. Refresh on `?q=ipek` → the search survives because the URL owns it.

**If it breaks:** searching `ipek` misses `İpek` → an old code path still uses `.lower()` instead of `search_key()`. Page two repeats the last row → the keyset predicate must be strictly `>` and the tie-breaker must be `id > last_id`. A renamed student disappears until refresh → invalidate the student-list query after PATCH.

**Tests:** parser-free unit test for `search_key("İPEK IŞIK") == search_key("İpek Işık")`; API tests for duplicate number, missing student, keyset no-duplicate page traversal, and teacher/coordinator 403.

Commit: `feat(admin): student management pattern`.

## Step 3.2: Teachers, allowlisting, and live session revocation

**What we're building:** the user administration screen: pre-register an email before first login, edit display name/roles, deactivate a teacher, and revoke every live Redis session immediately.

**Why this is not ordinary CRUD:** `users` is both the allowlist and the authorization source.
Deactivation must be atomic from the school's point of view: the database says inactive **and**
existing sessions stop working now. Even an eight-hour cookie that ignores dismissal is not access
control.

**Layer 1 · Nudge:** POST/PATCH users, never delete them. Keep a reverse index from user id to session ids in Redis. `create_session` adds to it; logout removes; deactivation deletes every referenced session key.

**Layer 2 · Guide:** session keys become `session:<sid>`; reverse set `user_sessions:<user_id>`. When creating: pipeline `SETEX session:<sid> ...` + `SADD user_sessions:<uid> <sid>` + `EXPIRE` reverse set slightly longer than session TTL. When reading a session, reject inactive users from Postgres even if the Redis key survives. On deactivate, fetch members, delete their `session:*` keys and the set. The DB commit comes first; session revocation follows and is retried once; a stale session still fails at the `is_active` DB check.

**Layer 3 · Exact assembly (session index):** amend `src/flrc/modules/auth/sessions.py`:

```python
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


def user_sessions_key(user_id: int) -> str:
    return f"user_sessions:{user_id}"


async def create_session(user_id: int) -> str:
    sid = secrets.token_urlsafe(32)
    redis = get_redis()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.setex(session_key(sid), SESSION_TTL_SECONDS, str(user_id))
        pipe.sadd(user_sessions_key(user_id), sid)
        pipe.expire(user_sessions_key(user_id), SESSION_TTL_SECONDS + 3600)
        await pipe.execute()
    return sid


async def delete_session(session_id: str, user_id: int | None = None) -> None:
    redis = get_redis()
    await redis.delete(session_key(session_id))
    if user_id is not None:
        await redis.srem(user_sessions_key(user_id), session_id)


async def revoke_user_sessions(user_id: int) -> int:
    redis = get_redis()
    index = user_sessions_key(user_id)
    members = await redis.smembers(index)
    if not members:
        await redis.delete(index)
        return 0
    keys = [session_key(m.decode() if isinstance(m, bytes) else str(m)) for m in members]
    deleted = await redis.delete(*keys)
    await redis.delete(index)
    return int(deleted)
```

Update the current-user dependency's final gate:

```python
if user is None or not user.is_active:
    raise HTTPException(401, {"code": "not_authenticated"})
```

Create `src/flrc/modules/administration/users.py` with:

- `GET /api/admin/users?q=&active=` → paginated user rows.
- `POST /api/admin/users` body `{email, full_name, is_admin, is_coordinator}`. Lowercase/strip email; duplicate → 409.
- `PATCH /api/admin/users/{id}` body optional name/roles/active.
- Forbid deactivating yourself: `409 cannot_deactivate_self`.
- Forbid removing the final active admin: count active admins first, `409 last_admin`.
- After a successful transition `is_active: true → false`, call `revoke_user_sessions(user.id)` and return `revoked_sessions` in the response.

The critical PATCH branch:

```python
was_active = target.is_active
# apply validated changes, including the last-admin and self checks
await db.commit()
revoked = 0
if was_active and not target.is_active:
    revoked = await revoke_user_sessions(target.id)
return UserOut.from_model(target, revoked_sessions=revoked)
```

**Frontend:** `/users` table: Name · Email · Admin · Coordinator · Status · Actions. The primary button says **Allow teacher** rather than Add user; language teaches the security model. Deactivate requires a confirm dialog naming the person and saying existing sessions will be revoked. Never expose a password field; there are no passwords.

**Check:** log in as a seeded teacher in a separate browser profile. As admin, deactivate them. Refresh the teacher window → immediate 401/login, without waiting for cookie expiry. Reactivate them; they may sign in again. Try deactivating yourself and the last admin: both blocked.

**If it breaks:** old sessions keep working → the current-user dependency trusts Redis without reloading `User` from Postgres. New logins fail for an allowlisted address → email normalization differs between OAuth and admin creation; centralize `normalize_email = value.strip().casefold()`.

**Tests:** fake Redis or an isolated Redis DB for create/revoke; API test for self-deactivate, final-admin protection, role changes, and teacher/coordinator 403.

Commit: `feat(admin): teacher allowlist and session revocation`.

## Step 3.3: Classes and the assignment matrix

**What we're building:** class administration for a year plus one compact assignment matrix that answers: who owns main English, skills, German, and French for every class?

**Why the matrix, not four dialogs per class:** assignments are relational data with a uniqueness rule (`class_id + role`). The useful admin view is the whole timetable-shaped truth, not a pile of individual edit pages. Missing assignments should be visually loud before teachers discover them at grade time.

**Layer 1 · Nudge:** one classes endpoint, one teachers lookup, one bulk assignment PUT. Upsert each `(class, role)` pair; `null` means delete that assignment.

**Layer 2 · Guide:** setup/active year can be edited; archived year is read-only. Creating a class validates grade 0-8 (0 is the Hazırlık year, ADR-065), spells the section by grade (an uppercase letter, or a Turkish title-case name such as Bulut for Hazırlık), and rejects duplicate grade+section within the year. Deleting a class is allowed only in a setup year and only if it has no enrollments, save batches, or assignments; otherwise use 409 with a reason. Assignments require active users. The bulk body is a list so Save All can commit the matrix atomically.

**Layer 3 · Exact assembly (API contract):** `src/flrc/modules/administration/classes.py`:

```python
class ClassOut(BaseModel):
    id: int
    year_id: int
    grade_level: int
    section: str
    student_count: int


class ClassCreate(BaseModel):
    year_id: int
    grade_level: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=8)


class AssignmentChange(BaseModel):
    class_id: int
    role: Literal["main", "skills", "german", "french"]
    user_id: int | None


class AssignmentBulk(BaseModel):
    changes: list[AssignmentChange] = Field(max_length=500)
```

Endpoints:

```text
GET    /api/admin/years/{year_id}/classes
POST   /api/admin/classes
PATCH  /api/admin/classes/{class_id}
DELETE /api/admin/classes/{class_id}
GET    /api/admin/years/{year_id}/assignments
PUT    /api/admin/years/{year_id}/assignments
```

For the bulk PUT, start one transaction, load all referenced classes and users in two queries, reject cross-year classes or inactive users, then for each change:

```python
existing = await db.scalar(
    select(TeachingAssignment).where(
        TeachingAssignment.class_id == change.class_id,
        TeachingAssignment.role == change.role,
    )
)
if change.user_id is None:
    if existing:
        await db.delete(existing)
elif existing:
    existing.user_id = change.user_id
else:
    db.add(TeachingAssignment(
        class_id=change.class_id,
        role=change.role,
        user_id=change.user_id,
    ))
```

Commit once after the loop. Return the full fresh matrix, not just `204`; the client cache gets the server's truth in one replacement.

**Frontend:** `/classes?year=<id>` has two tabs: **Classes** and **Assignments**. The assignment tab is a table, one row per class, four combobox columns. Inactive users never appear as choices, but a stale assignment to a now-inactive user is rendered as a red chip until corrected. Local changes live in component state with a sticky **Save assignments (N)** button.

**Check:** clear 5/A's skills teacher, open teacher grid as the main teacher: skills-owned columns show no owner and cannot be requested through the grant flow until an owner exists. The UI should say “No owner assigned; contact admin.” Assign one, refresh, owner appears.

**If it breaks:** duplicate assignment rows → the bulk path inserted without first querying the unique pair. Archived year mutates → every write must call a helper that rejects `year.status == 'archived'`, not just hide buttons.

Commit: `feat(admin): classes and assignment matrix`.

## Step 3.4: Enrollment moves, bulk moves, and the L2 switch

**What we're building:** the roster operations administrators actually perform after September: move one student to another class, select many and move them together, and switch German/French for one or many students.

**Why this is the domain model's proof:** a move changes exactly one `enrollments.class_id`. Grade rows do not move, copy, or rewrite because they never referenced the class. This step is where invariant #1 stops being architecture prose and becomes a five-second operation with zero grade loss.

**Layer 1 · Nudge:** roster endpoint returns enrollment + language. Move endpoint takes student ids and target class. Language endpoint upserts/deletes year-scoped `StudentLanguage`. Validate same year and grade compatibility.

**Layer 2 · Guide:** permit same-grade moves by default. Cross-grade moves require `allow_grade_change=true` and a second confirm because column sets differ. Moving to the current class is a no-op. Bulk mutation is all-or-nothing. L2 supports `german`, `french`, or `null`; null removes the language row. The school programme starts L2 in Grade 4. Use the shared `academics/programme.py` constant for roster editing and synthetic data. Grades 1-3 reject new L2 assignments; clearing an existing selection is always allowed in a writable year.

**Layer 3 · Exact assembly (service first):** `src/flrc/modules/administration/roster_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import Enrollment, SchoolClass


async def move_students(
    db: AsyncSession,
    *,
    student_ids: list[int],
    target_class: SchoolClass,
    allow_grade_change: bool,
) -> tuple[int, int]:
    enrollments = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.student_id.in_(student_ids),
                Enrollment.year_id == target_class.year_id,
            )
        )
    ).scalars().all()
    if len(enrollments) != len(set(student_ids)):
        raise ValueError("student_not_enrolled_in_year")

    source_ids = {e.class_id for e in enrollments}
    source_classes = {
        c.id: c
        for c in (
            await db.execute(select(SchoolClass).where(SchoolClass.id.in_(source_ids)))
        ).scalars()
    }
    if not allow_grade_change and any(
        source_classes[e.class_id].grade_level != target_class.grade_level
        for e in enrollments
    ):
        raise ValueError("grade_change_requires_confirmation")

    changed = 0
    unchanged = 0
    for enrollment in enrollments:
        if enrollment.class_id == target_class.id:
            unchanged += 1
        else:
            enrollment.class_id = target_class.id
            changed += 1
    return changed, unchanged
```

API contracts in `src/flrc/modules/administration/roster.py`:

```python
class MoveBody(BaseModel):
    student_ids: list[int] = Field(min_length=1, max_length=200)
    target_class_id: int
    allow_grade_change: bool = False


class LanguageBody(BaseModel):
    student_ids: list[int] = Field(min_length=1, max_length=200)
    language: Literal["german", "french"] | None
```

Endpoints:

```text
GET  /api/admin/classes/{class_id}/roster
POST /api/admin/roster/move
PUT  /api/admin/years/{year_id}/student-language
DELETE /api/admin/classes/{class_id}/roster/{student_id}
```

For language upsert, preload existing rows into `{student_id: row}`. For each student: delete if `language is None`; update if row exists; otherwise insert. Validate every student has an enrollment in that year.

**Frontend:** class roster table gains checkboxes. Toolbar appears only when selection is nonempty: **Move N students · Set second language**. The single-row action uses the same dialogs with one id; no parallel code paths. Before cross-grade move, the dialog states: “Grades are retained on the student record, but the destination grade may use different columns.”

**Class-table removal and column placement (ADR-048):** a Remove tab lists students and all assessment columns for the selected grade, subject, and semester. Student removal confirms the current class/year, removes only that enrollment and its year-scoped L2 choice, and preserves the student, other years, saved grades, and grade audit rows. Archived years reject it. Column removal uses the existing delete-or-disable API and states that columns are shared across the grade. Column-header handles support drag placement; arrow controls remain available for keyboard/touch. Reorder sends the complete column set for one grade/subject/semester, including inactive definitions except programme-ineligible middle-English text fields under
ADR-063, and rejects duplicate, partial, or mixed-scope lists.

**Check (prove the invariant):** enter three grades for a student in 5/A. Move them to 5/B. Open 5/B's same subject grid: the grades are there. Move back: still there. Switch German → French: the English grades remain; German grid drops the student; French grid gains them.

**If it breaks:** moved student appears in both classes → you inserted a second enrollment instead of updating the year-unique one. Grades vanish → some query still filters grade values by class identity instead of deriving the roster first and then fetching by student ids.

**Tests:** one move retains `grade_values` ids/versions unchanged; bulk rollback on one invalid student; same-class no-op; L2 switch; cross-grade confirmation gate.

Commit: `feat(admin): roster moves and second-language switching`.

## Step 3.5: The year and semester state machine

**What we're building:** the lifecycle screen and the transition endpoints that turn `setup → active → archived` and `semester open ↔ locked` into explicit business operations rather than direct status edits.

**Why a state machine instead of PATCH status:** lifecycle transitions have side effects and invariants. “Open semester 2” means semester 1 locks, exactly one semester is open, the year must be active, and every write guard changes behavior instantly. A generic status dropdown hides all of that.

**Layer 1 · Nudge:** no `PATCH /years/{id}` for status. Use verb endpoints: create setup year, activate, advance semester, reopen, close year. Centralize transition logic in a service and lock the year row `FOR UPDATE`.

**Layer 2 · Guide (legal transitions):**

- Create year → `setup`; both semester rows exist and are `locked`.
- Activate setup year → previous active year must be archived or absent; semester 1 becomes `open`.
- Advance from semester 1 → lock 1, open 2.
- Lock semester 2 → both locked; year remains active until explicit close-year.
- Reopen a semester → admin only, year active, lock the other semester first; the UI labels this exceptional.
- Close year → both semesters must be locked; year becomes `archived`; no grade/admin mutations thereafter. For a standard `YYYY-YYYY` label, the same transaction idempotently creates the next setup year, copies semesters/classes/columns/assignments, promotes grades 1-3 and 5-7 (Hazırlık and grade 4 pupils await the school's placement through the roster import, ADR-066), preserves language, and assigns fresh sequential year-scoped school numbers.

**Layer 3 · Exact assembly:** `src/flrc/modules/administration/lifecycle_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import AcademicYear, Semester


class LifecycleError(ValueError):
    pass


async def lock_year(db: AsyncSession, year_id: int) -> AcademicYear:
    year = await db.scalar(
        select(AcademicYear).where(AcademicYear.id == year_id).with_for_update()
    )
    if year is None:
        raise LifecycleError("unknown_year")
    return year


async def semesters_for_update(db: AsyncSession, year_id: int) -> list[Semester]:
    return list((await db.execute(
        select(Semester)
        .where(Semester.year_id == year_id)
        .order_by(Semester.number)
        .with_for_update()
    )).scalars())
```

`src/flrc/modules/administration/lifecycle.py` exposes:

```text
GET  /api/admin/years
POST /api/admin/years                         {label}
POST /api/admin/years/{id}/activate
POST /api/admin/years/{id}/advance-semester
POST /api/admin/years/{id}/lock-semester-2
POST /api/admin/years/{id}/reopen-semester    {number, confirm_label}
```

Creation:

```python
year = AcademicYear(label=body.label.strip(), status="setup")
db.add(year)
await db.flush()
db.add_all([
    Semester(year_id=year.id, number=1, status="locked"),
    Semester(year_id=year.id, number=2, status="locked"),
])
await db.commit()
```

Activation runs inside one transaction, rejects another `active` year, and sets semester 1 open. Advance locks 1 and opens 2. Reopen requires `body.confirm_label == year.label` and logs a structured event `semester_reopened` with actor/year/semester; no student values in logs.

**Frontend:** `/lifecycle` renders years as cards with a vertical state timeline. Only legal next actions are buttons. Exceptional reopen sits behind a Danger Zone accordion and typed confirmation. Show counts before transitions: classes, students, filled cells, unfilled cells. That count is informational, not a blocker; schools may intentionally leave cells blank.

**Guard hardening:** update every Phase-3 write helper to reject archived years. Keep `writable_semester` as the grade-write gate. Add `writable_year` to roster, classes, assignments, importer commit.

**Check:** activate a setup year; semester 1 opens. Save a grade. Advance semester; the old grid becomes read-only and semester 2 columns become current. Reopen 1; only 1 is open. Try two concurrent activation requests against two setup years: one wins, one 409s.

**If it breaks:** both semesters open → lock the pair before opening the selected semester and retain the partial unique index on `semesters(year_id) WHERE status='open'`. Two active years → add a partial unique index in a migration **only if your concurrency test proves the service lock cannot protect across different year rows**; the preferred database belt-and-braces form is `CREATE UNIQUE INDEX ... ON academic_years ((status)) WHERE status='active'`.

Commit: `feat(admin): explicit academic lifecycle state machine`.

## Step 3.6: Build the hostile Excel fixture before the importer

**What we're building:** a deterministic workbook generator that creates the ugly input you expect from real school exports: title rows, merged cells, inconsistent headers, blank lines, formula-like school numbers, footer totals, one sheet named `5/A`, another with a class column, and a gender column that the parser intentionally discards.

**Why fixture-first:** importers fail on files, not abstractions. A synthetic hostile workbook gives you a permanent regression suite without committing real student data; the project's synthetic-only rule stays intact.

**Layer 1 · Nudge:** `openpyxl.Workbook()`, two sheets, deliberately inconsistent shapes, fixed fake names/numbers, then a Typer command.

**Layer 2 · Guide:** create `tests/fixtures/roster-hostile.xlsx` from code, not by hand, so it is reproducible. Include these cases:

- title rows before headers;
- `Okul No`, `Öğrenci No`, `Numara` synonyms;
- separate `Sınıf` + `Şube` and combined `Sınıf/Şube`;
- `Almanca`, `Fransızca`, blank language;
- a duplicate school number with identical data (warning, de-duplicate);
- a duplicate school number with conflicting class (error);
- footer text `Toplam 28 öğrenci`;
- gender column `Cinsiyet` present and ignored.

**Layer 3 · Exact assembly:** `src/flrc/modules/imports/fixture.py`:

```python
from pathlib import Path

from openpyxl import Workbook


def make_hostile_fixture(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "5/A"
    ws.merge_cells("A1:F1")
    ws["A1"] = "2026-2027 ÖĞRENCİ LİSTESİ"
    ws.append([])
    ws.append(["Sıra", "Okul No", "Ad Soyad", "Cinsiyet", "Yabancı Dil"])
    ws.append([1, 51001, "İpek Işık", "K", "Almanca"])
    ws.append([2, 51002, "Çağrı Şen", "E", "Fransızca"])
    ws.append([3, 51003, "Öykü Akın", "K", None])
    ws.append([])
    ws.append([None, None, "Toplam 3 öğrenci"])

    mixed = wb.create_sheet("Karma Liste")
    mixed.append(["Kurum raporu — otomatik dışa aktarım"])
    mixed.append([])
    mixed.append(["Öğrenci No", "Öğrenci Adı Soyadı", "Sınıf/Şube", "2. Yabancı Dil"])
    mixed.append([61001, "Yağız Efe", "6/B", "DE"])
    mixed.append([61002, "Gökçe Arı", "6-B", "FR"])  # legacy delimiter: parser accepts it

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
```

Add `openpyxl` if you have not already: `uv add openpyxl python-multipart`. Add Typer command:

```python
@app.command("make-import-fixture")
def make_import_fixture(out: Path = Path("tests/fixtures/roster-hostile.xlsx")) -> None:
    make_hostile_fixture(out)
    typer.echo(f"wrote {out}")
```

**Check:** `uv run flrc make-import-fixture && unzip -l tests/fixtures/roster-hostile.xlsx | head`; an xlsx is a zip, and the command proves you generated a real workbook. Open it once in LibreOffice/Excel and smile at the mess.

**If it breaks:** openpyxl refuses a filename → ensure parent directory exists. The workbook opens repaired → a merged range was populated in a non-top-left cell; only write the anchor.

Commit: `test(importer): hostile synthetic workbook fixture`.

## Step 3.7: The importer parser, normalizing hostile input into typed rows

**What we're building:** a pure parser whose only job is `bytes → ImportPlan`. It finds headers, normalizes Turkish variants, parses classes/languages, skips footers, and returns precise cell-addressed errors and warnings. It does not touch the database.

**Why pure first:** database code obscures parsing bugs. A pure function is cheap to test with ten malformed workbooks and safe to run in dry-run and commit identically. The parser's contract is the security boundary: after it returns a typed `RowModel`, later code stops asking whether a school number is secretly `51001.0` or a class is `5 / A`.

**Layer 1 · Nudge:** read-only workbook, scan first 25 rows for a header set, map synonyms to canonical names, parse each subsequent row until footer heuristics fire, validate through Pydantic.

**Layer 2 · Guide (canonical fields):** `school_number`, `full_name`, `grade_level`, `section`, `language`. Required: number and name. Class may come from sheet title (`5/A`) or cells. Language optional. Gender is never mapped. Keep source location on each row (`sheet`, `row_number`) for errors. The canonical display delimiter is `/`; the importer still accepts `-` in hostile or legacy input.

**Layer 3 · Exact assembly:** create `src/flrc/modules/imports/parser.py`:

```python
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass

from openpyxl import load_workbook
from pydantic import BaseModel, Field, ValidationError

from flrc.modules.administration.names import search_key

HEADER_ALIASES = {
    "school_number": {"okul no", "öğrenci no", "ogrenci no", "numara", "no"},
    "full_name": {"ad soyad", "adı soyadı", "öğrenci adı soyadı", "ogrenci adi soyadi"},
    "class_combined": {"sınıf/şube", "sinif/sube", "sınıf şube", "class"},
    "grade_level": {"sınıf", "sinif"},
    "section": {"şube", "sube"},
    "language": {"yabancı dil", "2. yabancı dil", "ikinci yabancı dil", "l2"},
}
FOOTER_WORDS = ("toplam", "sınıf mevcudu", "sinif mevcudu", "öğrenci sayısı")
CLASS_RE = re.compile(r"^\s*([1-8])\s*[-/]?\s*([A-Za-zÇĞİÖŞÜçğıöşü])\s*$")


class RowModel(BaseModel):
    school_number: int = Field(gt=0)
    full_name: str = Field(min_length=2, max_length=160)
    grade_level: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=8)
    language: str | None = None
    sheet: str
    row_number: int


class ImportIssue(BaseModel):
    level: str  # error | warning
    code: str
    sheet: str
    cell: str | None = None
    message: str


class ImportPlan(BaseModel):
    sha256: str
    rows: list[RowModel]
    issues: list[ImportIssue]

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)


def norm(value: object) -> str:
    return search_key(str(value or "")).replace("\n", " ")


def header_map(values: list[object]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, raw in enumerate(values):
        value = norm(raw)
        for canonical, aliases in HEADER_ALIASES.items():
            if value in aliases:
                found[canonical] = index
    return found


def parse_class(value: object) -> tuple[int, str] | None:
    match = CLASS_RE.match(str(value or ""))
    if not match:
        return None
    return int(match.group(1)), match.group(2).upper()


def parse_language(value: object) -> str | None:
    key = norm(value)
    if not key:
        return None
    if key in {"almanca", "de", "german", "deutsch"}:
        return "german"
    if key in {"fransızca", "fransizca", "fr", "french", "français"}:
        return "french"
    raise ValueError("unknown_language")
```

Continue with the parser body:

```python
def parse_workbook(data: bytes) -> ImportPlan:
    digest = hashlib.sha256(data).hexdigest()
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows: list[RowModel] = []
    issues: list[ImportIssue] = []

    for ws in wb.worksheets:
        default_class = parse_class(ws.title)
        header_row = None
        mapping: dict[str, int] = {}
        for row_no, row in enumerate(ws.iter_rows(min_row=1, max_row=25, values_only=True), 1):
            candidate = header_map(list(row))
            if "school_number" in candidate and "full_name" in candidate:
                header_row, mapping = row_no, candidate
                break
        if header_row is None:
            issues.append(ImportIssue(
                level="warning", code="sheet_without_headers", sheet=ws.title,
                message="No recognizable student table found; sheet skipped.",
            ))
            continue

        for row_no, cells in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=False), header_row + 1):
            values = [c.value for c in cells]
            joined = " ".join(norm(v) for v in values if v is not None)
            if not joined:
                continue
            if any(word in joined for word in FOOTER_WORDS):
                continue

            def at(name: str) -> object:
                idx = mapping.get(name)
                return values[idx] if idx is not None and idx < len(values) else None

            number_raw = at("school_number")
            name_raw = at("full_name")
            if number_raw in (None, "") and name_raw in (None, ""):
                continue
            try:
                number = int(float(str(number_raw).replace(",", ".")))
                if float(str(number_raw).replace(",", ".")) != number:
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(ImportIssue(
                    level="error", code="bad_school_number", sheet=ws.title,
                    cell=cells[mapping["school_number"]].coordinate,
                    message=f"School number is not an integer: {number_raw!r}",
                ))
                continue

            cls = default_class
            if "class_combined" in mapping:
                cls = parse_class(at("class_combined"))
            elif "grade_level" in mapping and "section" in mapping:
                cls = parse_class(f"{at('grade_level')}/{at('section')}")
            if cls is None:
                issues.append(ImportIssue(
                    level="error", code="bad_class", sheet=ws.title,
                    cell=cells[mapping.get("class_combined", mapping.get("grade_level", 0))].coordinate,
                    message="Could not determine grade and section.",
                ))
                continue

            try:
                language = parse_language(at("language")) if "language" in mapping else None
                rows.append(RowModel(
                    school_number=number,
                    full_name=str(name_raw or "").strip(),
                    grade_level=cls[0], section=cls[1], language=language,
                    sheet=ws.title, row_number=row_no,
                ))
            except (ValidationError, ValueError) as exc:
                issues.append(ImportIssue(
                    level="error", code="row_validation", sheet=ws.title,
                    cell=f"A{row_no}", message=str(exc),
                ))

    deduped: dict[int, RowModel] = {}
    for row in rows:
        previous = deduped.get(row.school_number)
        if previous is None:
            deduped[row.school_number] = row
            continue
        same = (
            search_key(previous.full_name) == search_key(row.full_name)
            and previous.grade_level == row.grade_level
            and previous.section == row.section
            and previous.language == row.language
        )
        issues.append(ImportIssue(
            level="warning" if same else "error",
            code="duplicate_identical" if same else "duplicate_conflict",
            sheet=row.sheet,
            cell=f"A{row.row_number}",
            message=f"School number {row.school_number} appears more than once.",
        ))

    return ImportPlan(sha256=digest, rows=list(deduped.values()), issues=issues)
```

**Tests before API:** build tiny workbooks in memory for every alias; test title-derived class; combined class; unknown language; decimal school number; footer skip; duplicate identical warning; duplicate conflicting error; gender ignored. Real fixture parses to exactly five valid rows and no errors.

**Check:** `uv run pytest -q tests/test_importer.py` green. Print the plan once and verify every issue includes a human source location.

**If it breaks:** `ReadOnlyCell` has no coordinate in your openpyxl version → iterate normal cells or construct `get_column_letter(index + 1) + str(row_no)`. `51001` becomes `51001.0` → the explicit integer equivalence check is load-bearing.

Commit: `feat(importer): pure hostile-workbook parser`.

## Step 3.8: Dry-run → commit (one parser, two endpoints, zero surprises)

**What we're building:** the admin import workflow. Upload for a dry-run, inspect exactly what will create/update/move, then commit **the same bytes** by hash. Review the whole roster through scrolling pages, filter by grade/class, and stage class moves, additions, exclusions, or second-language edits before committing. The server reparses the original file and validates the separate, narrowly typed draft operations (ADR-048).

**Why the hash handshake:** a preview is only meaningful if commit applies the file that produced it. Trusting a replacement row list would bypass the parser. Re-uploading the original file keeps parsing authoritative, while a second digest binds the reviewed file, target year, and all validated draft operations.

**Layer 1 · Nudge:** two multipart endpoints, same `read_limited_xlsx()` helper, same parser. Dry-run compares plan to DB. Commit rejects parser errors and SHA mismatch, then creates classes/students, updates names, moves enrollments, and upserts languages in one transaction.

**Layer 2 · Guide (preview counts):** `new_students`, `renamed_students`, `new_classes`, `new_enrollments`, `moved_students`, `language_changes`, `unchanged`, plus issues. Counts cover the entire workbook. Each preview page contains up to 100 normalized rows by default, per-row actions, `total_rows`, `filtered_rows`, `next_offset`, and class counts. Scrolling requests subsequent pages. Search, grade, section, language, and action filters run on the full parsed roster before pagination. Max file size 10 MiB; extension and ZIP signature checked.

**Layer 3 · Exact assembly:** `src/flrc/modules/imports/router.py`:

```python
MAX_XLSX_BYTES = 10 * 1024 * 1024


async def read_limited_xlsx(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(415, {"code": "xlsx_required"})
    data = await file.read(MAX_XLSX_BYTES + 1)
    if len(data) > MAX_XLSX_BYTES:
        raise HTTPException(413, {"code": "file_too_large"})
    if not data.startswith(b"PK"):
        raise HTTPException(415, {"code": "bad_xlsx_container"})
    return data
```

Contracts:

```text
POST /api/admin/import/dry-run?year_id=123&offset=0&limit=100
  optional query filters: q, grade_level, section, language, action
  multipart: file, class_moves (JSON string, defaults to []), roster_edits (JSON object, defaults to {})

POST /api/admin/import/commit?year_id=123&expected_sha256=<file digest>&expected_review_sha256=<review digest>
  multipart: file, class_moves, roster_edits (the same reviewed JSON)
```

Create an `ImportPreview` model with counts, `sha256`, issues, row actions. Implement one comparison function `compare_plan(db, year_id, plan) -> ImportPreview`; commit calls it again inside the transaction and then applies exactly those actions.

Class moves are narrowly scoped overrides: each contains a school number already present in the parsed file and a destination grade/section present in the file or selected year's classes. Reject unknown students, duplicate overrides, unknown classes, invalid grades, and extra fields. `roster_edits` adds typed `additions`, `removed_school_numbers`, and `language_changes`. Additions require a positive year-specific number, nonblank name, known class, and a valid optional language; they cannot rename a differently named enrolled student. Exclusions and language edits must reference known draft rows. Extra fields and duplicate operations are rejected. Excluding a file row skips it; it does not delete an existing enrollment. Both endpoints apply the same validation. `review_sha256` binds the file digest, target year, sorted moves, additions, exclusions, and language edits; commit rejects a stale review. Legacy file-only commits remain supported. See ADR-047 and ADR-048.

Core commit order:

1. `writable_year`/admin gate; year may be `setup` or `active`, never archived.
2. Parse; reject `plan.has_errors` with 422 and the full issue list.
3. Compare SHA to `expected_sha256` using `hmac.compare_digest`.
4. Lock the year row `FOR UPDATE` so two imports cannot interleave.
5. Create missing classes and flush so ids exist.
6. Load students by school number. Insert missing; update normalized names only when changed.
7. Load year enrollments; insert or update `class_id`.
8. Upsert/delete `StudentLanguage` to match the file's explicit language value.
9. Commit once.
10. `structlog.info("import_committed", actor_id=..., year_id=..., sha256=..., counts=...)`: counts only, never names.

**Important language rule:** an empty language cell is authoritative **only if the workbook had a recognized language column**. When the workbook has no language column at all, leave existing language records untouched. Add `language_present: bool` to the normalized row or plan metadata so absence and blank are not conflated.

**Frontend:** `/import` is a three-state page: Choose file → Preview → Result. Keep the `File` object in React state, server-reviewed pages in TanStack Query, and all unsaved roster edits with undo history in a per-review Zustand store. The left grade selector immediately filters all classes in that grade. Class targets support both click-to-filter and drag-to-move; each row also has a class selector for keyboard/touch access, a second-language selector with an empty option, and an exclusion button. An add-student form stages a new row. The table follows the page scroll and loads more near its end. Changing file/year clears the draft. Commit is disabled during review refreshes, after errors, and for an empty roster. Send the same `File`, both digests, and all reviewed draft operations. Filters affect only the view, never which students are committed. After success, invalidate affected caches and show one durable result card with counts.

**Check (the money run):** upload the hostile fixture. Preview names the sheets/cells, says exactly what will be created, and ignores gender. Commit. Upload the same file again: preview should be almost entirely `unchanged`; commit should produce no duplicate students or enrollments. Modify one class in the workbook and dry-run → one move.

**If it breaks:** second import duplicates rows → you keyed by workbook row identity instead of school number/year unique constraints. Commit differs from preview → compare logic was duplicated; both endpoints must call the same function. Existing L2 disappears from a workbook without an L2 column → you collapsed “column absent” into “blank cell.”

**Tests:** dry-run never writes; SHA mismatch 409; parser error 422; idempotent second commit; move preserves grades; transaction rollback on forced failure after student creation; 10 MiB+1 rejected.

Commit: `feat(admin): dry-run and idempotent roster importer`.

## Step 3.9: Audit export and the close-year ceremony

**What we're building:** a complete year audit CSV plus the final state transition to archive. Closing is intentionally ceremonial: export first, inspect/retain it, then type the year label to close.

**Why:** archival is where “we can undo it later” stops being an acceptable operating model. The database remains the source of truth, but a portable UTF-8 CSV of every grade mutation is the school's independent receipt.

**Layer 1 · Nudge:** stream CSV, prepend UTF-8 BOM for Excel, deterministic order by audit id, SHA-256 header. Close endpoint accepts that digest and typed year label, verifies both semesters locked, then archives.

**Layer 2 · Guide:** export columns: audit id, timestamp, actor email/name, student school number/name, class-at-time-of-export if enrolled in that year, column labels/subject/type, old value, new value, forced, grant id, batch id. Do not include session ids or OAuth claims. The SHA is over the exact response bytes.

**Layer 3 · Exact assembly:** `GET /api/admin/years/{year_id}/audit-export.csv` builds rows with joined SQL and `csv.writer`. Start text with `\ufeff`; encode UTF-8; compute digest; return:

```python
return Response(
    content=payload,
    media_type="text/csv; charset=utf-8",
    headers={
        "Content-Disposition": f'attachment; filename="flrc-audit-{year.label}.csv"',
        "X-Audit-SHA256": hashlib.sha256(payload).hexdigest(),
    },
)
```

Close body:

```python
class CloseYearBody(BaseModel):
    confirm_label: str
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
```

Close algorithm:

- lock year and semesters;
- require `status == active`;
- require both semesters `locked`;
- require exact `confirm_label`;
- regenerate the audit export bytes **inside the close request** and compare digest (yes, this is extra work; it proves the supplied export still matches current audit state);
- set year archived, commit;
- structured log `year_archived` with actor/year/digest/counts.

After the archive write, invoke the rollover service before commit. Never copy grade values, audit rows, or old school numbers. Grade 8 has no next-year enrollment, and Hazırlık and grade 4 pupils wait for the roster import to place them by name (ADR-066). Assign promoted enrollments deterministic fresh numbers from 1 upward; activation retains the `student_numbers_incomplete` guard for manually cleared or incomplete imported numbers.

**Frontend:** lifecycle card's final button opens a three-step dialog: Download audit CSV → checkbox “I stored the export” → type year label → Archive. Read `X-Audit-SHA256` from the response and hold it in dialog state; no export, no close button. On success, surface the generated setup year and link directly to its class tables so the admin can fill new numbers.

**Check:** add one last grade after downloading the export but before close (reopen semester briefly in local dev). Attempt close with old digest → 409 `audit_changed_since_export`. Download again, lock, close succeeds. All write endpoints against that year now 409 read-only.

**If it breaks:** browser cannot read `X-Audit-SHA256` in a cross-origin deployment → same-origin proxy avoids CORS exposure; if you abandon the proxy later, expose the header explicitly. CSV mojibake in Excel → BOM missing.

Commit: `feat(admin): audit export and close-year ceremony`.

## Step 3.10: Archive browsing and student history

**Pending 2026-09-11 correction:** admin/archive year lists order by descending year label;
student history orders ascending. Database insertion ids are not academic chronology. Review
nonstandard labels explicitly. ADR-063 omits retired middle-English comments from archive/history
projections without deleting historical grade or audit records.

**What we're building:** read-only views for old years plus a student timeline that survives moves, renames, language switches, and new academic years.

**Why:** an archive that exists only in SQL is not an archive staff can use. The same domain model that made moves safe also makes history straightforward: stable student id, one enrollment per year, year-scoped language, semester-scoped columns, and grade values attached to the stable student.

**Layer 1 · Nudge:** reuse projections, not mutations. Archive endpoints return years/classes/grid snapshots. Student history groups by year → semesters → subjects and includes enrollment/language metadata.

**Layer 2 · Guide:** do not call the live `get_grid()` route handler from another route. Extract a service `build_grid_snapshot(...)` that both live grid and archive browser can call with an explicit semester and `read_only=True`. This prevents the archive from inheriting “choose current open semester” behavior.

**Layer 3 · Exact assembly (endpoints):** `src/flrc/modules/archive/router.py` guarded by `require_coordinator_or_admin`:

```text
GET /api/archive/years
GET /api/archive/years/{year_id}/classes
GET /api/archive/classes/{class_id}/grid?semester=1&subject=english&locale=tr
GET /api/archive/students/{student_id}/history
```

History output shape:

```python
class HistoryCell(BaseModel):
    column_id: int
    label: str
    subject: str
    value_type: str
    value: int | str | None


class HistorySemester(BaseModel):
    number: int
    status: str
    cells: list[HistoryCell]


class HistoryYear(BaseModel):
    year_id: int
    label: str
    year_status: str
    class_name: str | None
    language: str | None
    semesters: list[HistorySemester]


class StudentHistoryOut(BaseModel):
    student_id: int
    school_number: int
    full_name: str
    years: list[HistoryYear]
```

Query strategy: fetch the student; all enrollments joined to year/class; all language rows; all grade values joined to column→semester→year; assemble in Python dictionaries. This is a history page for one child, not a million-row analytics endpoint; clarity beats one monstrous JSON aggregation.

**Frontend:** `/archive` starts with year cards, drills to classes and read-only grids. `/students/$studentId/history` shows a timeline. Link to History from live roster, student list, and archive. Every archived screen carries a permanent **Read only** badge; no disabled edit controls pretending to be interactive.

**Check:** a student moved 5/A → 5/B midyear still shows one year entry with the current class and all grade values. After closing the year and creating the next, the same student history gains a second year rather than a second identity.

**If it breaks:** archived grid shows semester 2 when you ask for 1 → a helper still auto-selects “open else max.” Archive service must take an explicit semester id/number. Student appears twice → importer created a new student because school number matching drifted.

Commit: `feat(admin): archive browser and student history`.

## Step 3.11: Coordinator surfaces (overview, completeness, and exceptions)

**What we're building:** a coordinator dashboard that answers operational questions without granting admin powers: Which classes are incomplete? Which teacher assignments are missing? Which report sets are ready? Which recent saves/conflicts deserve attention?

**Why separate coordinator from admin:** observation and intervention are not the same permission. Coordinators need school-wide visibility and later report generation; they do not need to allowlist accounts, move rosters, or reopen semesters.

**Layer 1 · Nudge:** read-only aggregate endpoints behind `require_coordinator_or_admin`; no N+1 loops. Return counts and exception lists, not giant grade payloads.

**Layer 2 · Guide (useful cards):** active year/semester; total students; classes; active teachers; filled/expected grade cells by class and subject; missing role assignments; active grants; saves in last 24h. “Expected” means roster × active columns for the relevant subject, with L2 roster filtering.

**Layer 3 · Exact assembly:** `src/flrc/modules/administration/coordinator.py`:

```text
GET /api/coordinator/overview
GET /api/coordinator/completeness?semester_id=<id>
GET /api/coordinator/classes/{class_id}/missing?subject=english
```

`CompletenessRow`:

```python
class CompletenessRow(BaseModel):
    class_id: int
    class_name: str
    subject: str
    roster_count: int
    active_columns: int
    expected_cells: int
    filled_cells: int
    missing_cells: int
    percent: float
```

A “filled” cell is a `grade_values` row whose type-specific field is non-null; do not count an all-null cleared row as complete. Implement with grouped SQL per subject or a small number of bulk queries, then assemble. Avoid one query per class.

**Frontend:** coordinator landing page is cards + sortable completeness table. Clicking a row opens the existing grid in read-only coordinator mode with missing cells visually marked; do not duplicate a coordinator-specific grid component.

**Check:** as coordinator, `/admin/users` 403; `/coordinator/overview` 200. Clear one score → completeness decreases by one. Add a German student → only German expected-cell count changes.

**If it breaks:** percentages exceed 100 → duplicate joins from assignments or languages inflated counts; count distinct `(student_id, column_id)` pairs or pre-aggregate each side.

Commit: `feat(coordinator): school-wide completeness surfaces`.

## Step 3.12: Phase 3 test pass, generated client, and exit

**What we're building:** the proof that administrative convenience did not weaken the safety model.

**Layer 1 · Nudge:** expand the role matrix, run importer fixtures, concurrency-test lifecycle transitions, and test the domain invariant around moves.

**Layer 3 · Exact assembly (minimum backend matrix additions):**

```text
GET  /api/admin/students                 anonymous 401 · teacher 403 · coordinator 403 · admin 200
POST /api/admin/users                    teacher 403 · coordinator 403
POST /api/admin/roster/move              teacher 403 · coordinator 403
POST /api/admin/import/dry-run           teacher 403 · coordinator 403
GET  /api/coordinator/overview           teacher 403 · coordinator 200 · admin 200
GET  /api/archive/years                  teacher 403 · coordinator 200 · admin 200
POST /api/admin/years/{id}/activate      coordinator 403
```

Required focused tests:

- Turkish search equivalence.
- Deactivated user's existing session dies.
- Last active admin cannot be demoted/deactivated.
- Bulk assignment transaction rolls back on one invalid user.
- Student move changes only `enrollments.class_id`; grade ids/versions remain byte-for-byte stable.
- L2 switch changes grid membership only.
- Two concurrent year activations cannot produce two active years.
- Import dry-run writes zero rows.
- Same import twice is idempotent.
- Conflicting duplicate workbook row is a parser error.
- SHA mismatch blocks commit.
- Archived year rejects every write path.
- Audit export digest changes after a new audit row.
- Student history spans two years under one student id.

Frontend tests worth the time: student form validation; bulk selection survives row re-render; importer commit disabled on error; lifecycle danger dialog requires exact label.

Run the contract ritual:

```bash
pnpm generate
pnpm prettier --write .
pnpm turbo run lint typecheck test build
cd apps/backend && uv run pytest -q
```

### Phase 3 exit checklist

- ✅ Students searchable with Turkish İ/I/ı behavior and stable URL state.
- ✅ Teacher allowlisting works; deactivation kills a live session immediately.
- ✅ Class/assignment matrix exposes missing owners before grade entry.
- ✅ Single and bulk roster moves preserve grades; cross-grade moves require explicit confirmation.
- ✅ German/French switching changes only the L2 projection.
- ✅ Lifecycle transitions are verbs with locked rows, not arbitrary status PATCHes.
- ✅ Hostile synthetic workbook dry-runs with cell-addressed issues, commits idempotently, and ignores gender.
- ✅ Close-year refuses stale audit digests and archives only with both semesters locked.
- ✅ Archive grid is explicitly semester-addressed and read-only.
- ✅ One student history crosses years without duplicating identity.
- ✅ Coordinator sees completeness and exceptions but cannot mutate admin resources.
- ✅ DECISIONS.md: no student deletion · session reverse index · bulk assignment transaction · moves mutate enrollment only · language-column absent vs blank · stateless SHA import handshake · lifecycle verbs over status PATCH · export-before-archive ceremony · archive projection reuse.
- ✅ `git tag phase-3 && git push --tags`

You now have a system a school can operate, not merely a grade grid developers can admire. Phase 4 turns its data into printable artifacts, moves slow work off the request path, proves the hardest browser race automatically, and prepares the boring machinery that keeps the system alive after launch.

---

# Part VII. Phase 4: Reports, jobs, backups, E2E, and launch

**Phase goal:** the school can generate printable report bundles without blocking an API request, watch durable progress, download the result after a worker restart, export a whole academic year, restore the database from an off-site backup, and run the two-browser collision automatically in CI. Then the demo topology becomes a school-owned production deployment with a written runbook and a named rollback path.

**Original Phase-4 table count:** Part I originally planned fourteen SQLAlchemy tables. Phase 1 created eight; Phase 2 created five; Phase 3 intentionally created none. `job_runs` completed that original fourteen-table design; later ADR-051 and ADR-057 added
`demo_visitors` and `report_identity_audits`. `job_runs` is the durable truth for every slow operation: queued, running, progress, success/failure, output metadata, and a short-lived output blob. Celery carries messages; Postgres carries facts.

**One operational correction worth making explicit:** Render's container filesystem is not a durable artifact store. A PDF zip written only to `/tmp` can disappear on restart, sleep, or redeploy. For this school's small workload, completed job output lives temporarily in `job_runs.output_blob` and is purged after 24 hours. That avoids another vendor, keeps authorization on the same API, and makes the download survive worker restarts. If the school later generates hundreds of megabytes per day, move the blob behind an object-storage adapter; the API contract does not need to change.

## Step 4.1: `job_runs`, durable state for slow work

**What we're building:** the final table, a job service, and three API operations: create, inspect, download. No Celery yet; first make the state machine truthful on its own.

**Why before the worker:** queues are delivery mechanisms, not databases. If the browser asks “is my PDF done?”, the answer must come from a row you control, not from Celery's ephemeral internal state or a Redis result backend that spends commands and complicates retention.

**Layer 1 · Nudge:** model status transitions, output metadata/blob, progress counters, requester, kind, payload. Keep payload machine data only (ids, report kind, locale), never student names.

**Layer 2 · Guide:** statuses: `queued`, `running`, `succeeded`, `failed`. Kinds: `progress_pdf`, `german_karne`, `french_karne`, `year_export`. Output is nullable until success. Error code is machine-safe and generic. `output_expires_at` is set 24 hours after success. Authorization: the requester may inspect/download their own job; coordinators/admins may inspect report jobs; only admins may inspect year-export jobs if that export contains all school data.

**Layer 3 · Exact assembly:** append to `src/flrc/db/models.py` (new imports: `LargeBinary` and `Text`; `JSONB` is already present):

```python
class JobRun(TimestampMixin, Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('progress_pdf','german_karne','french_karne','year_export')",
            name="kind_valid",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name="status_valid",
        ),
        CheckConstraint("progress >= 0", name="progress_nonnegative"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    output_filename: Mapped[str | None]
    output_mime: Mapped[str | None]
    output_size: Mapped[int | None] = mapped_column(BigInteger)
    output_blob: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    output_expires_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None]
    error_detail: Mapped[str | None] = mapped_column(Text)
```

Generate migration:

```bash
uv run alembic revision --autogenerate -m "durable job runs"
uv run alembic upgrade head
```

Read it: exactly one `create_table`, four CHECKs, two indexes, no accidental PII columns.

Create `src/flrc/modules/jobs/service.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from flrc.db.models import JobRun

OUTPUT_TTL = timedelta(hours=24)


async def create_job(
    db: AsyncSession,
    *,
    kind: str,
    requested_by: int,
    payload: dict[str, object],
) -> JobRun:
    job = JobRun(kind=kind, status="queued", requested_by=requested_by, payload=payload)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def mark_running(db: Session, job: JobRun, total: int) -> None:
    job.status = "running"
    job.total = total
    job.progress = 0
    job.started_at = datetime.now(UTC).replace(tzinfo=None)
    job.error_code = None
    job.error_detail = None
    db.commit()


def mark_succeeded(
    db: Session,
    job: JobRun,
    *,
    data: bytes,
    filename: str,
    mime: str,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    job.status = "succeeded"
    job.progress = job.total
    job.output_blob = data
    job.output_filename = filename
    job.output_mime = mime
    job.output_size = len(data)
    job.output_expires_at = now + OUTPUT_TTL
    job.finished_at = now
    db.commit()


def mark_failed(db: Session, job: JobRun, code: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_detail = "The job failed. See server logs with this job id."
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
```

Create `src/flrc/modules/jobs/router.py`:

```python
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from flrc.modules.auth.dependencies import current_user
from flrc.db.models import JobRun, User
from flrc.db.session import get_session

router = APIRouter(tags=["jobs"])


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: int
    total: int
    output_filename: str | None
    output_size: int | None
    output_expires_at: datetime | None
    error_code: str | None

    @classmethod
    def from_model(cls, job: JobRun) -> "JobOut":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            progress=job.progress,
            total=job.total,
            output_filename=job.output_filename,
            output_size=job.output_size,
            output_expires_at=job.output_expires_at,
            error_code=job.error_code,
        )


def may_read_job(user: User, job: JobRun) -> bool:
    if user.is_admin or job.requested_by == user.id:
        return True
    return user.is_coordinator and job.kind != "year_export"


def safe_download_name(value: str | None) -> str:
    return (value or "download.bin").replace("\r", "").replace("\n", "").replace('"', "_")


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> JobOut:
    # output_blob is deferred on the ORM model, so status polling never loads a ZIP from Postgres.
    job = await db.get(JobRun, job_id)
    if job is None:
        raise HTTPException(404, {"code": "unknown_job"})
    if not may_read_job(user, job):
        raise HTTPException(403, {"code": "forbidden"})
    return JobOut.from_model(job)


@router.get("/jobs/{job_id}/download")
async def download_job(
    job_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    job = await db.scalar(
        select(JobRun)
        .options(undefer(JobRun.output_blob))
        .where(JobRun.id == job_id)
    )
    if job is None:
        raise HTTPException(404, {"code": "unknown_job"})
    if not may_read_job(user, job):
        raise HTTPException(403, {"code": "forbidden"})
    if job.status != "succeeded":
        raise HTTPException(409, {"code": "job_not_ready", "status": job.status})

    now = datetime.now(UTC).replace(tzinfo=None)
    if (
        job.output_blob is None
        or job.output_expires_at is None
        or job.output_expires_at <= now
    ):
        raise HTTPException(410, {"code": "output_expired"})

    filename = safe_download_name(job.output_filename)
    return Response(
        content=job.output_blob,
        media_type=job.output_mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Two details are load-bearing: `output_blob` is a **deferred ORM column**, so a 2-second status poll never pulls a multi-megabyte ZIP out of Postgres; and download explicitly `undefer`s it only after authorization is about to be checked. The filename sanitizer removes CR/LF/quotes before it becomes a response header.

Add a maintenance command:

```python
@app.command("purge-job-outputs")
def purge_job_outputs() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(sync_engine()) as db:
        count = db.execute(
            update(m.JobRun)
            .where(m.JobRun.output_expires_at < now, m.JobRun.output_blob.is_not(None))
            .values(output_blob=None)
        ).rowcount
        db.commit()
    typer.echo(f"purged {count or 0} job outputs")
```

Do **not** delete the job row; history is operational evidence. Delete only the potentially large blob.

**Check:** create one job from a Python shell, manually mark it succeeded with `b"hello"`, download through the API, then set expiry to yesterday → 410.

**If it breaks:** output survives in Python but not after commit → `LargeBinary` column/migration missing. The response consumes huge memory twice → acceptable at today's class-sized zip scale; record the object-storage escape hatch in DECISIONS.md rather than optimizing an imaginary workload.

Commit: `feat(jobs): durable job state and expiring outputs`.

## Step 4.2: Report cards as pure data, then HTML, then PDF

**Current renderer:** `modules/reports/builder.py` assembles typed contexts, `branding.py`
resolves optional private overlays/teacher identities, and `render.py` selects the current
primary-English, middle-English or karne template. See ADR-057 and `branding/README.md`.
Pending ADR-063 removes middle-English comments from generated reports. The pending memory
change caps layout batches at 16 render units in both pooled and serial fallback paths;
review duplex cover replacement and page order, not just whether the output is a valid PDF.

**What we're building:** the reporting pipeline in three separable layers:

1. database rows → `ReportCard` data;
2. `ReportCard` → Jinja HTML;
3. HTML → PDF bytes through WeasyPrint.

The three report kinds are one A5-landscape progress report and two A4 bilingual second-language report cards: German and French.

**Why the layers matter:** if a student's average is wrong, you should test Python data without rendering a PDF. If a label is wrong, inspect HTML without starting a worker. If page size is wrong, test PDF metadata. One giant `generate_pdf()` function would turn every failure into a mystery.

**Layer 1 · Nudge:** Pydantic/dataclass report view model, builder service, one progress template, one bilingual template parameterized by German/French, print CSS, PDF smoke tests.

**Layer 2 · Guide (report rules):**

- progress report: A5 landscape, one student per PDF, all active English columns for the chosen semester/grade;
- German/French karne: A4 portrait, only students enrolled in that L2 for the year, only matching subject columns;
- average uses only score columns with `counts_in_average=True` and non-null values;
- scale/text never enter arithmetic;
- labels resolve requested locale → Turkish fallback;
- cleared/null values render as an em dash, never `0`;
- filenames begin with school number so sorting is deterministic.

**Layer 3 · Exact assembly (dependencies):**

```bash
cd apps/backend
uv add jinja2 weasyprint
uv add --dev pypdf
```

The current WeasyPrint wheels still require Linux text-layout libraries in a minimal Debian container. Update the runtime stage of `Dockerfile`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
```

Create directories:

```bash
mkdir -p src/flrc/modules/reports/templates src/flrc/modules/reports/static
```

`src/flrc/modules/reports/models.py`:

```python
from pydantic import BaseModel


class ReportField(BaseModel):
    label: str
    group: str | None
    value_type: str
    value: int | str | None


class ReportCard(BaseModel):
    kind: str
    locale: str
    year_label: str
    semester_number: int
    class_name: str
    school_number: int
    student_name: str
    subject: str
    subject_label: str
    fields: list[ReportField]
    average: float | None
```

`src/flrc/modules/reports/builder.py` has one public function and no HTML knowledge:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from flrc.db.models import (
    AcademicYear, ColumnDefinition, Enrollment, GradeValue, SchoolClass,
    Semester, Student, StudentLanguage,
)
from flrc.modules.reports.models import ReportCard, ReportField

KIND_TO_SUBJECT = {
    "progress_pdf": "english",
    "german_karne": "german",
    "french_karne": "french",
}
VALUE_FIELD = {"score": "score", "scale3": "scale", "text": "text_value"}
SUBJECT_LABELS = {
    "english": {"tr": "İngilizce", "en": "English", "de": "Englisch", "fr": "Anglais"},
    "german": {"tr": "Almanca", "en": "German", "de": "Deutsch", "fr": "Allemand"},
    "french": {"tr": "Fransızca", "en": "French", "de": "Französisch", "fr": "Français"},
}


def pick_label(labels: dict[str, str] | None, locale: str) -> str | None:
    if not labels:
        return None
    return labels.get(locale) or labels.get("tr") or next(iter(labels.values()), "")


def score_average(
    columns: list[ColumnDefinition],
    values: dict[int, GradeValue],
) -> float | None:
    scores = [
        values[c.id].score
        for c in columns
        if c.counts_in_average and c.id in values and values[c.id].score is not None
    ]
    return round(sum(scores) / len(scores), 2) if scores else None


def build_cards(
    db: Session,
    *,
    class_id: int,
    semester_id: int,
    kind: str,
    locale: str,
) -> list[ReportCard]:
    subject = KIND_TO_SUBJECT.get(kind)
    if subject is None:
        raise ValueError("unknown_report_kind")

    cls = db.get(SchoolClass, class_id)
    semester = db.get(Semester, semester_id)
    if cls is None or semester is None or semester.year_id != cls.year_id:
        raise ValueError("class_semester_mismatch")
    year = db.get(AcademicYear, cls.year_id)
    if year is None:
        raise ValueError("unknown_year")

    columns = list(db.scalars(
        select(ColumnDefinition)
        .where(
            ColumnDefinition.semester_id == semester.id,
            ColumnDefinition.grade_level == cls.grade_level,
            ColumnDefinition.subject == subject,
            ColumnDefinition.is_active.is_(True),
        )
        .order_by(ColumnDefinition.position, ColumnDefinition.id)
    ))

    roster_stmt = (
        select(Student, Enrollment.school_number)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.class_id == cls.id)
        .order_by(Enrollment.school_number, Student.search_name, Student.id)
    )
    if subject in {"german", "french"}:
        roster_stmt = roster_stmt.join(
            StudentLanguage, StudentLanguage.student_id == Student.id
        ).where(
            StudentLanguage.year_id == year.id,
            StudentLanguage.language == subject,
        )
    roster = list(db.execute(roster_stmt).all())
    students = [student for student, _number in roster]
    school_numbers = {student.id: number for student, number in roster}

    student_ids = [student.id for student in students]
    column_ids = [column.id for column in columns]
    grade_values = (
        list(db.scalars(
            select(GradeValue).where(
                GradeValue.student_id.in_(student_ids),
                GradeValue.column_definition_id.in_(column_ids),
            )
        ))
        if student_ids and column_ids
        else []
    )
    by_student: dict[int, dict[int, GradeValue]] = {}
    for value in grade_values:
        by_student.setdefault(value.student_id, {})[value.column_definition_id] = value

    cards: list[ReportCard] = []
    for student in students:
        student_values = by_student.get(student.id, {})
        fields = []
        for column in columns:
            value_row = student_values.get(column.id)
            value = getattr(value_row, VALUE_FIELD[column.value_type]) if value_row else None
            fields.append(ReportField(
                label=pick_label(column.labels, locale) or "",
                group=pick_label(column.group_labels, locale),
                value_type=column.value_type,
                value=value,
            ))
        cards.append(ReportCard(
            kind=kind,
            locale=locale,
            year_label=year.label,
            semester_number=semester.number,
            class_name=f"{cls.grade_level}/{cls.section}",
            school_number=school_numbers[student.id],
            student_name=student.full_name,
            subject=subject,
            subject_label=pick_label(SUBJECT_LABELS[subject], locale) or subject,
            fields=fields,
            average=score_average(columns, student_values),
        ))
    return cards
```

The six-step query shape is deliberate: class/year/semester validation; columns; roster; one bulk grade query; Python assembly. No query runs inside the per-student loop.

Average helper:

```python
def score_average(columns: list[ColumnDefinition], values: dict[int, GradeValue]) -> float | None:
    scores = [
        values[c.id].score
        for c in columns
        if c.counts_in_average and c.id in values and values[c.id].score is not None
    ]
    return round(sum(scores) / len(scores), 2) if scores else None
```

`src/flrc/modules/reports/render.py`:

```python
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_card_html(card: ReportCard) -> str:
    template_name = "progress.html" if card.kind == "progress_pdf" else "bilingual.html"
    return env.get_template(template_name).render(card=card)


def render_card_pdf(card: ReportCard) -> bytes:
    html = render_card_html(card)
    return HTML(string=html, base_url=str(HERE)).write_pdf()
```

`templates/progress.html` starts:

```html
<!doctype html>
<html lang="{{ card.locale }}">
  <head>
    <meta charset="utf-8" />
    <style>
      @page {
        size: A5 landscape;
        margin: 8mm;
      }
      * {
        box-sizing: border-box;
      }
      body {
        font-family: "DejaVu Sans", sans-serif;
        font-size: 9pt;
        color: #111;
      }
      h1 {
        margin: 0 0 4mm;
        font-size: 15pt;
      }
      .meta {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2mm 8mm;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 5mm;
      }
      th,
      td {
        border: 0.25mm solid #555;
        padding: 1.8mm;
        vertical-align: top;
      }
      th {
        background: #eee;
        text-align: left;
      }
      .value {
        width: 24mm;
        text-align: center;
        font-weight: 700;
      }
    </style>
  </head>
  <body>
    <h1>{{ card.subject_label }}</h1>
    <div class="meta">
      <div><strong>{{ card.student_name }}</strong></div>
      <div>{{ card.class_name }} · {{ card.year_label }} · S{{ card.semester_number }}</div>
      <div>No: {{ card.school_number }}</div>
      <div>Average: {{ "—" if card.average is none else card.average }}</div>
    </div>
    <table>
      <tbody>
        {% for field in card.fields %}
        <tr>
          <td>{{ field.label }}</td>
          <td class="value">{{ "—" if field.value is none else field.value }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </body>
</html>
```

`templates/bilingual.html` uses `@page { size: A4 portrait; margin: 12mm; }`, a two-language heading, student meta, grouped table, and signature area. Keep translation strings in a small report translation dictionary keyed by `tr/de/fr/en`; do not reach into React i18next JSON from Python at runtime. The shared semantic keys may match, but the services should not import browser packages.

**Testing the PDF, not merely “file exists”:** `tests/test_reports.py` creates a card, calls `render_card_pdf`, asserts `pdf.startswith(b"%PDF-")`, then uses `pypdf.PdfReader(io.BytesIO(pdf))` to check exactly one page and the expected MediaBox dimensions within tolerance. Also test that the HTML escapes a student name containing `<script>`; Jinja autoescape must turn it into text.

**Check:** render three synthetic PDFs locally and open them. Print preview: no clipping, Turkish characters correct, A5 landscape actually landscape, A4 actually portrait. Test one very long name and one long text comment.

**If it breaks:** missing glyph squares → font package absent in the Docker image. CSS looks fine in browser but wrong in PDF → WeasyPrint implements print CSS, not every browser feature; use simple grid/table layout. Remote images stall rendering → reports should use local assets through `base_url`, not network URLs.

**Docs:** WeasyPrint first steps + Python API; Jinja autoescape docs. **Why deeper:** ARCH decision #10.

Commit: `feat(reports): pure card models, HTML templates, PDF renderer`.

## Step 4.3: Celery, one quiet worker, no result backend, durable progress in Postgres

**Current delivery amendment (ADR-028):** the API directly returns four report sets through
`GET /api/reports/pdf`; it does not expose the report-job creation route illustrated below.
Celery currently processes whole-year exports via `workers/tasks/exports.py`. Retain durable
`job_runs`, JSON-only messages, and no result backend for that implemented job path.

**What we're building:** the asynchronous execution path: the API creates a job, enqueues its id, sends a best-effort wake-up ping, and returns immediately. A separate service consumes the id, renders sequentially, updates Postgres progress, stores the final zip, and marks success/failure.

**Why “job id only” in the queue:** Redis messages should be tiny and non-sensitive. The worker reloads authoritative ids/payload from Postgres. Never put student names, grade values, or report HTML into Redis.

**Layer 1 · Nudge:** Celery app + sync task + worker start script + tiny health app. Quiet flags: no gossip, mingle, or heartbeat; no Redis result backend; one task at a time.

**Layer 2 · Guide:** task delivery is at-least-once, so the worker must be idempotent. At task start, lock the job. If already `succeeded`, return. If `running` with recent heartbeat, return/retry; for this one-worker design, marking queued→running under row lock is enough. `acks_late=True` means a killed worker can redeliver; durable job state protects against duplication. Prefetch 1 prevents one worker from hoarding multiple report batches.

**Layer 3 · Exact assembly (dependencies):**

```bash
uv add celery "redis[hiredis]" httpx
```

Create `src/flrc/workers/celery.py`:

```python
from celery import Celery

from flrc.config import settings

celery_app = Celery(
    "flrc",
    broker=settings.redis_url,
    include=["app.tasks.reports", "app.tasks.exports"],
)
celery_app.conf.update(
    task_ignore_result=True,
    result_backend=None,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 60 * 60},
)
```

Create `src/flrc/db/sync.py` and move the CLI helper there so worker/CLI share it:

```python
from sqlalchemy import create_engine

from flrc.config import settings


def sync_engine():
    return create_engine(
        settings.database_url.replace("+asyncpg", "+psycopg"),
        pool_pre_ping=True,
    )
```

Create `src/flrc/workers/tasks/reports.py`:

```python
import io
import re
import zipfile

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from flrc.db.models import JobRun
from flrc.db.sync import sync_engine
from flrc.modules.reports.builder import build_cards
from flrc.modules.reports.render import render_card_pdf
from flrc.modules.jobs.service import mark_failed, mark_running, mark_succeeded
from flrc.workers.celery import celery_app

log = structlog.get_logger()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", name).strip("-")
    return cleaned or "report"


@celery_app.task(name="reports.generate", bind=True)
def generate_report_job(self, job_id: int) -> None:
    with Session(sync_engine()) as db:
        job = db.scalar(select(JobRun).where(JobRun.id == job_id).with_for_update())
        if job is None or job.status == "succeeded":
            return
        payload = job.payload
        try:
            cards = build_cards(
                db,
                class_id=int(payload["class_id"]),
                semester_id=int(payload["semester_id"]),
                kind=job.kind,
                locale=str(payload.get("locale", "tr")),
            )
            mark_running(db, job, total=len(cards))

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for index, card in enumerate(cards, 1):
                    pdf = render_card_pdf(card)
                    filename = safe_filename(
                        f"{card.school_number}-{card.student_name}.pdf"
                    )
                    archive.writestr(filename, pdf)
                    job.progress = index
                    db.commit()

            data = buffer.getvalue()
            archive_name = safe_filename(
                f"{job.kind}-{payload['class_id']}-s{payload['semester_id']}.zip"
            )
            mark_succeeded(
                db, job, data=data, filename=archive_name, mime="application/zip"
            )
            log.info("report_job_succeeded", job_id=job.id, kind=job.kind, count=len(cards))
        except Exception:
            db.rollback()
            fresh = db.get(JobRun, job_id)
            if fresh is not None:
                mark_failed(db, fresh, "report_render_failed")
            log.exception("report_job_failed", job_id=job_id)
            raise
```

**The empty-class rule:** zero cards is a clean failure with code `empty_report_set`, not a successful empty zip. Check before `mark_running`.

Create `src/flrc/workers/health.py`:

```python
from fastapi import FastAPI

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "worker"}
```

Create executable `apps/backend/bin/start-worker-web.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

uv run uvicorn flrc.workers.health:app --host 0.0.0.0 --port "${PORT:-10000}" &
HEALTH_PID=$!

uv run celery -A flrc.workers.celery:celery_app worker \
  --loglevel=INFO \
  --pool=solo \
  --concurrency=1 \
  --without-gossip \
  --without-mingle \
  --without-heartbeat &
CELERY_PID=$!

cleanup() {
  kill "$HEALTH_PID" "$CELERY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "$HEALTH_PID" "$CELERY_PID"
status=$?
cleanup
wait || true
exit "$status"
```

```bash
chmod +x apps/backend/bin/start-worker-web.sh
```

Why this shape: Render requires a web service to bind a port; the health stub does that. Celery remains the real foreground purpose. If either process dies, the script exits and the platform restarts the service. The `solo` pool keeps memory predictable for one-person, one-school PDF generation.

**API enqueue contract:** `src/flrc/modules/reports/router.py`:

```python
class ReportJobCreate(BaseModel):
    class_id: int
    semester_id: int
    kind: Literal["progress_pdf", "german_karne", "french_karne"]
    locale: Literal["tr", "en", "de", "fr"] = "tr"


@router.post("/reports/jobs", status_code=202)
async def create_report_job(
    body: ReportJobCreate,
    background: BackgroundTasks,
    user: User = Depends(require_coordinator_or_admin),
    db: AsyncSession = Depends(get_session),
) -> JobOut:
    # validate class/semester/kind before creating row
    job = await create_job(
        db,
        kind=body.kind,
        requested_by=user.id,
        payload=body.model_dump(),
    )
    generate_report_job.delay(job.id)
    background.add_task(ping_worker_best_effort)
    return JobOut.from_model(job)
```

Wake helper:

```python
async def ping_worker_best_effort() -> None:
    if not settings.worker_health_url:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(settings.worker_health_url)
    except httpx.HTTPError:
        pass  # The request itself may already have woken a sleeping service.
```

Also call the helper from job-status polling while a job is queued. Do not make status endpoint latency depend on a 45-second cold start; three seconds and ignore.

**Local check:** run Redis/Postgres, API, and `./bin/start-worker-web.sh` in separate terminals. POST a report job. The API returns 202 before PDF completion. Poll job: queued → running with `progress/total` → succeeded. Kill the worker mid-job, restart, re-enqueue the same id manually: no duplicate succeeded output is produced.

**If it breaks:** Celery says task unregistered → `include` module wrong or worker launched against wrong app object. Redis command count spikes → heartbeat/gossip/mingle flags missing. Job remains queued after worker wake → broker URL mismatch between API and worker. Worker OOMs → confirm `--pool=solo`, sequential render, and no list of all PDF bytes retained alongside the zip.

**Docs:** Celery worker guide, Redis broker guide. **Why deeper:** ARCH decision #9.

Commit: `feat(worker): quiet celery report pipeline with durable progress`.

## Step 4.4: Report center, year export, and the four-language finish

**What we're building:** one coordinator/admin Report Center that starts PDF jobs, polls with TanStack Query, downloads completed bundles, starts a whole-year XLSX export, and exposes job history. In the same pass, the two SPAs receive the complete TR/EN/DE/FR sweep promised since Phase 1.

**Why combine these now:** job polling is the final major client-side data pattern. Once it exists, year export is another job kind, not another architecture. And reports are where untranslated labels become printed mistakes, so this is the right forcing function for the i18n completion pass.

### 4.4.1 The Report Center

**Layer 1 · Nudge:** report form → create mutation → query `refetchInterval` while queued/running → progress bar → download link when succeeded.

**Layer 2 · Guide:** preserve active job ids in URL search params or session storage so a refresh does not lose progress. Poll every 2 seconds while active; stop on terminal state. A 410 download expiry shows “Generate again,” not a broken anchor.

**Layer 3 · Exact assembly (query options):**

```ts
const jobQuery = useQuery({
  ...getJobOptions({ path: { job_id: jobId } }),
  enabled: jobId !== null,
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    return status === "queued" || status === "running" ? 2000 : false;
  },
});
```

UI states:

```text
queued      Waiting for worker…
running     Generating 12 / 28
succeeded   Download ZIP · Expires in 23h 14m
failed      Could not generate · error code · Generate again
```

Never show raw exception text. The job id is the support handle.

### 4.4.2 The whole-year XLSX export

**Current implementation (ADR-062):** one streaming writer emits seven sheets, reads at most
1,000 rows per batch, closes a result before committing progress, and preserves formula
neutralization. `tests/test_bulk_operations.py` covers query budgets and the larger synthetic
export. Use that implementation when maintaining exports, not the earlier assembly sketch.

**What we're building:** an operational portability file with one workbook and seven sheets: Students, Enrollments, Languages, Assignments, Columns, Grades, Audit.

**Why XLSX in addition to `pg_dump`:** a database dump is for disaster recovery; a workbook is for institutional portability and human inspection. One does not replace the other.

**Layer 3 · Exact assembly:** `src/flrc/workers/tasks/exports.py` builds in write-only mode:

```python
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from flrc.db.models import JobRun
from flrc.db.sync import sync_engine
from flrc.modules.jobs.service import mark_failed, mark_running, mark_succeeded
from flrc.workers.celery import celery_app

DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_xlsx_text(value: str) -> str:
    return f"'{value}" if value.startswith(DANGEROUS_FORMULA_PREFIXES) else value


@celery_app.task(name="exports.year")
def export_year_job(job_id: int) -> None:
    with Session(sync_engine()) as db:
        job = db.get(JobRun, job_id)
        if job is None or job.status == "succeeded":
            return
        try:
            year_id = int(job.payload["year_id"])
            mark_running(db, job, total=7)
            wb = Workbook(write_only=True)
            # For each sheet: append a bold header row and streamed DB rows.
            # Update job.progress after every completed sheet.
            buffer = BytesIO()
            wb.save(buffer)
            mark_succeeded(
                db,
                job,
                data=buffer.getvalue(),
                filename=f"flrc-year-{year_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception:
            db.rollback()
            fresh = db.get(JobRun, job_id)
            if fresh:
                mark_failed(db, fresh, "year_export_failed")
            raise
```

Use explicit column order and ids in every sheet. For Grades, include student school number, column id/label, semester, subject, typed value, version, updated_by id, and timestamps. For Audit, include the same portable columns as the close-year CSV.

Create the endpoint `POST /api/exports/year/{year_id}` behind `require_admin` and return a 202 job. The report center has an admin-only **Year export** card.

### 4.4.3 The i18n completion pass

The original Phase-2 column editor mirrored Turkish into all locales for newly created custom
columns as a scope cut; the built-in seed catalog was already translated. Remove the editor cut
now. The column editor gets four tabs/inputs: TR, EN, DE, FR for `labels` and optional
`group_labels`. Require Turkish; other fields may fall back to Turkish, but the UI marks the
fallback with a subtle badge. Keep report-label values in Postgres; do not move the seed catalog
into browser i18next resources. Remove the temporary `"_TODO": "translate"` sentinel from
`de.json`/`fr.json`; Phase 1's deliberate UI-chrome debt is paid here.

Run a literal-string audit:

```bash
rg -n --glob '*.{ts,tsx}' ">[^<{]*[A-Za-zÇĞİÖŞÜçğıöşü][^<{]*<" apps/teacher/src apps/admin/src
rg -n --glob '*.{ts,tsx}' "(toast|title|description|placeholder)=['\"]" apps/teacher/src apps/admin/src
```

These regexes are imperfect by design; they are a flashlight, not a compiler. Add/enable the chosen i18next literal-string ESLint rule if it fits your config without false-positive warfare. Every route title, dialog, toast, empty state, error code, job status, importer issue code, lifecycle action, and report label must have all four locale keys.

**Check:** run admin and teacher apps in each language. Generate German and French PDFs while UI locale differs from report locale. Printed labels follow the report locale; UI chrome follows the UI locale. Change a column's German label and regenerate: PDF changes without code deploy.

**If it breaks:** polling continues forever on failure → terminal statuses include both succeeded and failed. Refresh loses job → id was only component state. Excel opens a cell as a formula → `safe_xlsx_text` missing on user-controlled strings.

Commit: `feat(reports): report center, year export, complete i18n`.

## Step 4.5: Weekly off-site backup to the school's Google Drive, plus a real restore drill

**School-hosted amendment (ADR-056):** the current `flrc backup` service makes nightly
age-encrypted dumps with recorded status, monthly automated restore tests, and persistent
archived-year bundles in the school's Shared Drive. It runs from the private deployment's
Compose stack, not a root backup workflow. Follow [SELF-HOSTING.md](SELF-HOSTING.md) and
[RESTORE-DRILLS.md](RESTORE-DRILLS.md). There is no `.github/workflows/backup.yml` in this tree.
The weekly workflow below remains the original managed-profile teaching example; it is not
an installed backup or proof that the school's restoration procedure has passed.

**What we're building:** a scheduled GitHub Actions workflow that runs `pg_dump` against Neon's **direct** connection, uploads the custom-format dump to a school-owned Google Drive location, prunes old backups, and can be triggered manually. Then we restore one dump into a scratch database and prove the app can read it.

**Why this is non-negotiable:** Neon's short point-in-time recovery window is not a long-term archive, and “workflow green” is not proof a dump is restorable. A backup is a hypothesis until `pg_restore` succeeds.

**The Google Drive deployment choice:** prefer a folder inside a **Shared Drive** owned by the school's Workspace and add the service account as a member with only the access it needs. The script uses the Drive API and `supportsAllDrives=True`. If the school does not have Shared Drives, do not silently improvise storage ownership: have the Workspace admin approve the exact alternative account/delegation model and record it in the KVKK/operations ADR.

**Layer 1 · Nudge:** custom-format `pg_dump`, timestamped filename, SHA-256 sidecar, service-account JSON secret, Drive folder id, retention 12 copies, manual restore workflow.

**Layer 2 · Guide (secrets):**

- `PG_DUMP_URL`: plain PostgreSQL direct URL (`postgresql://...`), not SQLAlchemy's `+asyncpg` URL and not pooled.
- `GDRIVE_SERVICE_ACCOUNT_JSON`: whole service-account credential JSON.
- `GDRIVE_BACKUP_FOLDER_ID`: the exact destination folder id.

Do not echo any of them. GitHub Actions job permissions: `contents: read` only.

**Layer 3 · Exact assembly (upload script):** `scripts/upload_backup_to_drive.py`:

```python
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--retain", type=int, default=12)
    args = parser.parse_args()

    info = json.loads(os.environ["GDRIVE_SERVICE_ACCOUNT_JSON"])
    folder_id = os.environ["GDRIVE_BACKUP_FOLDER_ID"]
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    digest = hashlib.sha256(args.dump.read_bytes()).hexdigest()
    sidecar = args.dump.with_suffix(args.dump.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {args.dump.name}\n", encoding="utf-8")

    for path, mime in [
        (args.dump, "application/octet-stream"),
        (sidecar, "text/plain"),
    ]:
        drive.files().create(
            body={"name": path.name, "parents": [folder_id]},
            media_body=MediaFileUpload(str(path), mimetype=mime, resumable=True),
            fields="id,name,createdTime",
            supportsAllDrives=True,
        ).execute()

    result = drive.files().list(
        q=f"'{folder_id}' in parents and name contains 'flrc-' and trashed = false",
        fields="files(id,name,createdTime)",
        orderBy="createdTime desc",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    dumps = [f for f in result.get("files", []) if f["name"].endswith(".dump")]
    for old in dumps[args.retain:]:
        drive.files().delete(fileId=old["id"], supportsAllDrives=True).execute()
        # Delete matching sidecar in a later cleanup pass or by exact-name lookup.

    print(json.dumps({"uploaded": args.dump.name, "sha256": digest, "retained": min(len(dumps), args.retain)}))


if __name__ == "__main__":
    main()
```

**Workflow:** `.github/workflows/backup.yml`:

```yaml
name: Weekly database backup

on:
  schedule:
    - cron: "17 1 * * 0"
      timezone: "Europe/Istanbul"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  backup:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - name: Install PostgreSQL client and Drive libraries
        run: |
          sudo apt-get update
          sudo apt-get install -y postgresql-client
          python -m pip install --disable-pip-version-check google-api-python-client google-auth

      - name: Dump database
        env:
          PG_DUMP_URL: ${{ secrets.PG_DUMP_URL }}
        run: |
          set -euo pipefail
          stamp=$(date -u +'%Y-%m-%dT%H-%M-%SZ')
          file="flrc-${stamp}.dump"
          pg_dump "$PG_DUMP_URL" --format=custom --no-owner --no-privileges --file="$file"
          test -s "$file"
          echo "BACKUP_FILE=$file" >> "$GITHUB_ENV"

      - name: Upload to school Drive
        env:
          GDRIVE_SERVICE_ACCOUNT_JSON: ${{ secrets.GDRIVE_SERVICE_ACCOUNT_JSON }}
          GDRIVE_BACKUP_FOLDER_ID: ${{ secrets.GDRIVE_BACKUP_FOLDER_ID }}
        run: python scripts/upload_backup_to_drive.py "$BACKUP_FILE" --retain 12
```

Scheduling at minute 17 instead of the top of the hour avoids the common peak where scheduled workflow execution can be delayed. Manual `workflow_dispatch` is essential for the pre-launch proof.

**Restore drill (local first):** download a backup and sidecar from the school Drive, verify the hash, then:

```bash
sha256sum -c flrc-....dump.sha256

docker compose -f infra/compose/compose.dev.yaml exec postgres createdb -U flrc flrc_restore
docker cp flrc-....dump flrc-postgres-1:/tmp/restore.dump
docker compose -f infra/compose/compose.dev.yaml exec postgres pg_restore \
  -U flrc \
  -d flrc_restore \
  --no-owner \
  --no-privileges \
  /tmp/restore.dump

docker compose -f infra/compose/compose.dev.yaml exec postgres psql -U flrc -d flrc_restore -c \
  "select count(*) as students from students; select count(*) as grades from grade_values;"
```

Then point a temporary local API at `flrc_restore`, start it, log in through an E2E bypass or run an authenticated API test, and open an archived grid. Record the date, backup filename, counts, and result in `docs/RESTORE-DRILLS.md`.

**Check:** manual workflow green; two files arrive in the school-owned folder; hash verifies; restore succeeds; row counts sane; one read path works against restored DB.

**If it breaks:** `pg_dump` version mismatch with server → install a matching/newer PostgreSQL client. Drive 404 on folder → service account is not a member/has no access. Upload works but files land outside school governance → stop and fix ownership/location; “technically uploaded” is not the requirement.

**Docs:** PostgreSQL `pg_dump`/`pg_restore`; Google Drive API upload guide and Shared Drives guide; GitHub Actions schedule docs.

Commit: `ops: weekly school-owned backup and restore drill`.

## Step 4.6: Playwright, where the two-browser collision becomes automatic

**What we're building:** real E2E tests against real FastAPI/Postgres/Redis and built SPAs, including the crown jewel: two isolated authenticated browser contexts edit the same grade, one wins, the other sees a named conflict, then overwrites deliberately.

**Why now:** unit tests proved algorithms. E2E proves the seams: proxy, cookie, router, generated client, Query cache, Zustand dirty state, conflict dialog, and server concurrency all cooperate in an actual browser.

**The auth problem:** CI must not automate Google login. The correct escape hatch is a route that literally cannot exist outside `ENV=test`, is protected by an E2E secret, and creates a normal server-side session for a seeded user. Production never includes the router.

**Layer 1 · Nudge:** test-only session endpoint, deterministic E2E seed, Playwright projects, two storage states/contexts, one collision test.

**Layer 2 · Guide:** use multiple `BrowserContext`s with different saved storage states. Each context gets independent cookies, exactly like two humans. Seed one teacher as the column owner and one admin/coordinator account as the second writer. Never share one page/context and pretend it is two users.

**Layer 3 · Exact assembly (install):**

```bash
pnpm add -D @playwright/test -w
pnpm exec playwright install chromium
```

Root `package.json`:

```json
{
  "scripts": {
    "e2e": "playwright test",
    "e2e:ui": "playwright test --ui"
  }
}
```

Add to root `.gitignore`:

```text
playwright-report/
test-results/
e2e/.auth/
```

Backend settings:

```python
e2e_auth_secret: str = ""
```

`src/flrc/modules/auth/test_router.py`:

```python
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.modules.auth import cookies, sessions
from flrc.config import settings
from flrc.db.models import User
from flrc.db.session import get_session

router = APIRouter(prefix="/test", tags=["test-only"])


class TestSessionBody(BaseModel):
    email: str


@router.post("/session")
async def create_test_session(
    body: TestSessionBody,
    response: Response,
    x_e2e_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    if settings.env != "test" or not settings.e2e_auth_secret:
        raise HTTPException(404)
    if not secrets.compare_digest(x_e2e_secret, settings.e2e_auth_secret):
        raise HTTPException(404)
    user = await db.scalar(select(User).where(User.email == body.email, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(404)
    sid = await sessions.create_session(user.id)
    cookies.set_session_cookie(response, sid)
    return {"ok": True}
```

In `create_app()`:

```python
if settings.env == "test":
    from flrc.modules.auth.test_router import router as test_router

    app.include_router(test_router, prefix="/api")
```

That conditional is security-critical. Add a production-mode test asserting `/api/test/session` is 404 even with a secret header.

Create a deterministic `flrc seed-e2e` command: one active year, semester 1 open, class 5/A, two students, two users:

```text
owner@example-school.k12.tr   teacher, owns main role
admin@example-school.k12.tr   admin + coordinator
```

Create one English score column owned by `main`. Keep the fixture tiny so E2E starts fast.

`playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

`e2e/helpers/auth.ts`:

```ts
import { request as requestFactory } from "@playwright/test";
import type { Browser } from "@playwright/test";

export async function authenticatedContext(browser: Browser, email: string) {
  // One isolated API request context per identity. Reusing Playwright's shared
  // `request` fixture here would let the second login overwrite the first
  // context's cookie jar before we snapshot storageState.
  const api = await requestFactory.newContext({
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
  });

  try {
    const response = await api.post("/api/test/session", {
      headers: { "x-e2e-secret": process.env.E2E_AUTH_SECRET! },
      data: { email },
    });
    if (!response.ok()) throw new Error(`test login failed: ${response.status()}`);

    const state = await api.storageState();
    return browser.newContext({ storageState: state });
  } finally {
    await api.dispose();
  }
}
```

If the API request context's cookie domain does not match the browser base URL through the proxy, create the request context with the same frontend base URL (`http://localhost:4173`) so `/api/test/session` traverses Vite's proxy and sets a first-party cookie.

`e2e/conflict.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";

test("two writers collide, conflict names the winner, overwrite is explicit", async ({
  browser,
}) => {
  const ownerContext = await authenticatedContext(browser, "owner@example-school.k12.tr");
  const adminContext = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const owner = await ownerContext.newPage();
  const admin = await adminContext.newPage();

  await owner.goto("/classes/1/grid?subject=english");
  await admin.goto("/classes/1/grid?subject=english");

  const ownerCell = owner.getByTestId("cell-1-1").getByRole("textbox");
  const adminCell = admin.getByTestId("cell-1-1").getByRole("textbox");

  await ownerCell.fill("85");
  await ownerCell.blur();

  await adminCell.fill("90");
  await adminCell.blur();
  await admin.getByRole("button", { name: /save all/i }).click();
  await expect(admin.getByText(/saved/i)).toBeVisible();

  await owner.getByRole("button", { name: /save all/i }).click();
  const dialog = owner.getByRole("dialog");
  await expect(dialog).toContainText("90");
  await expect(dialog).toContainText("Admin");

  await dialog.getByRole("button", { name: /overwrite/i }).click();
  await expect(dialog).toBeHidden();
  await expect(ownerCell).toHaveValue("85");

  await ownerContext.close();
  await adminContext.close();
});
```

Add stable `data-testid="cell-${studentId}-${columnId}"` only where semantic roles cannot uniquely identify the grid cell; do not carpet-bomb the UI with test ids.

**Other required E2E flows:** login bootstrap through test session; teacher saves and refreshes; grant request/expiry using a test-controlled clock at API level if practical; admin imports hostile fixture dry-run → commit; lifecycle lock makes grid read-only; report job can be faked at task boundary for fast UI E2E while one backend integration test renders real PDF.

**CI workflow:** add an `e2e` job after unit tests. Start Postgres/Redis services, run migrations, seed E2E data, start API and built preview servers, wait on `/api/healthz`, then `pnpm e2e`. Upload Playwright report only on failure.

**Check:** run the collision test five times with `--repeat-each=5`; no flakes. Break the version check in save service → test fails. Restore it.

**If it breaks:** both contexts appear as the same user → you reused one storage state/context. Test route accidentally exists in dev/prod → conditional router registration missing. Random 401 → request context cookie origin differs from page origin.

**Docs:** Playwright authentication and multiple-role/browser-context guides.

Commit: `test(e2e): real two-browser grade conflict and critical flows`.

## Step 4.7: Observability without leaking student data

**What we're building:** request ids, structured JSON logs, Sentry for crashes, and a scrubber that treats student data as toxic in telemetry.

**Why:** production bugs without evidence are archaeology; production logs containing names/grades are a privacy incident waiting to happen. The target is operational visibility with ids and event codes, not payload dumps.

**Layer 1 · Nudge:** request-id middleware, structlog context, Sentry `send_default_pii=False`, request bodies and local variables disabled, recursive event/breadcrumb scrubbing, frontend Sentry with replay off unless separately approved.

**Layer 2 · Guide (allowed fields):** request id, route template, status, duration, actor id, class id, year id, job id, batch id, counts, error code. Avoid names, emails, school numbers, grade values, OAuth tokens, cookies, request bodies, import rows.

**Layer 3 · Exact assembly (dependencies):**

```bash
uv add structlog "sentry-sdk[fastapi]"
pnpm --filter @flrc/teacher add @sentry/react
pnpm --filter @flrc/admin add @sentry/react
```

`src/flrc/core/logging.py`:

```python
import logging
import sys

import structlog


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
```

Request-id middleware:

```python
import time
import uuid

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

log = structlog.get_logger()


async def request_context_middleware(request: Request, call_next):
    clear_contextvars()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["x-request-id"] = request_id
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response
```

Do not log query strings wholesale; search terms can contain names.

Sentry scrubber:

```python
SENSITIVE_KEYS = {
    "full_name", "email", "school_number", "score", "scale", "text_value",
    "old_score", "new_score", "old_text", "new_text", "cookie", "set-cookie",
    "authorization", "url", "query_string", "data", "x-flrc-gateway",
}


def scrub(value):
    if isinstance(value, dict):
        return {k: "[Filtered]" if k.casefold() in SENSITIVE_KEYS else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def before_send(event, hint):
    return scrub(event)


def before_breadcrumb(crumb, hint):
    return scrub(crumb)
```

Initialize with `send_default_pii=False`, `max_request_body_size="never"`,
`include_local_variables=False`, both scrubbers, environment/release, and a zero trace sample rate
until transaction metadata has been reviewed. In the browser, do not enable Session Replay by
default; screenshots/DOM can expose student data.

**Operational events to add now:** `oauth_login_succeeded` (user id only), `grade_batch_saved` (ids/counts), `conflict_detected`, `grant_created`, `undo_applied`, `import_committed`, `semester_reopened`, `year_archived`, `report_job_succeeded/failed`, `backup_restore_drill_recorded` (manual docs event, not app log).

**Check:** trigger a deliberate test exception whose local variable contains a fake student name and score. Inspect Sentry event: sensitive keys filtered. Grep production-like logs: no fake name, no email, no score value.

**If it breaks:** request body appears in Sentry breadcrumbs → disable/scrub integration data before launch. Search endpoint logs raw URL including `?q=Student Name` → log `request.url.path`, not full URL.

Commit: `ops: structured request telemetry with privacy scrubbers`.

## Step 4.8: Security and KVKK launch hardening

**What we're building:** the final threat-model pass before real children enter the database. This is not “add a security header and declare victory”; it is a concrete checklist tied to the system's actual trust boundaries.

**Layer 1 · Nudge:** secrets, cookies, origins, OAuth domain claim, allowlist, test-route absence, least privilege, output retention, logs, backups, dependencies, data-subject operations, incident path.

**Layer 2 · Guide (the launch gates):**

### Identity and session

- Google OAuth client under the school's Workspace, configured **Internal** where available.
- Validate the cryptographic ID token, exact `hd` claim, `email_verified=true`, and the school
  email domain; never trust only the login hint.
- Pre-registered active user allowlist remains the second gate.
- Bind the allowlist row to Google's stable `sub` on first login; a later mismatch is denied.
- `__Host-flrc_session`: host-only, HttpOnly, Secure in school HTTPS, SameSite=Lax, no
  JWT/localStorage tokens.
- Session secret is 48+ random bytes; rotate with a planned all-sessions logout.
- Sessions expire absolutely after at most eight hours.
- Deactivation rechecks DB and revokes Redis session keys.

### Request integrity

- Browser talks to same-origin `/api/*` proxy.
- School mode requires the secret Cloudflare-to-API gateway header and returns 404 at the direct
  managed API origin. Only the data-free liveness path bypasses it.
- State-changing requests pass Origin middleware against the exact public origin (and both exact
  local origins in development).
- No wildcard CORS.
- Request size limits on importer and any future uploads.
- Pydantic validates every external body; DB constraints backstop it.

### Data minimization

- No gender, birthdate, national id, home address.
- Synthetic data only in repo, screenshots, tests, demos, logs.
- Job output blob purged after 24h.
- Audit retained according to the school's written retention rule; do not invent a period in code without administrative approval.
- Error telemetry scrubbed; frontend replay off.

### Infrastructure

- Neon region/plan and backup location approved by school controller.
- Upstash region approved; Redis stores session ids and Celery messages containing only job ids.
- Google Drive backup destination owned/governed by school.
- GitHub repository private; secrets in Actions/hosting secret stores only.
- Production database credentials differ from demo/local.
- Migrations use direct URL; app uses pooled URL.

### Build/dependency supply chain

- Dependabot checks npm, Python, Docker, and GitHub Actions weekly.
- The locked-dependency audit runs on every repository plan. When GitHub Advanced Security is
  available, `GHAS_ENABLED=true` enables CodeQL for Python/TypeScript and dependency review for
  moderate-or-higher runtime vulnerabilities.
- CI pins official actions by major version at minimum; security-sensitive third-party actions by commit SHA if adopted.
- `pnpm audit`/`uv` ecosystem checks are advisory inputs, not blind auto-fix commands.
- Container rebuild at least monthly or on critical base-image CVE.

**Layer 3 · Exact assembly (security headers):** static frontends add `_headers` (or host equivalent):

```text
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Resource-Policy: same-origin
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Content-Security-Policy: default-src 'self'; connect-src 'self' https://*.ingest.sentry.io; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com
```

Treat CSP as a tested starting point. Browser console must be clean on login, grid, import, report download, Sentry initialization. Tighten the Sentry host to your actual DSN origin instead of a broad wildcard if practical.

Backend tests that are launch blockers:

- bad/missing Origin on POST → 403;
- unknown Google domain/claim path → refused;
- unverified Google email, missing `sub`, or a changed `sub` → refused;
- valid school Google account absent from allowlist → refused;
- inactive allowlisted user → 401;
- non-admin on admin mutation → 403;
- coordinator on coordinator read → 200, on admin write → 403;
- `/api/test/session` in `ENV=school` → 404;
- expired grant → no write permission;
- expired output → 410, blob absent after purge;
- request body above `MAX_REQUEST_BODY_BYTES` → 413, including streamed/chunked bodies;
- every data route enumerated without a session → 401;
- direct API request without `GATEWAY_SECRET` → 404;
- HTTP school request → HTTPS redirect; untrusted Host → 400;
- OpenAPI/docs in `ENV=school` → 404;
- archived year writes → 409.

Create `docs/PRIVACY-DATA-MAP.md` with five columns:

```text
Data category | Exact fields | Store/processor | Purpose | Retention/deletion owner
```

Create `docs/INCIDENT-RUNBOOK.md`: who disables access, how to deactivate all users if needed, rotate session secret, revoke OAuth client, rotate DB/Redis creds, preserve logs without copying student data, notify school controller, and document timeline. The legal notification obligations belong to the school's counsel/DPO; the runbook names that owner rather than guessing law in code.

**Check:** run a launch security review with a school administrator reading the data map. They should be able to answer where every category lives and who can see it.

Commit: `security: launch hardening and privacy operations docs`.

## Step 4.9: School production deployment with one frontend origin, Internal OAuth, API + worker

**School-hosted alternative (ADR-053 through ADR-058):** start from `infra/school-template/` in
a private school deployment repository. It pins both published images and carries the branding;
Caddy serves both SPAs and proxies the API. The migration, API, worker, and backup services share
the backend image. Use [SELF-HOSTING.md](SELF-HOSTING.md), [RELEASING.md](RELEASING.md), and
[RUNBOOK.md](RUNBOOK.md) for the current procedure. The assembly below describes the managed
Cloudflare/Render profile; do not mix its provider steps into a school VM deployment.

**What we're building:** the school-owned topology promised in Part I:

- teacher and admin SPAs as separate Cloudflare Pages deployments;
- one public school domain routes `/` to teacher, `/admin/*` to admin, and `/api/*` to Render;
- API and worker are separate Render web services from the same Docker image;
- Google OAuth client belongs to the school's Workspace;
- Neon/Upstash/Drive secrets belong to production, not demo.

**Why two frontends still:** different blast radius, navigation, deployment controls, and audience.
**Why one public origin:** one host-only session covers both panels, including logout, without
widening the cookie `Domain`. **Why the proxy still:** first-party cookie behavior and no token
storage remain worth one small edge gateway.

**Layer 1 · Nudge:** deploy both frontend builds, put a Worker/gateway in front with three fixed
route targets, attach one custom domain to the gateway, configure one exact backend origin and
OAuth callback, then deploy the two Render services.

**Layer 2 · Guide:** choose one school URL and reserve paths:

```text
https://flrc.school.k12.tr/          teacher
https://flrc.school.k12.tr/admin/*   admin
https://flrc.school.k12.tr/api/*     API proxy
https://flrc-api-school.onrender.com API origin behind the gateway only
```

The browser sees one origin. Deploy the admin build with `/admin/` as its Vite base and `/admin` as
its TanStack Router basepath. The gateway strips `/admin` when fetching the admin Pages upstream,
but the browser URL stays unchanged. Never accept an upstream target URL from query parameters.

**Layer 3 · Exact assembly (Cloudflare gateway contract):** create one Worker/gateway in front of
the two Pages deployments and Render. Its routing table, in this exact order, is:

```text
/api/*     → fixed Render API origin; preserve path and query
/admin     → admin Pages origin /
/admin/*   → admin Pages origin with the /admin prefix removed
everything → teacher Pages origin with path and query preserved
```

For API traffic, copy the incoming method, headers, and body; set `x-forwarded-host` and
`x-forwarded-proto` from the public URL; keep redirects manual so OAuth `Location` and
`Set-Cookie` reach the browser unchanged. Store all three origins as fixed Worker bindings or
environment variables. Validate that none can be supplied by a request.

Each Pages project still needs an SPA fallback:

```text
/* /index.html 200
```

The gateway owns the custom domain; the teacher and admin `*.pages.dev` domains are upstreams.
Set the frontend cross-links to the public `/admin` and `/` URLs, never to `pages.dev`.

**Production auth:** register one exact redirect URI in the production Google client:

```text
https://flrc.school.k12.tr/api/auth/callback
```

The teacher app owns `/login` and calls `/api/auth/login`. OAuth always uses the one public origin:

```python
redirect_uri = f"{settings.frontend_origin}/api/auth/callback"
return await oauth.google.authorize_redirect(request, redirect_uri)
```

On success, redirect to the teacher dashboard. Send all errors to `/login?error=...`. Anonymous
admin visits also redirect there; after authentication, an admin enters `/admin` through the
role-gated dashboard link. The OAuth state cookie and `flrc_session` both belong to the public
host. Keep the session cookie host-only; do not add a `Domain` attribute.

Production settings:

```text
ENV=school
FRONTEND_ORIGIN=https://flrc.school.k12.tr
ADMIN_ORIGIN=https://flrc.school.k12.tr
DATABASE_URL=<Neon pooled async URL>
DATABASE_URL_DIRECT=<Neon direct async URL>
REDIS_URL=<Upstash TLS URL>
SESSION_SECRET=<random>
GATEWAY_SECRET=<different random secret, also stored as encrypted Cloudflare Worker binding>
GOOGLE_CLIENT_ID=<school Workspace client>
GOOGLE_CLIENT_SECRET=<school Workspace secret>
ALLOWED_GOOGLE_DOMAIN=school.k12.tr
TRUSTED_HOSTS=flrc.school.k12.tr,flrc-api-school.onrender.com
SESSION_TTL_SECONDS=28800
MAX_REQUEST_BODY_BYTES=12582912
WORKER_HEALTH_URL=https://<worker-service>.onrender.com/health
OPS_TOKEN=<random>
SENTRY_DSN=<scrubbed school project, optional>
```

**Render service split:** same repo/image, different start commands.

API:

```text
uv run uvicorn flrc.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips=*
```

Worker web service:

```text
./bin/start-worker-web.sh
```

Use `infra/render/render.yaml` if you want infrastructure-as-code, but never commit secret values. Configure the health paths `/api/healthz` and `/health`, respectively.

**OAuth school client:** under the school's Google Cloud/Workspace control, create a separate
production Web application client. Register the one exact public callback URI above. Keep the demo
client separate forever. If Workspace allows Internal user type, use it; still keep the app's `hd`
claim, verified-email, stable-subject, and allowlist checks because domain membership alone is not
authorization.

Before the first OAuth login, run migrations and create the only bootstrap administrator with
`uv run flrc bootstrap-admin --email <school-email> --name "<administrator name>"`. Once an
active admin exists, the command refuses further bootstrap changes; use the authenticated admin
table for every later account.

**Migration discipline on launch:** deploy code that is backward-compatible with the current schema; run `alembic upgrade head` against the direct URL; then switch traffic/use deployment. Never auto-run destructive migrations blindly on every web process boot; two services racing a migration is the wrong robot.

**Check (full production loop):** teacher URL → Google school login → teacher SPA → `/api/me`
same-origin → `/admin` opens without another login → logout there → `/` is logged out too. Then
sign in again, save a grade, refresh, and generate a report: API 202, worker wakes, job progresses,
download succeeds after worker restart. Run one manual backup.

**If it breaks:** cookie absent → proxy stripped `Set-Cookie`, callback origin mismatch, or Secure/SameSite config wrong. Origin middleware rejects production POST → exact public origins missing. OAuth redirect mismatch → registered URI differs by one character. Worker health green but tasks never run → worker process died while health stub stayed alive; the start script must exit if either child exits.

**Docs:** Cloudflare Pages Functions routing/bindings; Render service docs; Google OIDC docs.

Commit: `deploy: school production topology`.

## Step 4.10: The launch runbook, rollback, and first-week operations

**Current operator entry point:** [RUNBOOK.md](RUNBOOK.md) contains the maintained checklist,
including paired image upgrades, backup service commands, and the pending comment-migration
rollback caveat. Treat the original walkthrough below as teaching context. Release readiness
must be recorded for the actual reviewed revision in [TODO.md](TODO.md).

**What we're building:** the document that lets Future You operate the system at 08:15 on a Monday when teachers are waiting. Launch is not a button; it is a sequence with abort conditions.

**Layer 1 · Nudge:** preflight, migration, smoke, pilot, rollback, restore, first-week checks, ownership.

**Layer 2 · Guide:** create `docs/RUNBOOK.md` with commands and exact dashboards/owners. A runbook is executable prose: no “check the database”; write the query/URL/expected result.

**Layer 3 · Exact assembly (launch sequence):**

### T-7 days

- Production accounts/projects created under school control.
- Privacy data map reviewed.
- OAuth client approved.
- Real teacher allowlist prepared.
- Restore drill completed from a fresh production-format dump.
- Report PDFs printed on the school's actual printer.
- One coordinator and one admin complete acceptance checklist.
- Freeze schema except launch blockers.

### T-1 day

- `main` green: lint, typecheck, unit, API, E2E, build.
- Tag release: `v1.0.0`.
- Manual production backup.
- Record current Alembic revision:

```bash
uv run alembic current
uv run alembic heads
```

They must agree after migration.

- Verify secrets by **presence**; never print values.
- Confirm no test route:

```bash
curl -i https://flrc.school.k12.tr/api/test/session
# 404
```

### Launch window

1. Announce maintenance/pilot window.
2. Take a pre-launch backup; record the filename + SHA.
3. Run `alembic upgrade head` against the direct URL.
4. Deploy API.
5. Deploy worker.
6. Deploy teacher/admin SPAs.
7. Smoke:
   - healthz 204 with an empty body;
   - shared login, then admin-link navigation;
   - `/api/me` correct;
   - one synthetic/pilot grade save;
   - one conflict test in a dedicated pilot row if approved;
   - one report job;
   - one output download;
   - one logout/login.
8. Open to pilot teachers first, then broader staff.

### Abort conditions

Abort/rollback if any of these occur:

- authenticated users see another user's identity/data;
- grade save silently overwrites without conflict;
- archived/locked semester accepts a write;
- importer preview differs from commit;
- report output contains the wrong student's data;
- OAuth allows a non-allowlisted user;
- migration partially applies or current/head disagree.

### Rollback

Code rollback: redeploy the previous known-good image/frontend release.

Schema rollback: **do not reflexively run `alembic downgrade` on production data**. Prefer forward-fix unless the migration was explicitly designed/tested reversible and no new data depends on it. If corruption or a destructive migration occurred, restore the pre-launch backup into a new database, verify, and switch the connection only through the incident plan.

### First week, every school day

- API health and error rate.
- Worker/job failure count.
- Redis session/broker health.
- Database storage and connection count.
- Last backup timestamp.
- Jobs stuck `queued/running` > 30 min:

```sql
select id, kind, status, created_at, started_at
from job_runs
where status in ('queued','running')
  and created_at < now() - interval '30 minutes'
order by id;
```

- Recent failed jobs:

```sql
select id, kind, error_code, created_at
from job_runs
where status='failed'
order by id desc
limit 20;
```

- No PII in logs: spot-check structured events.

### Monthly

- Dependency update window.
- Check that expired job blobs were purged.
- Access review: active users/admins/coordinators.
- Review missing assignments and completeness anomalies.

### Quarterly or per school policy

- Full restore drill into scratch DB.
- Incident runbook tabletop.
- Privacy/data-retention review.
- OAuth/service-account access review.

**Operator endpoints:** keep `/api/healthz` public and bodyless (204). If you add deeper
`/api/ops/*` diagnostics, protect them with `OPS_TOKEN` and never expose student payloads. A useful
private health response contains DB/Redis reachability and worker URL status, nothing else.

**Check:** hand the runbook to another technically competent person. They should be able to deploy, verify, identify a stuck job, and perform the restore drill without asking what you meant. Any question they ask becomes a runbook edit.

Commit: `docs: production launch and operations runbook`.

## Step 4.11: Final test pass and Phase 4 exit

**What we're building:** the final proof bundle: automated tests, manual print/restore checks, security gates, operational ownership, and the release tag.

**Layer 3 · Exact assembly (run everything):**

```bash
pnpm generate
pnpm prettier --write .
pnpm turbo run lint typecheck test build
cd apps/backend && uv run pytest -q
cd ../.. && pnpm e2e

docker build -t flrc-api:release apps/backend
```

Then run container smoke:

```bash
docker run --rm -e ENV=dev -p 8000:8000 flrc-api:release \
  uv run uvicorn flrc.main:app --host 0.0.0.0 --port 8000
```

Open `/api/healthz`. Separately start the worker image against dev Redis/Postgres and render one PDF job.

Required automated proof:

- migration guard green;
- role matrix green;
- save/concurrency/conflict tests green;
- grants/undo/audit tests green;
- Phase-3 admin/import/lifecycle/history tests green;
- report data/HTML/PDF tests green;
- job state/download/expiry/purge tests green;
- Celery task idempotence test green;
- year export opens and has the seven expected sheets;
- E2E two-context collision green across five repeated runs;
- production-mode test route 404;
- origin/security guards green.

Required manual proof:

- Print one A5 progress PDF on the actual school printer.
- Print one German and one French A4 report.
- Long Turkish names and text do not clip.
- Generate a 30-student class zip on a production-like worker.
- Kill/restart the worker and verify the completed job download survives.
- Run a manual backup; restore it; open one grid against the restored DB.
- Deactivate a logged-in teacher and watch the session die.
- Run UI in TR, EN, DE, FR.
- Use the teacher grid on desktop and phone.
- Admin imports a synthetic workbook through dry-run and commit.
- Coordinator reads completeness but cannot mutate admin resources.

### Phase 4 exit checklist

- ✅ `job_runs` is table fourteen; Celery has no result backend.
- ✅ Queue messages contain ids, not student payloads.
- ✅ Report output survives worker restart and expires/purges after 24h.
- ✅ A5 progress and A4 German/French PDFs render and print correctly.
- ✅ Report Center survives refresh and stops polling on terminal state.
- ✅ Year export produces a portable seven-sheet workbook with formula-injection defense.
- ✅ Weekly `pg_dump` lands in school-governed Drive with SHA sidecar and retention.
- ✅ A real restore drill succeeded and is recorded.
- ✅ Playwright's two authenticated contexts reproduce the collision automatically.
- ✅ Test auth route is impossible in the school environment.
- ✅ Logs/Sentry contain ids/counts/error codes, not names/grades/emails.
- ✅ Security/data map/incident/runbook docs reviewed by the responsible school owner.
- ✅ Production teacher/admin apps use same-origin `/api` proxies.
- ✅ School OAuth client is separate from the demo client.
- ✅ Launch rollback path names code rollback and database restore explicitly.
- ✅ `git tag v1.0.0 && git push --tags`.

---

# Epilogue: What you actually built

Not a CRUD tutorial. Not a portfolio dashboard with fake cards. A bilingual, multi-role school information system with:

- Google Workspace identity plus server-side revocable sessions;
- a typed Python/TypeScript contract generated from OpenAPI;
- a schema where students keep grades across class moves by construction;
- optimistic concurrency that names the other writer instead of silently losing work;
- time-boxed cross-role grants and replayable undo from the audit log;
- Turkish-safe search and a hostile-input Excel importer with dry-run/commit identity;
- an explicit year/semester state machine and immutable archive posture;
- durable async PDF/export jobs with a quiet Celery worker;
- school-owned off-site backups with restore proof;
- two-browser E2E collision tests;
- privacy-aware logs, short-lived generated artifacts, and written operations.

The most valuable sentence in the whole project is still the one from Part I: **TanStack Query owns what the server said; Zustand owns what the human typed and hasn't sent.** The runner-up is the domain invariant Phase 3 proved: **moving a student changes an enrollment, not a grade.**

Keep `DECISIONS.md` written in your own words. Keep the demo synthetic. And when a future employer asks for a hard bug, do not show them a to-do app; show them two teachers colliding on version 3 of the same grade, the database refusing to lie, and the UI making the human choose what happens next.
