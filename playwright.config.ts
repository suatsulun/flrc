import { defineConfig, devices } from "@playwright/test";

/**
 * Two known limitations of this suite. Both are documented rather than fixed;
 * see the follow-ups on the PR that added this note.
 *
 * 1. **The specs share one database while Playwright runs several workers.**
 *    `fullyParallel` is false, so tests within a file are serial, but separate
 *    spec files still run concurrently. They read and write the same seeded
 *    school, so `admin-workspace.spec.ts` mutating class 5/A's columns can race
 *    `layout.spec.ts` measuring that same class's grade grid. That race is real:
 *    it is what exposed the sticky-clamp bug fixed in ADR-045 — the grid ended
 *    up with fewer columns than the spec assumed, which widened the forced
 *    minimum relative to the column sum. The bug is fixed; the coupling is not.
 *    Treat a timing-shaped failure here as shared state before blaming load.
 *
 * 2. **The suite is not idempotent against a dirty database.**
 *    `admin-workspace.spec.ts` adds a student with a fixed school number, so a
 *    second run without reseeding fails on the duplicate. Reseed between runs:
 *    `uv run flrc seed-e2e` from `apps/backend`. CI is unaffected because every
 *    run starts on a fresh database.
 *
 * ## Running an isolated stack
 *
 * Several sessions may work on this repo at once, so nothing here assumes the
 * default ports. Every origin is environment-driven; a hardcoded one does not
 * fail loudly, it silently drives whichever stack owns the port. Pick your own
 * ports, database, and Redis index, then:
 *
 * ```sh
 * # backend — origins must match the app ports below, or CSRF/origin checks reject
 * ENV=test E2E_AUTH_SECRET=... \
 *   DATABASE_URL=postgresql+asyncpg://flrc:flrc@localhost:5432/flrc_myfeature \
 *   DATABASE_URL_DIRECT=... REDIS_URL=redis://localhost:6379/3 \
 *   FRONTEND_ORIGIN=http://localhost:4273 ADMIN_ORIGIN=http://localhost:5274 \
 *   uv run uvicorn flrc.main:app --host 127.0.0.1 --port 8100
 *
 * # apps — VITE_API_TARGET points each preview's /api proxy at that backend
 * VITE_API_TARGET=http://localhost:8100 pnpm --filter @flrc/teacher preview --port 4273
 * VITE_API_TARGET=http://localhost:8100 pnpm --filter @flrc/admin   preview --port 5274
 *
 * # specs — both origins, or the run drives the default ports instead
 * E2E_BASE_URL=http://localhost:4273 E2E_ADMIN_BASE_URL=http://localhost:5274 pnpm e2e
 * ```
 *
 * `e2e/helpers/origins.ts` holds both origins; add new ones there rather than
 * inlining a literal in a spec.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
