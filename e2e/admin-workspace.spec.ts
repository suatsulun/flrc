import { expect, test } from "@playwright/test";
import type { AdminClassOut, RosterStudentOut } from "../packages/api-client/src/index";
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

test("admin manages a class from student cards on a phone", async ({ browser }) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  const page = await context.newPage();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${adminOrigin}/admin/classes`);
  const noSidewaysScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= 390);
  const yearId = await page.getByLabel("Academic year", { exact: true }).inputValue();
  const added = "E2E Phone Student";
  try {
    await expect(page.getByRole("button", { name: /^5\/A/ })).toHaveAttribute(
      "aria-current",
      "page",
    );

    // Each teacher role stacks above a select as wide as the card, so names never clip.
    const mainTeacher = page
      .locator("label")
      .filter({ has: page.locator("span", { hasText: /^Main teacher$/ }) })
      .locator("select");
    expect((await mainTeacher.boundingBox())!.width).toBeGreaterThan(300);

    // Cards by default: selection, school number and language stay editable on each card.
    const viewSwitch = page.getByRole("radiogroup", { name: "View", exact: true });
    await expect(viewSwitch.getByRole("radio", { name: "Cards", exact: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const cards = page.getByTestId("student-grade-card");
    const card = cards.filter({ hasText: "E2E Synthetic One" });
    await expect(card.getByRole("checkbox", { name: "Select E2E Synthetic One" })).toBeVisible();
    await expect(card.getByLabel("E2E Synthetic One — School number")).toHaveValue("99001");
    await expect(card.getByLabel("E2E Synthetic One — School number")).toBeEditable();
    // Each active column is listed with the role that grades it.
    await expect(card.getByRole("term").filter({ hasText: /^Exam/ })).toContainText("Main teacher");
    const language = card.getByLabel("E2E Synthetic One — Second language", { exact: true });
    for (const option of ["german", ""]) {
      await language.selectOption(option);
      await expect(language).toHaveValue(option);
      await expect(language).toBeEnabled();
    }
    // Dragging needs a mouse, so phones move students by ticking them instead.
    await expect(page.getByRole("button", { name: /to another class$/ })).toHaveCount(0);
    await expect(
      page.getByText("Tick students on their cards to move them to another class", {
        exact: false,
      }),
    ).toBeVisible();
    expect(await noSidewaysScroll()).toBe(true);

    // The add form sits under the cards; a ticked student moves through the toolbar.
    await page.getByRole("spinbutton", { name: "School number", exact: true }).fill("99990");
    await page.getByRole("textbox", { name: "Full name", exact: true }).fill(added);
    await page.getByRole("button", { name: "Add student", exact: true }).click();
    const addedCard = cards.filter({ hasText: added });
    await expect(addedCard).toBeVisible();
    await addedCard.getByRole("checkbox", { name: `Select ${added}`, exact: true }).click();
    const bulkActions = page.getByRole("toolbar", { name: "Actions for the selected students" });
    await bulkActions.getByLabel("Move to class…").selectOption({ label: "5/B" });
    await bulkActions.getByRole("button", { name: "Move", exact: true }).click();
    const moveDialog = page.getByRole("dialog");
    await expect(moveDialog).toContainText(`${added} will move from 5/A to 5/B.`);
    await moveDialog.getByRole("button", { name: "Move", exact: true }).click();
    await expect(page.getByText(`${added} was moved to 5/B.`)).toBeVisible();
    await expect(addedCard).toHaveCount(0);
    expect(await noSidewaysScroll()).toBe(true);

    // The table pins the selection, number and name columns narrowly while the rest scrolls.
    await viewSwitch.getByRole("radio", { name: "Table", exact: true }).click();
    await expect(cards).toHaveCount(0);
    const surface = page.getByTestId("class-roster-surface");
    const headers = surface.locator("thead th");
    const widths = await Promise.all(
      [0, 1, 2].map(async (index) => Math.round((await headers.nth(index).boundingBox())!.width)),
    );
    expect(widths).toEqual([40, 72, 120]);
    const nameCell = surface.getByRole("cell", { name: "E2E Synthetic One", exact: true });
    const before = (await nameCell.boundingBox())!.x;
    await surface.evaluate((element) => element.scrollBy({ left: 200 }));
    expect(await surface.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    expect((await nameCell.boundingBox())!.x).toBeCloseTo(before, 0);
    expect(await noSidewaysScroll()).toBe(true);
  } finally {
    // Later specs count this year's rosters; never leave the phone student behind.
    const listed = await page.request.get(`${adminOrigin}/api/admin/years/${yearId}/classes`);
    for (const schoolClass of (await listed.json()) as AdminClassOut[]) {
      const roster = await page.request.get(
        `${adminOrigin}/api/admin/classes/${schoolClass.id}/roster`,
      );
      for (const student of (await roster.json()) as RosterStudentOut[]) {
        if (student.full_name !== added) continue;
        await page.request.delete(
          `${adminOrigin}/api/admin/classes/${schoolClass.id}/roster/${student.student_id}`,
          { headers: { Origin: adminOrigin } },
        );
      }
    }
    await context.close();
  }
});
