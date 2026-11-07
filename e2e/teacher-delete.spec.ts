import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { ManagedUserOut, UserCreate } from "../packages/api-client/src/index";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

test("a deactivated teacher is deleted only after the five-second countdown", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const endpoint = `${adminOrigin}/api/admin/users`;
  const headers = { Origin: adminOrigin };
  const email = `leaver-${randomUUID()}@example-school.k12.tr`;
  const created = await context.request.post(endpoint, {
    headers,
    data: {
      email,
      full_name: "E2E Departing Teacher",
      teaching_field: "english",
      teaching_stage: "middle",
    } satisfies UserCreate,
  });
  expect(created.status()).toBe(201);
  const userId = ((await created.json()) as ManagedUserOut).id;
  const deactivated = await context.request.patch(`${endpoint}/${userId}`, {
    headers,
    data: { is_active: false },
  });
  expect(deactivated.status()).toBe(200);

  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/users`);
  const row = page.getByRole("row").filter({ hasText: email });
  const deleteRow = row.getByRole("button", { name: "Delete permanently", exact: true });
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: /^Delete permanently/ });

  // Cancel works at once, while the delete button is still locked.
  await deleteRow.click();
  await expect(
    dialog.getByRole("heading", { name: "Permanently delete E2E Departing Teacher?" }),
  ).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(confirm).toHaveText("Delete permanently (5)");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(row).toBeVisible();

  // Reopening restarts the countdown; the button unlocks only after five seconds.
  await deleteRow.click();
  const opened = Date.now();
  await expect(confirm).toHaveText("Delete permanently (5)");
  await expect(confirm).toBeDisabled();
  await expect(confirm).toHaveText("Delete permanently (3)", { timeout: 4_000 });
  await expect(confirm).toBeDisabled();
  await expect(confirm).toBeEnabled({ timeout: 7_000 });
  expect(Date.now() - opened).toBeGreaterThanOrEqual(4_500);
  await expect(confirm).toHaveText("Delete permanently");
  await confirm.click();

  await expect(dialog).toBeHidden();
  await expect(row).toHaveCount(0);
  const toast = page
    .getByRole("listitem")
    .filter({ hasText: "E2E Departing Teacher was permanently deleted. This cannot be undone." });
  await expect(toast).toBeVisible();
  await expect(toast.getByRole("button", { name: "Undo" })).toHaveCount(0);

  // The address is free again for a new account.
  const listed = (await (await context.request.get(endpoint)).json()) as ManagedUserOut[];
  expect(listed.some((user) => user.id === userId)).toBe(false);
  const again = await context.request.post(endpoint, {
    headers,
    data: {
      email,
      full_name: "E2E Returning Teacher",
      teaching_field: "english",
      teaching_stage: "middle",
    } satisfies UserCreate,
  });
  expect(again.status()).toBe(201);
  const returning = ((await again.json()) as ManagedUserOut).id;
  // Clean up the returning account the same way, so the seeded teacher list stays as it was.
  const retired = await context.request.patch(`${endpoint}/${returning}`, {
    headers,
    data: { is_active: false },
  });
  expect(retired.status()).toBe(200);
  const removed = await context.request.delete(`${endpoint}/${returning}`, { headers });
  expect(removed.status()).toBe(200);
  await context.close();
});

test("the teachers table fills its card and its selects show whole options", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => {
    if (!sessionStorage.getItem("language-set")) localStorage.setItem("i18nextLng", "tr");
  });
  const page = await context.newPage();
  const table = page.getByRole("table");
  const fit = () =>
    table.evaluate((element) => {
      const viewport = element.closest("[data-slot=table-scroll]")!;
      return {
        gap: viewport.clientWidth - element.getBoundingClientRect().width,
        overflow: viewport.scrollWidth - viewport.clientWidth,
      };
    });

  // In Turkish the whole row fits a 1440px screen, and on a wider one the table still meets
  // the card's right edge: no empty strip right of the actions, no sideways scrolling.
  for (const width of [1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${adminOrigin}/admin/users`);
    await expect(table.getByRole("row").nth(1)).toBeVisible();
    const { gap, overflow } = await fit();
    expect(gap, `${width}px gap`).toBeLessThanOrEqual(1);
    expect(overflow, `${width}px overflow`).toBeLessThanOrEqual(1);
  }

  for (const language of ["tr", "en", "de", "fr"]) {
    await page.evaluate((value) => {
      sessionStorage.setItem("language-set", "1");
      localStorage.setItem("i18nextLng", value);
    }, language);
    await page.goto(`${adminOrigin}/admin/users`);
    await expect(table.getByRole("row").nth(1)).toBeVisible();
    expect((await fit()).gap, language).toBeLessThanOrEqual(1);
    const clipped = await page.locator("select").evaluateAll((selects) => {
      const context = document.createElement("canvas").getContext("2d")!;
      return selects.flatMap((select) => {
        const style = getComputedStyle(select as HTMLSelectElement);
        context.font = style.font;
        const room =
          select.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return [...(select as HTMLSelectElement).options]
          .filter((option) => context.measureText(option.text).width > room + 0.5)
          .map((option) => `${select.getAttribute("aria-label") ?? select.id}: ${option.text}`);
      });
    });
    expect(clipped, language).toEqual([]);
  }

  // A phone keeps the page itself from scrolling sideways; the table scrolls in its card.
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(`${adminOrigin}/admin/users`);
  await expect(table.getByRole("row").nth(1)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await context.close();
});
