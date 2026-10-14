import { randomUUID } from "node:crypto";
import { expect, test as base, type BrowserContext } from "@playwright/test";
import type { ManagedUserOut, UserCreate } from "../../packages/api-client/src/index";
import { authenticatedContext } from "./auth";
import { teacherOrigin } from "./origins";

// Import workflows must not inherit another test's per-account allowance.
// Use real accounts and normal admin endpoints; keep the limiter fully enabled.
export const test = base.extend<{ importContext: BrowserContext }>({
  importContext: async ({ browser }, use) => {
    const operator = await authenticatedContext(browser, "admin@example-school.k12.tr");
    const endpoint = `${teacherOrigin}/api/admin/users`;
    const headers = { Origin: teacherOrigin };
    const email = `import-${randomUUID()}@example-school.k12.tr`;
    let userId: number | undefined;
    let context: BrowserContext | undefined;
    try {
      const created = await operator.request.post(endpoint, {
        headers,
        data: {
          email,
          full_name: "E2E Isolated Import Admin",
          is_admin: true,
          teaching_field: "english",
          teaching_stage: "middle",
        } satisfies UserCreate,
      });
      expect(created.status()).toBe(201);
      userId = ((await created.json()) as ManagedUserOut).id;
      context = await authenticatedContext(browser, email);
      await use(context);
    } finally {
      try {
        await context?.close();
        if (userId !== undefined) {
          const deactivated = await operator.request.patch(`${endpoint}/${userId}`, {
            headers,
            data: { is_active: false },
          });
          expect(deactivated.status()).toBe(200);
        }
      } finally {
        await operator.close();
      }
    }
  },
});
