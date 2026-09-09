import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example-school.k12.tr";

test("teacher groups, translated fields, and year activation state stay explicit", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();

  await page.goto(`${adminOrigin}/admin/assignments`);
  const cards = page.getByTestId("assignment-teacher-card");
  await expect(cards).toHaveCount(28);

  await page.getByRole("radio", { name: "Primary", exact: true }).click();
  await expect(cards).toHaveCount(12);
  await expect(cards.first()).toHaveAttribute("data-teaching-stage", "primary");
  await expect(page.getByRole("radio", { name: "5", exact: true })).toHaveCount(0);

  await page.getByRole("radio", { name: "Middle school", exact: true }).click();
  await expect(cards).toHaveCount(12);
  await expect(cards.first()).toHaveAttribute("data-teaching-stage", "middle");

  await page.getByRole("radio", { name: "German", exact: true }).click();
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toHaveAttribute("data-teaching-field", "german");

  await page.getByRole("radio", { name: "French", exact: true }).click();
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toHaveAttribute("data-teaching-field", "french");

  await page.getByRole("radio", { name: "All teachers", exact: true }).click();
  await expect(cards).toHaveCount(28);

  await page.goto(`${adminOrigin}/admin/users`);
  await expect(page.getByRole("columnheader", { name: "Teaching field" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "School level" })).toBeVisible();
  await expect(page.getByText("users.teachingField", { exact: true })).toHaveCount(0);

  await page.goto(`${adminOrigin}/admin/lifecycle`);
  const setupYear = page.locator('[data-testid="lifecycle-year"][data-year-status="setup"]');
  await expect(setupYear).toHaveCount(1);
  await expect(setupYear).toHaveAttribute("data-missing-school-numbers", "0");
  await expect(
    setupYear.getByText("Finish and archive E2E Synthetic Year before activating this year."),
  ).toBeVisible();
  await expect(setupYear.getByRole("button", { name: "Activate" })).toBeDisabled();
  await expect(setupYear.getByText("Locked", { exact: true })).toHaveCount(2);

  const activeYear = page.locator('[data-testid="lifecycle-year"][data-year-status="active"]');
  if ((await activeYear.count()) === 1) {
    const activeSemesterCount = await activeYear
      .locator("dl")
      .getByText("Active", { exact: true })
      .count();
    expect(activeSemesterCount).toBeLessThanOrEqual(1);
  }

  await context.close();
});
