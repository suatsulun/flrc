import { request as requestFactory } from "@playwright/test";
import type { Browser } from "@playwright/test";
import { teacherOrigin } from "./origins";

export async function authenticatedContext(browser: Browser, email: string) {
  const api = await requestFactory.newContext({
    baseURL: teacherOrigin,
  });
  try {
    const response = await api.post("/api/test/session", {
      headers: { "x-e2e-secret": process.env.E2E_AUTH_SECRET ?? "" },
      data: { email },
    });
    if (!response.ok()) throw new Error(`test login failed: ${response.status()}`);
    return browser.newContext({ storageState: await api.storageState() });
  } finally {
    await api.dispose();
  }
}
