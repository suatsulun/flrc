import type { MeOut } from "@flrc/api-client";
import { expect, test } from "@playwright/test";
import { adminOrigin, teacherOrigin } from "./helpers/origins";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
});

test("login renders while the session request is still pending", async ({ page }) => {
  await page.route("**/api/me", () => {});
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible({
    timeout: 2_000,
  });
});

test("a stalled session check releases the teacher route to login", async ({ page }) => {
  await page.route("**/api/me", () => {});
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible({
    timeout: 8_000,
  });
  await expect(page).toHaveURL(`${teacherOrigin}/login`);
});

test("a stalled session check releases the admin route to its login destination", async ({
  page,
}) => {
  await page.route("**/api/me", () => {});
  // The admin build owns the teacher origin; intercept its destination so this
  // guard test also works with CI's default build-time development origin.
  await page.route("**/login", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Sign-in destination</h1>" }),
  );
  await page.goto(`${adminOrigin}/admin/`);
  await expect(page.getByRole("heading", { name: "Sign-in destination" })).toBeVisible({
    timeout: 8_000,
  });
});

for (const status of [401, 503]) {
  test(`login remains usable after a ${status} session response`, async ({ page }) => {
    let checks = 0;
    await page.route("**/api/me", (route) => {
      checks += 1;
      return route.fulfill({ status, json: { detail: "unavailable" } });
    });
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({ contentType: "text/html", body: "<h1>Google sign-in started</h1>" }),
    );
    await page.goto("/login");
    const signIn = page.getByRole("button", { name: "Sign in with Google" });
    await expect(signIn).toBeEnabled();
    await signIn.click();
    await expect(page.getByRole("heading", { name: "Google sign-in started" })).toBeVisible();
    expect(checks).toBe(1);
  });
}

test("an existing session still redirects from login when its check succeeds", async ({ page }) => {
  const user: MeOut = {
    id: 1,
    full_name: "Synthetic Teacher",
    email: "teacher@example-school.k12.tr",
    is_admin: false,
    is_coordinator: false,
    assignments: [],
  };
  let releaseSession!: () => void;
  const sessionReady = new Promise<void>((resolve) => {
    releaseSession = resolve;
  });
  await page.route("**/api/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/me", async (route) => {
    await sessionReady;
    await route.fulfill({ json: user });
  });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible();
  releaseSession();
  await expect(page).toHaveURL(`${teacherOrigin}/`);
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeHidden();
});
