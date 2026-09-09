/**
 * Origins for the two apps under test.
 *
 * Both are environment-driven so a session can run an isolated stack on its own
 * ports. A hardcoded origin here does not fail loudly — it silently drives
 * whichever stack happens to own the default port, which corrupts both runs.
 */
export const teacherOrigin = process.env.E2E_BASE_URL ?? "http://localhost:4173";
export const adminOrigin = process.env.E2E_ADMIN_BASE_URL ?? "http://localhost:5174";
