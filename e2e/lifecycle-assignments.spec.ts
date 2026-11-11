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
  // Desktop keeps every card open beside the drag tray; collapsing is phone-only.
  await expect(page.locator("#main aside")).toBeVisible();
  await expect(cards.locator("[aria-expanded]")).toHaveCount(0);

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

test("phones assign and remove classes by tapping instead of dragging", async ({ browser }) => {
  const context = await authenticatedContext(browser, adminEmail);
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto(`${adminOrigin}/admin/assignments`);
  const cards = page.getByTestId("assignment-teacher-card");
  await expect(cards).toHaveCount(28);
  await expect(page.getByText(/^Tap a teacher to expand their card/)).toBeVisible();
  await expect(page.getByText(/^Drag classes from the tray/)).toHaveCount(0);
  await expect(page.locator("#main aside")).toBeHidden();
  // Every teacher starts as one collapsed line, so the page stays short and never scrolls sideways.
  await expect(cards.getByRole("button", { expanded: false })).toHaveCount(28);
  await expect(cards.getByRole("button", { expanded: true })).toHaveCount(0);
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight,
  }));
  expect(size.width).toBeLessThanOrEqual(390);
  expect(size.height).toBeLessThan(2200);

  const card = cards.filter({ hasText: "E2E Middle Teacher 01" });
  const toggle = card.locator("button[aria-expanded]");
  await expect(toggle).toHaveAccessibleName(
    "E2E Middle Teacher 01 English Middle school Classes: 0",
  );
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(card.getByText("middle-01@example-school.k12.tr")).toBeVisible();

  // The picker offers only the teacher's stage and names who holds a slot already.
  const addMain = card.getByRole("button", {
    name: "E2E Middle Teacher 01 — Main teacher — Add class",
  });
  await addMain.click();
  const mainPicker = page.getByRole("dialog", { name: "E2E Middle Teacher 01 · Main teacher" });
  await expect(mainPicker.getByRole("radio")).toHaveText(["5", "6", "7", "8"]);
  await expect(mainPicker.getByRole("radio", { name: "5", exact: true })).toBeChecked();
  await expect(mainPicker.getByRole("listitem").filter({ hasText: "5/A" })).toContainText(
    "E2E Owner",
  );
  await expect(mainPicker.getByRole("checkbox", { name: "5/A", exact: true })).not.toBeChecked();
  await page.keyboard.press("Escape");
  await expect(mainPicker).toBeHidden();
  await expect(addMain).toBeFocused();

  const addSkills = card.getByRole("button", {
    name: "E2E Middle Teacher 01 — Skills / LGS teacher — Add class",
  });
  const addBox = await addSkills.boundingBox();
  expect(addBox?.height).toBeGreaterThanOrEqual(40);
  await addSkills.click();
  const skillsPicker = page.getByRole("dialog", {
    name: "E2E Middle Teacher 01 · Skills teacher",
  });
  const row = skillsPicker.getByRole("listitem").filter({ hasText: "5/A" });
  await expect(row).toContainText("Not assigned");
  // While the save is in flight the picker stays open, so focus can return to an enabled opener.
  const { promise: held, resolve: release } = Promise.withResolvers<void>();
  await page.route("**/api/admin/years/*/assignments", async (route) => {
    if (route.request().method() === "PUT") await held;
    await route.continue();
  });
  await row.getByRole("checkbox", { name: "5/A", exact: true }).click();
  await expect(skillsPicker.getByRole("button", { name: "Done" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(skillsPicker).toBeVisible();
  release();
  await expect(
    page.getByText("E2E Middle Teacher 01 assigned to 5/A as Skills teacher."),
  ).toBeVisible();
  await page.unroute("**/api/admin/years/*/assignments");
  await expect(row.getByRole("checkbox", { name: "5/A", exact: true })).toBeChecked();
  await expect(row).toContainText("Assigned");
  await skillsPicker.getByRole("button", { name: "Done" }).click();
  await expect(skillsPicker).toBeHidden();
  await expect(addSkills).toBeFocused();

  const remove = card.getByRole("button", { name: "Remove 5/A from E2E Middle Teacher 01" });
  const removeBox = await remove.boundingBox();
  expect(removeBox?.width).toBeGreaterThanOrEqual(40);
  expect(removeBox?.height).toBeGreaterThanOrEqual(40);
  await expect(toggle).toContainText("Classes: 1");
  await remove.click();
  await expect(
    page.getByText("E2E Middle Teacher 01 removed from 5/A as Skills teacher."),
  ).toBeVisible();
  await expect(remove).toHaveCount(0);
  await expect(card.getByText("No classes assigned yet")).toHaveCount(2);
  await expect(toggle).toContainText("Classes: 0");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(card.getByText("middle-01@example-school.k12.tr")).toHaveCount(0);

  await context.close();
});
