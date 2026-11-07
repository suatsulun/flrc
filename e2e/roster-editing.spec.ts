import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";

import { adminOrigin as adminUrl } from "./helpers/origins";

test("class tables clear languages, drag new notes, and remove columns and students", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  // The specs share one database; a retry must not collide with what a failed attempt left.
  const attempt = test.info().retry;
  const dragged = `Synthetic Dragged Note ${attempt}`;
  const renamed = `Synthetic Renamed Note ${attempt}`;
  const removable = `Synthetic Removable Student ${attempt}`;
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
  await page.getByLabel("Column title").fill(dragged);
  // Grades 5-8 English take no written notes (ADR-063), so the text type is not offered.
  await expect(page.getByLabel("Column type").locator('option[value="text"]')).toHaveCount(0);
  await page.getByLabel("Column type").selectOption("scale3");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const headers = page.getByTestId("class-column-header");
  await expect(headers.last()).toContainText(dragged);
  // Keep headers in view and move through intermediate points to start a native drag.
  await headers.first().scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: `Drag column ${dragged}`, exact: true })
    .dragTo(headers.first(), { steps: 10, scroll: "none" });
  await expect(headers.first()).toContainText(dragged);
  await page.reload();
  await expect(headers.first()).toContainText(dragged);
  await expect(language).toHaveValue("");
  // Renaming keeps the field (and its grades); Escape leaves the name untouched and returns
  // focus to the header button that opened the dialog.
  const rename = page.getByRole("button", { name: `Rename column ${dragged}`, exact: true });
  await rename.click();
  const renameBox = page.getByRole("dialog").getByLabel("Column name (English)");
  await expect(renameBox).toHaveValue(dragged);
  await renameBox.fill("Discarded name");
  await renameBox.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(rename).toBeFocused();
  await rename.click();
  await expect(renameBox).toHaveValue(dragged);
  await renameBox.fill(renamed);
  await renameBox.press("Enter");
  await expect(page.getByText(`Column “${dragged}” was renamed to “${renamed}”.`)).toBeVisible();
  await expect(headers.first()).toContainText(renamed);
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Remove assessment columns" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Remove students", exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Remove column ${renamed}`, exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByTestId("remove-column-row").filter({ hasText: renamed })).toHaveCount(0);
  for (const subject of ["German", "French"]) {
    await page.getByRole("radio", { name: subject, exact: true }).click();
    await page.getByRole("radio", { name: "Table", exact: true }).click();
    await page.getByRole("button", { name: "Add column", exact: true }).click();
    await page.getByLabel("Column title").fill(`Synthetic ${subject} Note ${attempt}`);
    await page.getByLabel("Column type").selectOption("text");
    // The karne prints Turkish beside German/French notes, so the wording box appears for them.
    await page.getByLabel("Turkish wording on the report card").fill(`Sentetik ${subject} not`);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(headers.last()).toContainText(`Synthetic ${subject} Note ${attempt}`);
    await page.getByRole("radio", { name: "Remove", exact: true }).click();
    await page
      .getByRole("button", {
        name: `Remove column Synthetic ${subject} Note ${attempt}`,
        exact: true,
      })
      .click();
    await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
    await expect(
      page
        .getByTestId("remove-column-row")
        .filter({ hasText: `Synthetic ${subject} Note ${attempt}` }),
    ).toHaveCount(0);
  }
  await page.getByRole("radio", { name: "Table", exact: true }).click();
  await page
    .getByRole("spinbutton", { name: "School number", exact: true })
    .fill(String(98998 - attempt * 10));
  await page.getByRole("textbox", { name: "Full name", exact: true }).fill(removable);
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  await expect(page.getByText(removable, { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  const removeStudent = page.getByRole("button", {
    name: `Remove student ${removable}`,
    exact: true,
  });
  await removeStudent.click();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByTestId("remove-student-row").filter({ hasText: removable })).toBeVisible();
  await expect(removeStudent).toBeFocused();
  await removeStudent.click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByTestId("remove-student-row").filter({ hasText: removable })).toHaveCount(
    0,
  );
  await page.reload();
  await expect(page.getByText(removable, { exact: true })).toHaveCount(0);
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
  await page.getByLabel("Column type").selectOption("scale3");
  await page.getByRole("radio", { name: "Remove", exact: true }).click();
  await expect(page.getByTestId("class-roster-surface")).toBeHidden();
  await expect(page.getByRole("button", { name: "Add column", exact: true })).toBeHidden();
  await page.getByRole("radio", { name: "Table", exact: true }).click();
  await expect(number).toHaveValue("98997");
  await expect(name).toHaveValue("Synthetic Unsaved Student");
  await expect(page.getByLabel("Column title")).toHaveValue("Synthetic Unsaved Column");
  await expect(page.getByLabel("Column type")).toHaveValue("scale3");
  await context.close();
});

test("an undone school number shows again and is not re-sent from the input", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  const saves: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "PATCH" && /\/roster\/\d+$/.test(new URL(request.url()).pathname)) {
      saves.push(request.postData() ?? "");
    }
  });
  await page.goto(`${adminUrl}/admin/classes`);
  const input = page.getByLabel("E2E Synthetic One — School number", { exact: true });
  await expect(input).toHaveValue(/^\d+$/);
  const before = await input.inputValue();
  const edited = String(Number(before) + 10);
  await input.fill(edited);
  await input.blur();
  await expect(page.getByText(`E2E Synthetic One’s school number is now ${edited}.`)).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByText("Change undone.")).toBeVisible();
  // The input follows the restored number instead of keeping the undone one.
  await expect(input).toHaveValue(before);
  await expect(input).toBeEnabled();
  // Leaving the input again sends nothing, so the undo stays undone.
  await input.focus();
  await input.blur();
  await page.waitForLoadState("networkidle");
  expect(saves).toHaveLength(1);
  await page.reload();
  await expect(input).toHaveValue(before);
  await context.close();
});
