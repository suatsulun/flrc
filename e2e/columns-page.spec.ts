import { expect, test } from "@playwright/test";
import { authenticatedContext } from "./helpers/auth";
import { adminOrigin } from "./helpers/origins";

test("the column page renames and copies columns, each with Undo", async ({ browser }) => {
  const context = await authenticatedContext(browser, "admin@example-school.k12.tr");
  await context.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  const page = await context.newPage();
  await page.goto(`${adminOrigin}/admin/columns?grade=5&subject=english`);

  await page.getByRole("button", { name: "Rename column Exam", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const name = dialog.getByLabel("Column name (English)");
  await expect(name).toHaveValue("Exam");
  await name.fill("   ");
  await expect(dialog.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await name.fill("Written exam");
  await name.press("Enter");
  await expect(page.getByText("Column “Exam” was renamed to “Written exam”.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Rename column Written exam", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByText("Change undone.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Rename column Exam", exact: true })).toBeVisible();
  // Row actions name the field they act on, and the add dialog has a visible Cancel.
  await expect(
    page.getByRole("button", { name: "Move column Exam down", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete column Exam", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Add column", exact: true }).click();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toHaveCount(0);

  await page.getByRole("button", { name: "Copy to another grade or subject", exact: true }).click();
  // English columns copy to English only.
  await expect(dialog.getByLabel("Target subject").locator("option")).toHaveText(["English"]);
  await expect(dialog).toContainText("Source and target are the same");
  await expect(dialog.getByRole("button", { name: "Copy", exact: true })).toBeDisabled();
  await dialog.getByLabel("Target grade").selectOption("6");
  await expect(dialog).toContainText("Grade 6 · English has no columns yet.");
  await dialog.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(page.getByText(/^\d+ columns were copied\.$/)).toBeVisible();
  await expect(page).toHaveURL(/grade=6/);
  await expect(page.getByRole("button", { name: "Rename column Exam", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByText("No columns yet", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
  await context.close();
});
