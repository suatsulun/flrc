import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example-school.k12.tr";

test("destructive user actions use the styled site dialog", async ({ browser }) => {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();

  await page.goto(`${adminOrigin}/admin/users`);
  await page.getByRole("button", { name: "Deactivate", exact: true }).first().click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Deactivate" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();

  await context.close();
});
