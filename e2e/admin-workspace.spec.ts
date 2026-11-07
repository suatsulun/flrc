import { expect, test } from "@playwright/test";
import type { AdminClassOut } from "../packages/api-client/src/index";
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
  // The active year keeps its classes; deleting is offered in a setup year only.
  await expect(page.getByRole("button", { name: "Delete class", exact: true })).toBeDisabled();
  await expect(
    page.getByText("Classes can be deleted only while their academic year is in setup."),
  ).toBeVisible();

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
  const moveHandle = addedRow.getByRole("button", {
    name: "Move E2E Added Student to another class",
  });
  await moveHandle.scrollIntoViewIfNeeded();
  // Every move is confirmed first; cancelling leaves the student where they were.
  await moveHandle.dragTo(targetTab, { steps: 10, scroll: "none" });
  const moveDialog = page.getByRole("dialog");
  await expect(moveDialog).toContainText("E2E Added Student will move from 5/A to 5/B.");
  await moveDialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(moveDialog).toBeHidden();
  await expect(addedRow).toBeVisible();
  await moveHandle.dragTo(targetTab, { steps: 10, scroll: "none" });
  await moveDialog.getByRole("checkbox", { name: "Don’t ask again this session" }).click();
  await moveDialog.getByRole("button", { name: "Move", exact: true }).click();
  await expect(addedRow).toBeHidden();
  await expect(page.getByText("E2E Added Student was moved to 5/B.")).toBeVisible();
  await targetTab.click();
  await expect(page.getByText("E2E Added Student", { exact: true })).toBeVisible();

  // A bulk move uses the same confirmation, which this session now skips.
  await page.getByRole("checkbox", { name: "Select E2E Added Student", exact: true }).click();
  const bulkActions = page.getByRole("toolbar", { name: "Actions for the selected students" });
  await bulkActions.getByLabel("Move to class…").selectOption({ label: "5/A" });
  await bulkActions.getByRole("button", { name: "Move", exact: true }).click();
  await expect(page.getByText("E2E Added Student was moved to 5/A.")).toBeVisible();
  await expect(moveDialog).toHaveCount(0);
  await expect(addedRow).toBeHidden();
  await page.getByRole("button", { name: /^5\/A/ }).click();
  await expect(addedRow).toBeVisible();

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

test("admin edits and deletes an unused class of a setup year", async ({ browser }) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/classes`);
  const year = page.getByLabel("Academic year", { exact: true });
  await year.selectOption({ label: "2027-2028" });
  const yearId = await year.inputValue();
  try {
    await page.getByRole("button", { name: "Add class", exact: true }).click();
    await page.getByRole("textbox", { name: "Section", exact: true }).fill("C");
    await page.getByRole("button", { name: "Add class", exact: true }).click();
    await expect(page.getByRole("button", { name: /^5\/C/ })).toHaveAttribute(
      "aria-current",
      "page",
    );

    // The page's own buttons; the dialogs render outside the main landmark.
    const main = page.locator("#main");
    const edit = main.getByRole("button", { name: "Edit class", exact: true });
    await edit.click();
    const dialog = page.getByRole("dialog");
    const section = dialog.getByRole("textbox", { name: "Section", exact: true });
    await expect(section).toHaveValue("C");
    await section.fill("D");
    await section.press("Enter");
    await expect(page.getByText("5/C is now 5/D.")).toBeVisible();
    await expect(dialog).toHaveCount(0);
    await expect(edit).toBeFocused();
    await expect(page.getByRole("button", { name: /^5\/D/ })).toHaveAttribute(
      "aria-current",
      "page",
    );

    const remove = main.getByRole("button", { name: "Delete class", exact: true });
    await expect(remove).toBeEnabled();
    await remove.click();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(remove).toBeFocused();
    await expect(page.getByRole("button", { name: /^5\/D/ })).toBeVisible();
    await remove.click();
    await dialog.getByRole("button", { name: "Delete class", exact: true }).click();
    await expect(page.getByText("5/D was deleted.")).toBeVisible();
    await expect(page.getByRole("button", { name: /^5\/D/ })).toHaveCount(0);
  } finally {
    // Later specs import into this year and count its classes; never leave one behind.
    const listed = await page.request.get(`${adminOrigin}/api/admin/years/${yearId}/classes`);
    for (const leftover of (await listed.json()) as AdminClassOut[]) {
      if (leftover.name !== "5/C" && leftover.name !== "5/D") continue;
      await page.request.delete(`${adminOrigin}/api/admin/classes/${leftover.id}`, {
        headers: { Origin: adminOrigin },
      });
    }
    await context.close();
  }
});

test("a class deleted elsewhere closes its edit instead of editing the class shown next", async ({
  browser,
}) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const page = await context.newPage();
  // A fake clock lets the class list go stale without waiting half a minute.
  await page.clock.install();
  await page.goto(`${adminOrigin}/admin/classes`);
  const year = page.getByLabel("Academic year", { exact: true });
  await year.selectOption({ label: "2027-2028" });
  const yearId = await year.inputValue();
  const classes = async () =>
    (await (
      await page.request.get(`${adminOrigin}/api/admin/years/${yearId}/classes`)
    ).json()) as AdminClassOut[];
  try {
    for (const section of ["C", "D"]) {
      await page.getByRole("button", { name: "Add class", exact: true }).click();
      await page.getByRole("textbox", { name: "Section", exact: true }).fill(section);
      await page.getByRole("button", { name: "Add class", exact: true }).click();
      await expect(page.getByRole("button", { name: new RegExp(`^5/${section}`) })).toHaveAttribute(
        "aria-current",
        "page",
      );
    }
    await page.getByRole("button", { name: /^5\/C/ }).click();
    await expect(page.getByRole("button", { name: /^5\/C/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await page.locator("#main").getByRole("button", { name: "Edit class", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("textbox", { name: "Section", exact: true }).fill("E");

    // Another administrator deletes 5/C; the page's next refetch falls back to 5/D.
    const deleted = (await classes()).find((item) => item.name === "5/C");
    expect(deleted).toBeDefined();
    const removal = await page.request.delete(`${adminOrigin}/api/admin/classes/${deleted!.id}`, {
      headers: { Origin: adminOrigin },
    });
    expect(removal.ok()).toBe(true);
    await page.clock.fastForward("01:00");
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));

    // The draft was for 5/C: once the list no longer has it, the dialog closes rather than
    // saving the draft onto 5/D, the class the page falls back to.
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^5\/C/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^5\/D/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect((await classes()).map((item) => item.name)).toEqual(["5/D"]);
  } finally {
    // Later specs import into this year and count its classes; never leave one behind.
    for (const leftover of await classes()) {
      if (!["5/C", "5/D", "5/E"].includes(leftover.name)) continue;
      await page.request.delete(`${adminOrigin}/api/admin/classes/${leftover.id}`, {
        headers: { Origin: adminOrigin },
      });
    }
    await context.close();
  }
});
