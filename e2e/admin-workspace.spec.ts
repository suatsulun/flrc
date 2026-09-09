import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";
import { expectContainedTable } from "./helpers/table";

test("admin manages the school from the class table", async ({ browser }) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/classes`);

  await expect(page.getByRole("heading", { name: "Class tables" })).toBeVisible();
  await expect(
    page.getByLabel("Academic year", { exact: true }).locator("option:checked"),
  ).toHaveText("E2E Synthetic Year");
  await expect(page.getByRole("button", { name: /^5\/A/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("E2E Synthetic One", { exact: true })).toBeVisible();
  await expect(page.getByLabel("E2E Synthetic One — School number")).toHaveValue("99001");

  const rosterSurface = page.getByTestId("class-roster-surface");
  await expectContainedTable(rosterSurface);

  const mainBefore = await page.locator("#main").boundingBox();
  await page.getByRole("button", { name: "Minimize side panel" }).click();
  const mainAfter = await page.locator("#main").boundingBox();
  expect(mainBefore).not.toBeNull();
  expect(mainAfter).not.toBeNull();
  expect(mainAfter!.width).toBeGreaterThan(mainBefore!.width + 100);
  await page.getByRole("button", { name: "Restore side panel" }).click();

  const header = page.getByRole("banner");
  const headerBefore = await header.boundingBox();
  await page.getByRole("button", { name: "Minimize top panel" }).click();
  expect(headerBefore).not.toBeNull();
  const restoreTopPanel = page.getByRole("button", { name: "Restore top panel" });
  await expect(restoreTopPanel).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => (await header.boundingBox())?.height)
    .toBeLessThan(headerBefore!.height);
  await restoreTopPanel.click();

  await page.getByRole("spinbutton", { name: "School number", exact: true }).fill("98999");
  await page.getByRole("textbox", { name: "Full name", exact: true }).fill("E2E Added Student");
  await page.getByRole("button", { name: "Add student" }).click();

  const addedRow = page.getByRole("row").filter({ hasText: "E2E Added Student" });
  await expect(addedRow).toBeVisible();
  await expect(page.locator("tbody tr").first()).toContainText("E2E Added Student");

  const targetTab = page.getByRole("button", { name: /^5\/B/ });
  await addedRow
    .getByRole("button", { name: "Move E2E Added Student to another class" })
    .dragTo(targetTab);
  await expect(addedRow).toBeHidden();
  await targetTab.click();
  await expect(page.getByText("E2E Added Student", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Add column" }).click();
  await page.getByLabel("Column title").fill("Participation");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("columnheader").filter({ hasText: "Participation" })).toBeVisible();
  await expect(page.getByTestId("class-roster-surface").locator("table")).toBeInViewport();

  await page.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("radio", { name: "Light" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);

  await context.close();
});
