import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";

import { adminOrigin as adminUrl } from "./helpers/origins";

test("class tables clear languages, drag new notes, and remove columns and students", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/classes`);
  await expect(page.getByText("E2E Synthetic One", { exact: true })).toBeVisible();
  const language = page.getByLabel("E2E Synthetic One — Second language", { exact: true });
  for (const option of ["german", "", "french", ""]) {
    await language.selectOption(option);
    await expect(language).toHaveValue(option);
    await expect(language).toBeEnabled();
  }
  await page.getByRole("button", { name: "Add column", exact: true }).click();
  await page.getByLabel("Column title").fill("Synthetic Dragged Note");
  await page.getByLabel("Column type").selectOption("text");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const headers = page.getByTestId("class-column-header");
  await expect(headers.last()).toContainText("Synthetic Dragged Note");
  // Keep headers in view and move through intermediate points to start a native drag.
  await headers.first().scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: "Drag column Synthetic Dragged Note", exact: true })
    .dragTo(headers.first(), { steps: 10, scroll: "none" });
  await expect(headers.first()).toContainText("Synthetic Dragged Note");
  await page.reload();
  await expect(headers.first()).toContainText("Synthetic Dragged Note");
  await expect(language).toHaveValue("");
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Remove assessment columns" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Remove students", exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Remove column Synthetic Dragged Note", exact: true })
    .click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(
    page.getByTestId("remove-column-row").filter({ hasText: "Synthetic Dragged Note" }),
  ).toHaveCount(0);
  for (const subject of ["German", "French"]) {
    await page.getByRole("radio", { name: subject, exact: true }).click();
    await page.getByRole("radio", { name: "Table", exact: true }).click();
    await page.getByRole("button", { name: "Add column", exact: true }).click();
    await page.getByLabel("Column title").fill(`Synthetic ${subject} Note`);
    await page.getByLabel("Column type").selectOption("text");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(headers.last()).toContainText(`Synthetic ${subject} Note`);
    await page.getByRole("radio", { name: "Remove", exact: true }).click();
    await page
      .getByRole("button", { name: `Remove column Synthetic ${subject} Note`, exact: true })
      .click();
    await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
    await expect(
      page.getByTestId("remove-column-row").filter({ hasText: `Synthetic ${subject} Note` }),
    ).toHaveCount(0);
  }
  await page.getByRole("radio", { name: "Table", exact: true }).click();
  await page.getByRole("spinbutton", { name: "School number", exact: true }).fill("98998");
  await page
    .getByRole("textbox", { name: "Full name", exact: true })
    .fill("Synthetic Removable Student");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  await expect(page.getByText("Synthetic Removable Student", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await page
    .getByRole("button", { name: "Remove student Synthetic Removable Student", exact: true })
    .click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByTestId("remove-student-row").filter({ hasText: "Synthetic Removable Student" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Remove student Synthetic Removable Student", exact: true })
    .click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(
    page.getByTestId("remove-student-row").filter({ hasText: "Synthetic Removable Student" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Synthetic Removable Student", { exact: true })).toHaveCount(0);
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await page.screenshot({ path: "test-results/class-remove-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/class-remove-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
  await context.close();
});

test("class form drafts survive switching between table and removal panels", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminUrl}/admin/classes`);
  const number = page.getByRole("spinbutton", { name: "School number", exact: true });
  const name = page.getByRole("textbox", { name: "Full name", exact: true });
  await number.fill("98997");
  await name.fill("Synthetic Unsaved Student");
  await page.getByRole("button", { name: "Add column", exact: true }).click();
  await page.getByLabel("Column title").fill("Synthetic Unsaved Column");
  await page.getByLabel("Column type").selectOption("text");
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await expect(page.getByTestId("class-roster-surface")).toBeHidden();
  await expect(page.getByRole("button", { name: "Add column", exact: true })).toBeHidden();
  await page.getByRole("radio", { name: "Table", exact: true }).click();
  await expect(number).toHaveValue("98997");
  await expect(name).toHaveValue("Synthetic Unsaved Student");
  await expect(page.getByLabel("Column title")).toHaveValue("Synthetic Unsaved Column");
  await expect(page.getByLabel("Column type")).toHaveValue("text");
  await context.close();
});
